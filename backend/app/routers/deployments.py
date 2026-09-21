"""部署生命周期路由。"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import orchestrator
from ..db import get_db
from ..engines import EngineError
from ..models import Deployment, DeploymentEvent, DeploymentStatus, Model, User
from ..schemas import (
    DeploymentCreate,
    DeploymentDetail,
    DeploymentEventOut,
    DeploymentOut,
    DeploymentUpdate,
)
from ..security import get_current_user

router = APIRouter(prefix="/api/deployments", tags=["部署管理"])


def _to_out(db: Session, deployment: Deployment) -> DeploymentOut:
    out = DeploymentOut.model_validate(deployment)
    model = db.get(Model, deployment.model_id)
    out.model_name = model.display_name if model else ""
    return out


def _get_or_404(db: Session, deployment_id: int) -> Deployment:
    deployment = db.get(Deployment, deployment_id)
    if deployment is None:
        raise HTTPException(status_code=404, detail="部署不存在")
    return deployment


@router.get("", response_model=list[DeploymentOut], summary="部署列表")
def list_deployments(
    status_filter: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[DeploymentOut]:
    stmt = select(Deployment).order_by(Deployment.id.desc())
    if status_filter:
        stmt = stmt.where(Deployment.status == status_filter)
    return [_to_out(db, d) for d in db.scalars(stmt).all()]


@router.post(
    "",
    response_model=DeploymentOut,
    status_code=status.HTTP_201_CREATED,
    summary="创建部署（自动启动）",
)
async def create_deployment(
    payload: DeploymentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DeploymentOut:
    if db.scalar(select(Deployment).where(Deployment.name == payload.name)):
        raise HTTPException(status_code=409, detail=f"部署名 {payload.name} 已存在")
    model = db.get(Model, payload.model_id)
    if model is None:
        raise HTTPException(status_code=404, detail="模型不存在")

    # 引擎默认参数 + 模型推荐参数 + 用户覆盖，逐层合并
    params = dict(orchestrator.get_engine(payload.engine).default_params)
    params.update(model.default_engine_params or {})
    params.update(payload.engine_params or {})

    deployment = Deployment(
        name=payload.name,
        model_id=payload.model_id,
        engine=payload.engine,
        replicas=payload.replicas,
        engine_params=params,
        status=DeploymentStatus.PENDING,
        created_by=user.username,
    )
    db.add(deployment)
    db.commit()
    db.refresh(deployment)

    deployment = await orchestrator.start_deployment(db, deployment)
    return _to_out(db, deployment)


@router.get("/{deployment_id}", response_model=DeploymentDetail, summary="部署详情")
def get_deployment(
    deployment_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)
) -> DeploymentDetail:
    deployment = _get_or_404(db, deployment_id)
    detail = DeploymentDetail.model_validate(deployment)
    detail.model_name = (
        model.display_name if (model := db.get(Model, deployment.model_id)) else ""
    )
    detail.events = [
        DeploymentEventOut.model_validate(e) for e in deployment.events[:50]
    ]
    return detail


@router.patch("/{deployment_id}", response_model=DeploymentOut, summary="更新部署配置")
def update_deployment(
    deployment_id: int,
    payload: DeploymentUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> DeploymentOut:
    deployment = _get_or_404(db, deployment_id)
    data = payload.model_dump(exclude_unset=True)
    if "replicas" in data and data["replicas"] is not None:
        deployment.replicas = data["replicas"]
    if "engine_params" in data and data["engine_params"] is not None:
        deployment.engine_params = {**(deployment.engine_params or {}), **data["engine_params"]}
    orchestrator.record_event(
        db, deployment, "updated", "配置已更新（下次重启生效）"
    )
    db.commit()
    db.refresh(deployment)
    return _to_out(db, deployment)


@router.post("/{deployment_id}/start", response_model=DeploymentOut, summary="启动")
async def start(
    deployment_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)
) -> DeploymentOut:
    deployment = _get_or_404(db, deployment_id)
    try:
        deployment = await orchestrator.start_deployment(db, deployment)
    except (orchestrator.OrchestratorError, EngineError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_out(db, deployment)


@router.post("/{deployment_id}/stop", response_model=DeploymentOut, summary="停止")
async def stop(
    deployment_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)
) -> DeploymentOut:
    deployment = _get_or_404(db, deployment_id)
    deployment = await orchestrator.stop_deployment(db, deployment)
    return _to_out(db, deployment)


@router.post("/{deployment_id}/restart", response_model=DeploymentOut, summary="重启")
async def restart(
    deployment_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)
) -> DeploymentOut:
    deployment = _get_or_404(db, deployment_id)
    deployment = await orchestrator.restart_deployment(db, deployment)
    return _to_out(db, deployment)


@router.delete(
    "/{deployment_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除部署"
)
async def delete(
    deployment_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)
) -> None:
    deployment = _get_or_404(db, deployment_id)
    await orchestrator.delete_deployment(db, deployment)


@router.get(
    "/{deployment_id}/events",
    response_model=list[DeploymentEventOut],
    summary="部署事件时间线",
)
def events(
    deployment_id: int,
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[DeploymentEventOut]:
    _get_or_404(db, deployment_id)
    items = db.scalars(
        select(DeploymentEvent)
        .where(DeploymentEvent.deployment_id == deployment_id)
        .order_by(DeploymentEvent.id.desc())
        .limit(limit)
    ).all()
    return [DeploymentEventOut.model_validate(e) for e in items]


@router.get("/{deployment_id}/health", summary="即时健康检查")
async def health(
    deployment_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)
) -> dict:
    deployment = _get_or_404(db, deployment_id)
    model = db.get(Model, deployment.model_id)
    if model is None:
        raise HTTPException(status_code=404, detail="模型不存在")
    engine = orchestrator.get_engine(deployment.engine)
    try:
        ok = await asyncio.wait_for(
            engine.health(orchestrator.build_context(deployment, model)), timeout=10
        )
    except Exception as exc:  # noqa: BLE001
        return {"healthy": False, "error": str(exc), "status": deployment.status.value}
    return {"healthy": ok, "status": deployment.status.value}
