"""API 出入参模型。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .models import DeploymentStatus, ModelSource


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --------------------------------------------------------------------------- #
# 认证
# --------------------------------------------------------------------------- #
class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: "UserOut"


class UserOut(ORMModel):
    id: int
    username: str
    email: str | None = None
    is_admin: bool
    created_at: datetime


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    email: str | None = None
    is_admin: bool = False


# --------------------------------------------------------------------------- #
# 模型仓库
# --------------------------------------------------------------------------- #
class ModelBase(BaseModel):
    display_name: str = Field(min_length=1, max_length=255)
    description: str = ""
    source: ModelSource = ModelSource.HUGGINGFACE
    source_ref: str = Field(min_length=1, max_length=512)
    revision: str = "main"
    parameter_count: str | None = None
    quantization: str | None = None
    size_bytes: int = 0
    tags: list[str] = Field(default_factory=list)
    default_engine_params: dict = Field(default_factory=dict)


class ModelCreate(ModelBase):
    name: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9._-]+$")


class ModelUpdate(BaseModel):
    display_name: str | None = None
    description: str | None = None
    revision: str | None = None
    parameter_count: str | None = None
    quantization: str | None = None
    tags: list[str] | None = None
    default_engine_params: dict | None = None


class ModelOut(ORMModel, ModelBase):
    id: int
    name: str
    created_at: datetime
    updated_at: datetime
    deployment_count: int = 0


# --------------------------------------------------------------------------- #
# 部署
# --------------------------------------------------------------------------- #
class DeploymentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9._-]+$")
    model_id: int
    engine: str = "mock"
    replicas: int = Field(default=1, ge=1, le=8)
    engine_params: dict = Field(default_factory=dict)


class DeploymentUpdate(BaseModel):
    replicas: int | None = Field(default=None, ge=1, le=8)
    engine_params: dict | None = None


class DeploymentEventOut(ORMModel):
    id: int
    level: str
    event: str
    message: str
    created_at: datetime


class DeploymentOut(ORMModel):
    id: int
    name: str
    model_id: int
    model_name: str = ""
    engine: str
    status: DeploymentStatus
    replicas: int
    host_port: int | None
    endpoint: str | None
    engine_params: dict
    runtime: dict
    error_message: str | None
    created_by: str | None
    created_at: datetime
    started_at: datetime | None
    stopped_at: datetime | None


class DeploymentDetail(DeploymentOut):
    events: list[DeploymentEventOut] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# 推理
# --------------------------------------------------------------------------- #
class ChatMessage(BaseModel):
    role: str = Field(pattern=r"^(system|user|assistant)$")
    content: str


class CompletionRequest(BaseModel):
    prompt: str = Field(min_length=1)
    max_tokens: int = Field(default=256, ge=1, le=8192)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    top_p: float = Field(default=1.0, ge=0.0, le=1.0)
    stream: bool = False


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1)
    max_tokens: int = Field(default=512, ge=1, le=8192)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    top_p: float = Field(default=1.0, ge=0.0, le=1.0)
    stream: bool = False


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class CompletionResponse(BaseModel):
    id: str
    deployment: str
    model: str
    text: str
    finish_reason: str = "stop"
    usage: Usage
    latency_ms: float


class ChatChoice(BaseModel):
    index: int = 0
    message: ChatMessage
    finish_reason: str = "stop"


class ChatResponse(BaseModel):
    id: str
    deployment: str
    model: str
    choices: list[ChatChoice]
    usage: Usage
    latency_ms: float


# --------------------------------------------------------------------------- #
# OpenAI 兼容请求体：比控制台请求多一个 model 字段（值即部署名）
# --------------------------------------------------------------------------- #
class OpenAIChatRequest(ChatRequest):
    model: str | None = None
    user: str | None = None


class OpenAICompletionRequest(CompletionRequest):
    model: str | None = None
    user: str | None = None


# --------------------------------------------------------------------------- #
# 指标
# --------------------------------------------------------------------------- #
class MetricSampleOut(ORMModel):
    timestamp: datetime
    qps: float
    tokens_per_second: float
    latency_p50_ms: float
    latency_p95_ms: float
    gpu_utilization: float
    gpu_memory_used_mb: float
    gpu_memory_total_mb: float
    total_requests: int
    failed_requests: int
    running_requests: int
    queue_depth: int


class MetricsSummary(BaseModel):
    deployment_id: int
    current: MetricSampleOut | None = None
    samples: list[MetricSampleOut] = Field(default_factory=list)


class RequestLogOut(ORMModel):
    id: int
    deployment_id: int
    request_id: str
    prompt_preview: str
    stream: bool
    status: str
    error: str | None
    prompt_tokens: int
    completion_tokens: int
    latency_ms: float
    created_at: datetime


# --------------------------------------------------------------------------- #
# API Key
# --------------------------------------------------------------------------- #
class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)


class ApiKeyOut(ORMModel):
    id: int
    name: str
    prefix: str
    owner: str
    is_active: bool
    last_used_at: datetime | None
    created_at: datetime


class ApiKeyCreated(ApiKeyOut):
    #: 明文密钥，仅在创建响应中出现一次
    key: str = ""


# --------------------------------------------------------------------------- #
# 总览
# --------------------------------------------------------------------------- #
class OverviewStats(BaseModel):
    total_models: int
    total_deployments: int
    running_deployments: int
    failed_deployments: int
    total_requests: int
    requests_last_hour: int
    failure_rate: float
    avg_latency_ms: float
    total_tokens: int
    engines: list[str]


class EngineInfo(BaseModel):
    name: str
    display_name: str
    description: str
    available: bool
    requires_gpu: bool = False
    default_params: dict = Field(default_factory=dict)
    #: 前端据此动态渲染部署参数表单
    param_schema: list[dict] = Field(default_factory=list)


TokenResponse.model_rebuild()
