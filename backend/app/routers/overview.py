"""总览与引擎目录路由。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from .. import orchestrator
from ..db import get_db
from ..models import Deployment, DeploymentStatus, Model, RequestLog, User
from ..schemas import EngineInfo, OverviewStats
from ..security import get_current_user

router = APIRouter(prefix="/api", tags=["总览"])


@router.get("/overview", response_model=OverviewStats, summary="平台总览统计")
def overview(
    db: Session = Depends(get_db), _: User = Depends(get_current_user)
) -> OverviewStats:
    total_models = db.scalar(select(func.count(Model.id))) or 0
    status_counts = dict(
        db.execute(
            select(Deployment.status, func.count(Deployment.id)).group_by(Deployment.status)
        ).all()
    )
    total_deployments = sum(status_counts.values())

    totals = db.execute(
        select(
            func.count(RequestLog.id),
            func.coalesce(
                func.sum(
                    case(
                        (
                            RequestLog.status != "success",
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
            func.coalesce(func.avg(RequestLog.latency_ms), 0.0),
            func.coalesce(
                func.sum(RequestLog.prompt_tokens + RequestLog.completion_tokens), 0
            ),
        )
    ).one()

    since = datetime.now(timezone.utc) - timedelta(hours=1)
    last_hour = db.scalar(
        select(func.count(RequestLog.id)).where(RequestLog.created_at >= since)
    ) or 0

    total_requests = int(totals[0] or 0)
    failed = int(totals[1] or 0)

    return OverviewStats(
        total_models=int(total_models),
        total_deployments=total_deployments,
        running_deployments=int(status_counts.get(DeploymentStatus.RUNNING, 0)),
        failed_deployments=int(status_counts.get(DeploymentStatus.FAILED, 0)),
        total_requests=total_requests,
        requests_last_hour=int(last_hour),
        failure_rate=round(failed / total_requests, 4) if total_requests else 0.0,
        avg_latency_ms=round(float(totals[2] or 0.0), 2),
        total_tokens=int(totals[3] or 0),
        engines=[info["name"] for info in orchestrator.engine_catalog()],
    )


@router.get("/engines", response_model=list[EngineInfo], summary="可用推理引擎")
def engines(_: User = Depends(get_current_user)) -> list[EngineInfo]:
    return [EngineInfo(**info) for info in orchestrator.engine_catalog()]
