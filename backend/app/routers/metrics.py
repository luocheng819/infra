"""监控指标与请求日志路由。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Deployment, MetricSample, RequestLog, User
from ..schemas import MetricSampleOut, MetricsSummary, RequestLogOut
from ..security import get_current_user

router = APIRouter(prefix="/api", tags=["监控与日志"])


def _require_deployment(db: Session, deployment_id: int) -> Deployment:
    deployment = db.get(Deployment, deployment_id)
    if deployment is None:
        raise HTTPException(status_code=404, detail="部署不存在")
    return deployment


@router.get(
    "/deployments/{deployment_id}/metrics",
    response_model=MetricsSummary,
    summary="部署指标时序",
)
def get_metrics(
    deployment_id: int,
    minutes: int = Query(default=30, ge=1, le=1440),
    limit: int = Query(default=240, ge=10, le=2000),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> MetricsSummary:
    _require_deployment(db, deployment_id)
    since = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    rows = db.scalars(
        select(MetricSample)
        .where(
            MetricSample.deployment_id == deployment_id,
            MetricSample.timestamp >= since,
        )
        .order_by(MetricSample.id.desc())
        .limit(limit)
    ).all()
    samples = [MetricSampleOut.model_validate(s) for s in reversed(rows)]
    return MetricsSummary(
        deployment_id=deployment_id,
        current=samples[-1] if samples else None,
        samples=samples,
    )


@router.get(
    "/deployments/{deployment_id}/logs",
    response_model=list[RequestLogOut],
    summary="部署请求日志",
)
def get_logs(
    deployment_id: int,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[RequestLogOut]:
    _require_deployment(db, deployment_id)
    stmt = (
        select(RequestLog)
        .where(RequestLog.deployment_id == deployment_id)
        .order_by(RequestLog.id.desc())
        .limit(limit)
        .offset(offset)
    )
    if status_filter:
        stmt = stmt.where(RequestLog.status == status_filter)
    return [RequestLogOut.model_validate(r) for r in db.scalars(stmt).all()]


@router.get("/logs", response_model=list[RequestLogOut], summary="全局请求日志")
def all_logs(
    deployment_id: int | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[RequestLogOut]:
    stmt = select(RequestLog).order_by(RequestLog.id.desc()).limit(limit)
    if deployment_id is not None:
        stmt = stmt.where(RequestLog.deployment_id == deployment_id)
    if status_filter:
        stmt = stmt.where(RequestLog.status == status_filter)
    return [RequestLogOut.model_validate(r) for r in db.scalars(stmt).all()]


@router.get("/metrics/summary", summary="全局指标概览")
def metrics_summary(
    db: Session = Depends(get_db), _: User = Depends(get_current_user)
) -> dict:
    since = datetime.now(timezone.utc) - timedelta(hours=1)
    totals = db.execute(
        select(
            func.count(RequestLog.id),
            func.coalesce(
                func.sum(case((RequestLog.status != "success", 1), else_=0)), 0
            ),
            func.coalesce(func.avg(RequestLog.latency_ms), 0.0),
        )
    ).one()
    recent = db.execute(
        select(
            func.count(RequestLog.id),
            func.coalesce(
                func.sum(case((RequestLog.status != "success", 1), else_=0)), 0
            ),
        ).where(RequestLog.created_at >= since)
    ).one()

    per_deployment = db.execute(
        select(
            Deployment.id,
            Deployment.name,
            func.count(RequestLog.id),
            func.coalesce(
                func.sum(case((RequestLog.status != "success", 1), else_=0)), 0
            ),
            func.coalesce(func.avg(RequestLog.latency_ms), 0.0),
        )
        .outerjoin(RequestLog, RequestLog.deployment_id == Deployment.id)
        .group_by(Deployment.id)
        .order_by(func.count(RequestLog.id).desc())
        .limit(10)
    ).all()

    return {
        "total_requests": int(totals[0] or 0),
        "failed_requests": int(totals[1] or 0),
        "avg_latency_ms": round(float(totals[2] or 0.0), 2),
        "requests_last_hour": int(recent[0] or 0),
        "failures_last_hour": int(recent[1] or 0),
        "top_deployments": [
            {
                "deployment_id": row[0],
                "name": row[1],
                "requests": int(row[2] or 0),
                "failed": int(row[3] or 0),
                "avg_latency_ms": round(float(row[4] or 0.0), 2),
            }
            for row in per_deployment
        ],
    }
