"""领域模型。

设计要点：
- ``Model`` 是模型仓库里的一份权重/制品登记，可被多次部署。
- ``Deployment`` 是一个模型实例的生命周期载体，指向某个引擎适配器。
- ``DeploymentEvent`` / ``RequestLog`` 是审计与可观测性的基础数据。
- ``MetricSample`` 存引擎上报的时间序列采样点。
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ModelSource(str, enum.Enum):
    """模型来源类型。"""

    LOCAL = "local"  # 本地上传/放置的目录
    HUGGINGFACE = "huggingface"  # HF 仓库 ID
    MODELSCOPE = "modelscope"  # 魔搭仓库 ID


class DeploymentStatus(str, enum.Enum):
    """部署状态机：

    PENDING -> STARTING -> RUNNING -> STOPPING -> STOPPED
                   \\-> FAILED <-/
    """

    PENDING = "pending"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


TERMINAL_STATUSES = {DeploymentStatus.STOPPED, DeploymentStatus.FAILED}


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255), default=None)
    hashed_password: Mapped[str] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Model(Base):
    __tablename__ = "models"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[ModelSource] = mapped_column(
        Enum(ModelSource), default=ModelSource.HUGGINGFACE
    )
    # 对于 LOCAL 是相对 models_dir 的目录名；对于远程是仓库 ID
    source_ref: Mapped[str] = mapped_column(String(512))
    revision: Mapped[str] = mapped_column(String(128), default="main")
    parameter_count: Mapped[str | None] = mapped_column(String(32), default=None)
    quantization: Mapped[str | None] = mapped_column(String(32), default=None)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    # 该模型推荐的引擎默认参数
    default_engine_params: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    deployments: Mapped[list[Deployment]] = relationship(
        back_populates="model", cascade="all, delete-orphan"
    )


class Deployment(Base):
    __tablename__ = "deployments"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("models.id", ondelete="CASCADE"))
    engine: Mapped[str] = mapped_column(String(32), default="mock")
    status: Mapped[DeploymentStatus] = mapped_column(
        Enum(DeploymentStatus), default=DeploymentStatus.PENDING
    )
    replicas: Mapped[int] = mapped_column(Integer, default=1)
    host_port: Mapped[int | None] = mapped_column(Integer, default=None)
    endpoint: Mapped[str | None] = mapped_column(String(255), default=None)
    # 引擎参数：temperature / max_tokens / gpu_memory_utilization ...
    engine_params: Mapped[dict] = mapped_column(JSON, default=dict)
    # 引擎适配器启动后回填的运行时句柄（进程 pid、外部 URL 等）
    runtime: Mapped[dict] = mapped_column(JSON, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, default=None)
    created_by: Mapped[str | None] = mapped_column(String(64), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    stopped_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    model: Mapped[Model] = relationship(back_populates="deployments")
    events: Mapped[list[DeploymentEvent]] = relationship(
        back_populates="deployment",
        cascade="all, delete-orphan",
        order_by="DeploymentEvent.id.desc()",
    )


class DeploymentEvent(Base):
    """部署生命周期事件，用于审计与前端时间线。"""

    __tablename__ = "deployment_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    deployment_id: Mapped[int] = mapped_column(
        ForeignKey("deployments.id", ondelete="CASCADE"), index=True
    )
    level: Mapped[str] = mapped_column(String(16), default="info")
    event: Mapped[str] = mapped_column(String(64))
    message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    deployment: Mapped[Deployment] = relationship(back_populates="events")


class MetricSample(Base):
    """引擎上报的时间序列采样点。"""

    __tablename__ = "metric_samples"

    id: Mapped[int] = mapped_column(primary_key=True)
    deployment_id: Mapped[int] = mapped_column(
        ForeignKey("deployments.id", ondelete="CASCADE"), index=True
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    # 吞吐
    qps: Mapped[float] = mapped_column(Float, default=0.0)
    tokens_per_second: Mapped[float] = mapped_column(Float, default=0.0)
    # 延迟（毫秒）
    latency_p50_ms: Mapped[float] = mapped_column(Float, default=0.0)
    latency_p95_ms: Mapped[float] = mapped_column(Float, default=0.0)
    # 资源
    gpu_utilization: Mapped[float] = mapped_column(Float, default=0.0)
    gpu_memory_used_mb: Mapped[float] = mapped_column(Float, default=0.0)
    gpu_memory_total_mb: Mapped[float] = mapped_column(Float, default=0.0)
    # 累计计数
    total_requests: Mapped[int] = mapped_column(Integer, default=0)
    failed_requests: Mapped[int] = mapped_column(Integer, default=0)
    running_requests: Mapped[int] = mapped_column(Integer, default=0)
    # 队列
    queue_depth: Mapped[int] = mapped_column(Integer, default=0)


class RequestLog(Base):
    """一次推理调用的记录。"""

    __tablename__ = "request_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    deployment_id: Mapped[int] = mapped_column(
        ForeignKey("deployments.id", ondelete="CASCADE"), index=True
    )
    request_id: Mapped[str] = mapped_column(String(64), index=True)
    api_key_id: Mapped[int | None] = mapped_column(
        ForeignKey("api_keys.id", ondelete="SET NULL"), default=None
    )
    prompt_preview: Mapped[str] = mapped_column(Text, default="")
    stream: Mapped[bool] = mapped_column(default=False)
    status: Mapped[str] = mapped_column(String(16), default="success")
    error: Mapped[str | None] = mapped_column(Text, default=None)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


class ApiKey(Base):
    """调用推理接口用的 API Key（与平台登录态分离）。"""

    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    prefix: Mapped[str] = mapped_column(String(16), index=True)
    hashed_key: Mapped[str] = mapped_column(String(128))
    owner: Mapped[str] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(default=True)
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
