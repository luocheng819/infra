"""推理引擎抽象。

这一层是整个平台的「深模块」：编排器只认识 ``InferenceEngine`` 这组方法，
不关心背后是 Mock、vLLM、Ollama 还是任意 OpenAI 兼容服务。

新增一个引擎 = 实现该接口 + 用 ``@register_engine`` 注册，无需改动上游代码。
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import AsyncIterator, ClassVar


@dataclass
class EngineContext:
    """一次引擎调用所需的全部上下文，由编排器构造。"""

    deployment_id: int
    deployment_name: str
    model_name: str
    # 模型制品的实际位置（本地目录），远程来源由引擎自行解析
    model_path: str
    engine_params: dict = field(default_factory=dict)
    host_port: int | None = None
    # start() 返回的运行时句柄，后续调用原样带回
    runtime: dict = field(default_factory=dict)

    def param(self, key: str, default=None):
        return self.engine_params.get(key, default)


@dataclass
class GenerationResult:
    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    finish_reason: str = "stop"


@dataclass
class EngineMetrics:
    """引擎自报的运行指标快照。"""

    qps: float = 0.0
    tokens_per_second: float = 0.0
    latency_p50_ms: float = 0.0
    latency_p95_ms: float = 0.0
    gpu_utilization: float = 0.0
    gpu_memory_used_mb: float = 0.0
    gpu_memory_total_mb: float = 0.0
    total_requests: int = 0
    failed_requests: int = 0
    running_requests: int = 0
    queue_depth: int = 0


class EngineError(RuntimeError):
    """引擎启动或推理失败。"""


class InferenceEngine(abc.ABC):
    """推理引擎适配器接口。"""

    name: ClassVar[str] = ""
    display_name: ClassVar[str] = ""
    description: ClassVar[str] = ""
    requires_gpu: ClassVar[bool] = False
    #: 该引擎暴露给用户的默认可调参数
    default_params: ClassVar[dict] = {}
    #: 该引擎的参数说明，前端据此渲染表单
    param_schema: ClassVar[list[dict]] = []

    # ------------------------------------------------------------------ #
    # 生命周期
    # ------------------------------------------------------------------ #
    @abc.abstractmethod
    async def start(self, ctx: EngineContext) -> dict:
        """启动实例，返回运行时句柄（会被持久化到 Deployment.runtime）。"""

    @abc.abstractmethod
    async def stop(self, ctx: EngineContext) -> None:
        """停止实例，幂等。"""

    @abc.abstractmethod
    async def health(self, ctx: EngineContext) -> bool:
        """健康检查。"""

    # ------------------------------------------------------------------ #
    # 推理
    # ------------------------------------------------------------------ #
    @abc.abstractmethod
    async def complete(self, ctx: EngineContext, request) -> GenerationResult:
        """非流式生成。request 为 schemas.CompletionRequest 或 ChatRequest。"""

    @abc.abstractmethod
    def stream(self, ctx: EngineContext, request) -> AsyncIterator[str]:
        """流式生成，逐个产出增量文本。"""

    # ------------------------------------------------------------------ #
    # 可观测性
    # ------------------------------------------------------------------ #
    @abc.abstractmethod
    async def metrics(self, ctx: EngineContext) -> EngineMetrics:
        """上报当前指标快照。"""

    # ------------------------------------------------------------------ #
    def info(self) -> dict:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "available": True,
            "requires_gpu": self.requires_gpu,
            "default_params": dict(self.default_params),
            "param_schema": list(self.param_schema),
        }
