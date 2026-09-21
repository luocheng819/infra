"""模型仓库路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Deployment, Model, User
from ..schemas import ModelCreate, ModelOut, ModelUpdate
from ..security import get_current_user

router = APIRouter(prefix="/api/models", tags=["模型仓库"])


def _to_out(db: Session, model: Model) -> ModelOut:
    count = db.scalar(
        select(func.count(Deployment.id)).where(Deployment.model_id == model.id)
    )
    out = ModelOut.model_validate(model)
    out.deployment_count = int(count or 0)
    return out


@router.get("", response_model=list[ModelOut], summary="模型列表")
def list_models(
    q: str | None = Query(default=None, description="按名称/描述模糊搜索"),
    source: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[ModelOut]:
    stmt = select(Model).order_by(Model.id.desc())
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(Model.name.ilike(like), Model.display_name.ilike(like), Model.description.ilike(like))
        )
    if source:
        stmt = stmt.where(Model.source == source)
    models = db.scalars(stmt).all()
    return [_to_out(db, m) for m in models]


@router.post(
    "", response_model=ModelOut, status_code=status.HTTP_201_CREATED, summary="登记模型"
)
def create_model(
    payload: ModelCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ModelOut:
    if db.scalar(select(Model).where(Model.name == payload.name)):
        raise HTTPException(status_code=409, detail=f"模型名 {payload.name} 已存在")
    model = Model(**payload.model_dump())
    db.add(model)
    db.commit()
    db.refresh(model)
    _ = user
    return _to_out(db, model)


@router.get("/{model_id}", response_model=ModelOut, summary="模型详情")
def get_model(
    model_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)
) -> ModelOut:
    model = db.get(Model, model_id)
    if model is None:
        raise HTTPException(status_code=404, detail="模型不存在")
    return _to_out(db, model)


@router.patch("/{model_id}", response_model=ModelOut, summary="更新模型")
def update_model(
    model_id: int,
    payload: ModelUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> ModelOut:
    model = db.get(Model, model_id)
    if model is None:
        raise HTTPException(status_code=404, detail="模型不存在")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(model, field, value)
    db.commit()
    db.refresh(model)
    return _to_out(db, model)


@router.delete(
    "/{model_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除模型"
)
def delete_model(
    model_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)
) -> None:
    model = db.get(Model, model_id)
    if model is None:
        raise HTTPException(status_code=404, detail="模型不存在")
    active = db.scalar(
        select(func.count(Deployment.id)).where(
            Deployment.model_id == model_id,
            Deployment.status.in_(["running", "starting"]),
        )
    )
    if active:
        raise HTTPException(
            status_code=409, detail="该模型仍有运行中的部署，请先停止后再删除"
        )
    db.delete(model)
    db.commit()
