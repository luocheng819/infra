"""vLLM 引擎：把 ``vllm serve`` 作为子进程拉起，再复用 OpenAI 兼容客户端做推理。

这是「真实引擎」的落地示例：启动/停止负责进程生命周期，推理侧完全复用
``OpenAIChatClient``，因此指标、流式、计量逻辑与 ``openai`` 引擎一致。

本机未安装 vLLM 时该引擎标记为不可用，但代码路径完整保留；
装了 vLLM 的机器无需改任何代码即可直接部署。
"""

from __future__ import annotations

import asyncio
import os
import shutil
import signal
import time
from pathlib import Path
from typing import AsyncIterator

import httpx

from ..config import get_settings
from ..schemas import ChatRequest, CompletionRequest
from .base import (
    EngineContext,
    EngineError,
    EngineMetrics,
    GenerationResult,
    InferenceEngine,
)
from .openai_compat import OpenAIChatClient, collect_upstream_metrics
from . import register_engine


@register_engine
class VLLMEngine(InferenceEngine):
    name = "vllm"
    display_name = "vLLM"
    description = (
        "在生产级推理服务 vLLM 上启动模型实例。启动时执行 vllm serve，"
        "就绪后通过 OpenAI 兼容接口提供推理，并解析其 Prometheus 指标。"
    )
    requires_gpu = True
    default_params = {
        "tensor_parallel_size": 1,
        "gpu_memory_utilization": 0.9,
        "max_model_len": 8192,
        "dtype": "auto",
        "quantization": "",
        "trust_remote_code": False,
        "max_tokens": 512,
        "temperature": 0.7,
        "served_model_name": "",
    }
    param_schema = [
        {
            "key": "tensor_parallel_size",
            "label": "张量并行度 (TP)",
            "type": "int",
            "default": 1,
            "min": 1,
            "max": 16,
            "help": "需要等于所用 GPU 数量",
        },
        {
            "key": "gpu_memory_utilization",
            "label": "显存占用比例",
            "type": "float",
            "default": 0.9,
            "min": 0.1,
            "max": 1.0,
            "step": 0.05,
        },
        {
            "key": "max_model_len",
            "label": "最大上下文长度",
            "type": "int",
            "default": 8192,
            "min": 128,
            "max": 1048576,
            "help": "留空或 0 表示使用模型默认值",
        },
        {
            "key": "dtype",
            "label": "权重精度",
            "type": "select",
            "default": "auto",
            "options": ["auto", "float16", "bfloat16", "float32"],
        },
        {
            "key": "quantization",
            "label": "量化方式",
            "type": "select",
            "default": "",
            "options": ["", "awq", "gptq", "fp8", "squeezellm"],
        },
        {
            "key": "trust_remote_code",
            "label": "信任远程代码",
            "type": "bool",
            "default": False,
        },
        {
            "key": "served_model_name",
            "label": "对外模型名",
            "type": "string",
            "default": "",
            "help": "留空则使用平台登记的模型名",
        },
    ]

    _procs: dict[int, asyncio.subprocess.Process] = {}
    _clients: dict[int, OpenAIChatClient] = {}

    # ------------------------------------------------------------------ #
    @classmethod
    def available(cls) -> bool:
        return shutil.which("vllm") is not None

    def info(self) -> dict:
        info = super().info()
        info["available"] = self.available()
        if not info["available"]:
            info["description"] += "（当前环境未检测到 vllm 可执行文件）"
        return info

    # ------------------------------------------------------------------ #
    def _log_path(self, ctx: EngineContext) -> Path:
        settings = get_settings()
        return settings.logs_dir / f"deployment-{ctx.deployment_id}.log"

    def _build_command(self, ctx: EngineContext) -> list[str]:
        params = ctx.engine_params or {}
        cmd = ["vllm", "serve", ctx.model_path, "--port", str(ctx.host_port)]

        tp = int(params.get("tensor_parallel_size") or 1)
        if tp > 1:
            cmd += ["--tensor-parallel-size", str(tp)]
        if params.get("gpu_memory_utilization") is not None:
            cmd += ["--gpu-memory-utilization", str(params["gpu_memory_utilization"])]
        if params.get("max_model_len"):
            cmd += ["--max-model-len", str(params["max_model_len"])]
        if params.get("dtype"):
            cmd += ["--dtype", str(params["dtype"])]
        if params.get("quantization"):
            cmd += ["--quantization", str(params["quantization"])]
        if params.get("trust_remote_code"):
            cmd.append("--trust-remote-code")
        served = params.get("served_model_name") or ctx.model_name
        cmd += ["--served-model-name", str(served)]
        return cmd

    async def start(self, ctx: EngineContext) -> dict:
        if not self.available():
            raise EngineError(
                "未检测到 vllm 可执行文件。请先 `pip install vllm`，"
                "或改用 mock / openai 兼容引擎。"
            )
        if not ctx.host_port:
            raise EngineError("缺少可用端口，无法启动 vLLM 实例")

        cmd = self._build_command(ctx)
        log_path = self._log_path(ctx)
        log_file = log_path.open("ab", buffering=0)

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=log_file,
            stderr=asyncio.subprocess.STDOUT,
            # 独立进程组，停止时能连子进程一起回收
            start_new_session=True,
            env={**os.environ, "VLLM_LOGGING_LEVEL": os.environ.get("VLLM_LOGGING_LEVEL", "INFO")},
        )
        self._procs[ctx.deployment_id] = proc

        client = OpenAIChatClient(
            f"http://127.0.0.1:{ctx.host_port}",
            ctx.param("api_key", "EMPTY"),
        )
        self._clients[ctx.deployment_id] = client

        settings = get_settings()
        deadline = time.time() + settings.engine_start_timeout_seconds * 20
        while time.time() < deadline:
            if proc.returncode is not None:
                await client.aclose()
                raise EngineError(
                    f"vLLM 进程退出（code={proc.returncode}），详见日志 {log_path}"
                )
            try:
                models = await client.models()
                return {
                    "engine": self.name,
                    "pid": proc.pid,
                    "base_url": client.base_url,
                    "upstream_models": models,
                    "log_path": str(log_path),
                    "command": cmd,
                    "loaded_at": time.time(),
                }
            except httpx.HTTPError:
                await asyncio.sleep(1.0)

        await self._terminate(ctx.deployment_id, proc)
        await client.aclose()
        raise EngineError(
            f"vLLM 实例在 {settings.engine_start_timeout_seconds * 20}s 内未就绪，"
            f"详见日志 {log_path}"
        )

    async def _terminate(self, deployment_id: int, proc: asyncio.subprocess.Process) -> None:
        if proc.returncode is not None:
            return
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=15)
        except asyncio.TimeoutError:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                proc.kill()
            await proc.wait()
        self._procs.pop(deployment_id, None)

    async def stop(self, ctx: EngineContext) -> None:
        client = self._clients.pop(ctx.deployment_id, None)
        if client is not None:
            await client.aclose()
        proc = self._procs.get(ctx.deployment_id)
        if proc is not None:
            await self._terminate(ctx.deployment_id, proc)

    async def health(self, ctx: EngineContext) -> bool:
        proc = self._procs.get(ctx.deployment_id)
        if proc is not None and proc.returncode is not None:
            return False
        client = self._clients.get(ctx.deployment_id)
        if client is None:
            return False
        try:
            await client.models()
            return True
        except httpx.HTTPError:
            return False

    async def complete(self, ctx: EngineContext, request) -> GenerationResult:
        client = self._clients.get(ctx.deployment_id)
        if client is None:
            raise EngineError("实例未启动，无法推理")
        return await client.complete(ctx, request)

    async def stream(self, ctx: EngineContext, request) -> AsyncIterator[str]:
        client = self._clients.get(ctx.deployment_id)
        if client is None:
            raise EngineError("实例未启动，无法推理")
        async for chunk in client.stream(ctx, request):
            yield chunk

    async def metrics(self, ctx: EngineContext) -> EngineMetrics:
        client = self._clients.get(ctx.deployment_id)
        if client is None:
            return EngineMetrics()
        return await collect_upstream_metrics(client, ctx)
