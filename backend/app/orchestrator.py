"""部署编排器。

职责边界（这是本平台的核心服务层）：
- 端口分配与回收
- 部署状态机流转与事件记录
- 调用引擎适配器完成 start / stop / health
- 推理调用 + 请求日志 + 指标采样
- 后台巡检：把引擎健康状态持续同步回数据库

路由层只负责鉴权和参数校验，所有业务规则集中在这里。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import random
import time
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import SessionLocal
from .engines import (
    EngineContext,
    EngineError,
    get_engine,
    list_engines,
    load_builtin_engines,
)
from .models import (
    Deployment,
    DeploymentEvent,
    DeploymentStatus,
    MetricSample,
    Model,
    RequestLog,
    utcnow,
)
from .engines.base import GenerationResult
from .schemas import ChatRequest, CompletionRequest

logger = logging.getLogger(__name__)


class OrchestratorError(RuntimeError):
    """面向用户的编排错误。"""


# --------------------------------------------------------------------------- #
# 事件与上下文
# --------------------------------------------------------------------------- #
def record_event(
    db: Session,
    deployment: Deployment,
    event: str,
    message: str = "",
    level: str = "info",
) -> DeploymentEvent:
    entry = DeploymentEvent(
        deployment_id=deployment.id, event=event, message=message, level=level
    )
    db.add(entry)
    return entry


def build_context(deployment: Deployment, model: Model) -> EngineContext:
    settings = get_settings()
    if model.source.value == "local":
        model_path = str(settings.models_dir / model.source_ref)
    else:
        model_path = model.source_ref
    return EngineContext(
        deployment_id=deployment.id,
        deployment_name=deployment.name,
        model_name=model.name,
        model_path=model_path,
        engine_params=deployment.engine_params or {},
        host_port=deployment.host_port,
        runtime=deployment.runtime or {},
    )


# --------------------------------------------------------------------------- #
# 端口分配
# --------------------------------------------------------------------------- #
def allocate_port(db: Session) -> int:
    """在配置区间内挑一个未被占用的端口。"""
    settings = get_settings()
    used = {
        row[0]
        for row in db.execute(
            select(Deployment.host_port).where(Deployment.host_port.is_not(None))
        )
        if row[0]
    }
    candidates = list(range(settings.port_range_start, settings.port_range_end + 1))
    random.shuffle(candidates)
    for port in candidates:
        if port not in used:
            return port
    raise OrchestratorError(
        f"端口区间 {settings.port_range_start}-{settings.port_range_end} 已耗尽，"
        "请调整 LLMD_PORT_RANGE_START/END 或清理历史部署。"
    )


# --------------------------------------------------------------------------- #
# 生命周期
# --------------------------------------------------------------------------- #
async def start_deployment(db: Session, deployment: Deployment) -> Deployment:
    """把部署推进到 RUNNING。失败时置为 FAILED 并记录原因。"""
    if deployment.status == DeploymentStatus.RUNNING:
        raise OrchestratorError("部署已在运行中")
    if deployment.status == DeploymentStatus.STARTING:
        raise OrchestratorError("部署正在启动中")

    model = db.get(Model, deployment.model_id)
    if model is None:
        raise OrchestratorError("关联模型不存在")

    if deployment.host_port is None:
        deployment.host_port = allocate_port(db)

    deployment.status = DeploymentStatus.STARTING
    deployment.error_message = None
    deployment.stopped_at = None
    record_event(
        db,
        deployment,
        "start_requested",
        f"使用引擎 {deployment.engine} 启动，端口 {deployment.host_port}",
    )
    db.commit()

    engine = get_engine(deployment.engine)
    ctx = build_context(deployment, model)

    try:
        runtime = await engine.start(ctx)
    except EngineError as exc:
        deployment.status = DeploymentStatus.FAILED
        deployment.error_message = str(exc)
        record_event(db, deployment, "start_failed", str(exc), level="error")
        db.commit()
        db.refresh(deployment)
        return deployment
    except Exception as exc:  # noqa: BLE001 - 兜底，避免后台任务静默死亡
        logger.exception("启动部署 %s 失败", deployment.name)
        deployment.status = DeploymentStatus.FAILED
        deployment.error_message = f"{type(exc).__name__}: {exc}"
        record_event(db, deployment, "start_failed", str(exc), level="error")
        db.commit()
        db.refresh(deployment)
        return deployment

    deployment.runtime = runtime
    deployment.status = DeploymentStatus.RUNNING
    deployment.started_at = utcnow()
    deployment.endpoint = f"http://127.0.0.1:{deployment.host_port}"
    record_event(
        db,
        deployment,
        "started",
        f"实例就绪，推理入口 {deployment.endpoint}/v1/deployments/{deployment.id}",
    )
    db.commit()
    db.refresh(deployment)
    return deployment


async def stop_deployment(db: Session, deployment: Deployment) -> Deployment:
    """停止部署并释放端口，幂等。"""
    if deployment.status in (DeploymentStatus.STOPPED, DeploymentStatus.PENDING):
        if deployment.status == DeploymentStatus.PENDING:
            deployment.status = DeploymentStatus.STOPPED
            deployment.stopped_at = utcnow()
            record_event(db, deployment, "stopped", "尚未启动，直接标记为已停止")
            db.commit()
        return deployment

    deployment.status = DeploymentStatus.STOPPING
    record_event(db, deployment, "stop_requested", "正在停止实例")
    db.commit()

    model = db.get(Model, deployment.model_id)
    engine = get_engine(deployment.engine)
    try:
        if model is not None:
            await engine.stop(build_context(deployment, model))
    except Exception as exc:  # noqa: BLE001
        logger.warning("停止部署 %s 时引擎报错：%s", deployment.name, exc)
        record_event(db, deployment, "stop_warning", f"引擎停止时报错：{exc}", "warning")

    deployment.status = DeploymentStatus.STOPPED
    deployment.stopped_at = utcnow()
    deployment.runtime = {}
    record_event(db, deployment, "stopped", "实例已停止，端口已释放")
    db.commit()
    db.refresh(deployment)
    return deployment


async def delete_deployment(db: Session, deployment: Deployment) -> None:
    """先停后删，避免遗留孤儿进程。"""
    await stop_deployment(db, deployment)
    db.delete(deployment)
    db.commit()


async def restart_deployment(db: Session, deployment: Deployment) -> Deployment:
    await stop_deployment(db, deployment)
    deployment.host_port = None
    db.commit()
    return await start_deployment(db, deployment)


# --------------------------------------------------------------------------- #
# 推理
# --------------------------------------------------------------------------- #
async def _load_running(
    db: Session, deployment_id: int
) -> tuple[Deployment, Model, EngineContext]:
    deployment = db.get(Deployment, deployment_id)
    if deployment is None:
        raise OrchestratorError(f"部署 {deployment_id} 不存在")
    if deployment.status != DeploymentStatus.RUNNING:
        raise OrchestratorError(
            f"部署 {deployment.name} 当前状态为 {deployment.status.value}，无法推理"
        )
    model = db.get(Model, deployment.model_id)
    if model is None:
        raise OrchestratorError("关联模型不存在")
    return deployment, model, build_context(deployment, model)


def _summarize(request) -> str:
    if isinstance(request, ChatRequest):
        last = next(
            (m.content for m in reversed(request.messages) if m.role == "user"), ""
        )
    else:
        last = request.prompt
    return last[:200]


def _write_request_log(
    db: Session,
    deployment: Deployment,
    request_id: str,
    request,
    *,
    status: str,
    latency_ms: float,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    error: str | None = None,
    api_key_id: int | None = None,
) -> None:
    db.add(
        RequestLog(
            deployment_id=deployment.id,
            request_id=request_id,
            api_key_id=api_key_id,
            prompt_preview=_summarize(request),
            stream=bool(getattr(request, "stream", False)),
            status=status,
            error=error,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
        )
    )
    db.commit()


async def run_completion(
    db: Session,
    deployment_id: int,
    request: CompletionRequest | ChatRequest,
    api_key_id: int | None = None,
) -> tuple[GenerationResult, str, float]:
    """执行一次非流式推理，返回 (结果, 请求ID, 耗时毫秒)。"""
    deployment, model, ctx = await _load_running(db, deployment_id)
    engine = get_engine(deployment.engine)
    request_id = f"cmpl-{uuid.uuid4().hex[:24]}"
    started = time.perf_counter()

    try:
        result = await engine.complete(ctx, request)
    except Exception as exc:  # noqa: BLE001
        latency = (time.perf_counter() - started) * 1000
        _write_request_log(
            db,
            deployment,
            request_id,
            request,
            status="failed",
            latency_ms=latency,
            error=str(exc),
            api_key_id=api_key_id,
        )
        raise OrchestratorError(f"推理失败：{exc}") from exc

    latency = (time.perf_counter() - started) * 1000
    _write_request_log(
        db,
        deployment,
        request_id,
        request,
        status="success",
        latency_ms=latency,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        api_key_id=api_key_id,
    )
    return result, request_id, latency


async def stream_completion(
    db: Session,
    deployment_id: int,
    request: CompletionRequest | ChatRequest,
    api_key_id: int | None = None,
    request_id: str | None = None,
):
    """流式推理。产出原始文本增量；结束时落请求日志。

    调用方（路由层）负责把增量包装成自己的协议格式：
    控制台用自定义 SSE 事件，/v1 用 OpenAI 的 chunk 格式。
    """
    deployment, model, ctx = await _load_running(db, deployment_id)
    engine = get_engine(deployment.engine)
    request_id = request_id or f"cmpl-{uuid.uuid4().hex[:24]}"
    started = time.perf_counter()
    chunks: list[str] = []
    error: str | None = None

    try:
        async for chunk in engine.stream(ctx, request):
            chunks.append(chunk)
            yield chunk
    except Exception as exc:  # noqa: BLE001
        error = str(exc)
        logger.warning("流式推理失败 %s: %s", deployment.name, exc)
    finally:
        latency = (time.perf_counter() - started) * 1000
        text = "".join(chunks)
        _write_request_log(
            db,
            deployment,
            request_id,
            request,
            status="failed" if error else "success",
            latency_ms=latency,
            completion_tokens=max(1, len(text) // 3) if text else 0,
            error=error,
            api_key_id=api_key_id,
        )


# --------------------------------------------------------------------------- #
# 指标
# --------------------------------------------------------------------------- #
async def collect_metrics_once(db: Session, deployment: Deployment) -> MetricSample | None:
    """采样一次并落库。非 RUNNING 状态跳过。"""
    if deployment.status != DeploymentStatus.RUNNING:
        return None
    model = db.get(Model, deployment.model_id)
    if model is None:
        return None

    engine = get_engine(deployment.engine)
    try:
        snapshot = await engine.metrics(build_context(deployment, model))
    except Exception as exc:  # noqa: BLE001
        logger.debug("采集 %s 指标失败：%s", deployment.name, exc)
        return None

    settings = get_settings()
    # 累计计数以请求日志为准，避免依赖引擎实现是否完整
    totals = db.execute(
        select(
            func.count(RequestLog.id),
            func.coalesce(
                func.sum(case((RequestLog.status != "success", 1), else_=0)), 0
            ),
        ).where(RequestLog.deployment_id == deployment.id)
    ).one()
    total_requests = int(totals[0] or 0)
    failed_requests = int(totals[1] or 0)

    recent = db.scalars(
        select(RequestLog)
        .where(RequestLog.deployment_id == deployment.id)
        .order_by(RequestLog.id.desc())
        .limit(100)
    ).all()
    latencies = sorted(log.latency_ms for log in recent)
    p50 = latencies[len(latencies) // 2] if latencies else 0.0
    p95 = latencies[min(int(len(latencies) * 0.95), len(latencies) - 1)] if latencies else 0.0

    window_start = datetime.now(timezone.utc) - timedelta(seconds=30)
    window_count = db.scalar(
        select(func.count(RequestLog.id)).where(
            RequestLog.deployment_id == deployment.id,
            RequestLog.created_at >= window_start,
        )
    )
    qps = (window_count or 0) / 30.0

    sample = MetricSample(
        deployment_id=deployment.id,
        qps=snapshot.qps or qps,
        tokens_per_second=snapshot.tokens_per_second,
        latency_p50_ms=snapshot.latency_p50_ms or p50,
        latency_p95_ms=snapshot.latency_p95_ms or p95,
        gpu_utilization=snapshot.gpu_utilization,
        gpu_memory_used_mb=snapshot.gpu_memory_used_mb,
        gpu_memory_total_mb=snapshot.gpu_memory_total_mb,
        total_requests=total_requests or snapshot.total_requests,
        failed_requests=failed_requests,
        running_requests=snapshot.running_requests,
        queue_depth=snapshot.queue_depth,
    )
    db.add(sample)
    db.commit()

    _prune_metrics(db, deployment.id, settings.metrics_retention_points)
    return sample


def _prune_metrics(db: Session, deployment_id: int, keep: int) -> None:
    """只保留最近 keep 个采样点，防止 SQLite 无限增长。"""
    cutoff_id = db.scalar(
        select(MetricSample.id)
        .where(MetricSample.deployment_id == deployment_id)
        .order_by(MetricSample.id.desc())
        .offset(keep)
        .limit(1)
    )
    if cutoff_id is not None:
        db.query(MetricSample).filter(
            MetricSample.deployment_id == deployment_id,
            MetricSample.id <= cutoff_id,
        ).delete(synchronize_session=False)
        db.commit()


# --------------------------------------------------------------------------- #
# 后台巡检
# --------------------------------------------------------------------------- #
class HealthMonitor:
    """周期性同步引擎健康状态并采集指标。"""

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    async def _tick(self) -> None:
        settings = get_settings()
        db = SessionLocal()
        try:
            running = db.scalars(
                select(Deployment).where(Deployment.status == DeploymentStatus.RUNNING)
            ).all()
            for deployment in running:
                model = db.get(Model, deployment.model_id)
                if model is None:
                    continue
                engine = get_engine(deployment.engine)
                try:
                    healthy = await engine.health(build_context(deployment, model))
                except Exception as exc:  # noqa: BLE001
                    logger.debug("健康检查 %s 异常：%s", deployment.name, exc)
                    healthy = False

                if not healthy:
                    deployment.status = DeploymentStatus.FAILED
                    deployment.error_message = "健康检查连续失败，实例可能已崩溃"
                    record_event(
                        db,
                        deployment,
                        "unhealthy",
                        "健康检查失败，已标记为 FAILED",
                        level="error",
                    )
                    db.commit()
                    continue

                try:
                    await collect_metrics_once(db, deployment)
                except Exception as exc:  # noqa: BLE001
                    logger.debug("采集 %s 指标异常：%s", deployment.name, exc)
        finally:
            db.close()
        _ = settings

    async def _loop(self) -> None:
        settings = get_settings()
        while not self._stop.is_set():
            try:
                await self._tick()
            except Exception:  # noqa: BLE001
                logger.exception("健康巡检轮次失败")
            try:
                await asyncio.wait_for(
                    self._stop.wait(), timeout=settings.health_check_interval_seconds
                )
            except asyncio.TimeoutError:
                continue

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stop.clear()
            self._task = asyncio.create_task(self._loop(), name="llmd-health-monitor")

    async def shutdown(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None


monitor = HealthMonitor()


async def shutdown_all_engines() -> None:
    """进程退出时回收所有由本进程拉起的引擎实例。"""
    db = SessionLocal()
    try:
        active = db.scalars(
            select(Deployment).where(
                Deployment.status.in_(
                    [DeploymentStatus.RUNNING, DeploymentStatus.STARTING]
                )
            )
        ).all()
        for deployment in active:
            model = db.get(Model, deployment.model_id)
            if model is None:
                continue
            try:
                await get_engine(deployment.engine).stop(build_context(deployment, model))
                deployment.status = DeploymentStatus.STOPPED
                deployment.stopped_at = utcnow()
            except Exception as exc:  # noqa: BLE001
                logger.warning("退出时停止 %s 失败：%s", deployment.name, exc)
        db.commit()
    finally:
        db.close()


def engine_catalog() -> list[dict]:
    load_builtin_engines()
    return [engine.info() for engine in list_engines()]
