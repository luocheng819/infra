"""OpenAI 兼容引擎。

对接任意暴露 ``/v1/chat/completions`` 的服务：vLLM、Ollama、TGI、SGLang、
LM Studio、OpenAI 官方 API 等。

它既可独立使用（``base_url`` 指向已存在的服务），也被 ``vllm`` 引擎复用为
推理客户端 —— 后者只负责把进程拉起来。
"""

from __future__ import annotations

import json
import time
from typing import AsyncIterator

import httpx

from ..schemas import ChatRequest, CompletionRequest
from .base import (
    EngineContext,
    EngineError,
    EngineMetrics,
    GenerationResult,
    InferenceEngine,
)
from . import register_engine

DEFAULT_TIMEOUT = httpx.Timeout(connect=10.0, read=300.0, write=60.0, pool=10.0)


def _messages_of(request) -> list[dict]:
    if isinstance(request, ChatRequest):
        return [{"role": m.role, "content": m.content} for m in request.messages]
    return [{"role": "user", "content": request.prompt}]


class OpenAIChatClient:
    """对 OpenAI 兼容接口的最小封装，供多个引擎复用。"""

    def __init__(self, base_url: str, api_key: str = "EMPTY") -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or "EMPTY"
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=DEFAULT_TIMEOUT,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def models(self) -> list[str]:
        resp = await self._client.get("/v1/models")
        resp.raise_for_status()
        return [m["id"] for m in resp.json().get("data", [])]

    def _payload(self, ctx: EngineContext, request, stream: bool) -> dict:
        params = ctx.engine_params or {}
        payload = {
            "model": ctx.param("served_model_name") or ctx.model_name,
            "messages": _messages_of(request),
            "max_tokens": getattr(request, "max_tokens", 256),
            "temperature": getattr(request, "temperature", 0.7),
            "top_p": getattr(request, "top_p", 1.0),
            "stream": stream,
        }
        # 透传其余可调项（presence_penalty 等）
        for key in ("presence_penalty", "frequency_penalty", "stop", "seed"):
            if key in params and params[key] is not None:
                payload[key] = params[key]
        if stream:
            payload["stream_options"] = {"include_usage": True}
        return payload

    async def complete(self, ctx: EngineContext, request) -> GenerationResult:
        resp = await self._client.post(
            "/v1/chat/completions", json=self._payload(ctx, request, stream=False)
        )
        if resp.status_code >= 400:
            raise EngineError(f"上游返回 {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        choice = (data.get("choices") or [{}])[0]
        usage = data.get("usage") or {}
        return GenerationResult(
            text=(choice.get("message") or {}).get("content", ""),
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            finish_reason=choice.get("finish_reason") or "stop",
        )

    async def stream(self, ctx: EngineContext, request) -> AsyncIterator[str]:
        payload = self._payload(ctx, request, stream=True)
        async with self._client.stream("POST", "/v1/chat/completions", json=payload) as resp:
            if resp.status_code >= 400:
                body = (await resp.aread()).decode(errors="replace")
                raise EngineError(f"上游返回 {resp.status_code}: {body[:300]}")
            async for line in resp.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                chunk = line[5:].strip()
                if chunk == "[DONE]":
                    break
                try:
                    data = json.loads(chunk)
                except json.JSONDecodeError:
                    continue
                for choice in data.get("choices") or []:
                    delta = choice.get("delta") or {}
                    content = delta.get("content")
                    if content:
                        yield content

    async def stats(self) -> dict:
        """尽力从 /metrics 拉取（vLLM 暴露 Prometheus 格式）。"""
        try:
            resp = await self._client.get("/metrics")
            if resp.status_code >= 400:
                return {}
        except httpx.HTTPError:
            return {}
        out: dict[str, float] = {}
        for line in resp.text.splitlines():
            if line.startswith("#") or " " not in line:
                continue
            key, _, value = line.rpartition(" ")
            try:
                out[key.strip()] = float(value)
            except ValueError:
                continue
        return out


@register_engine
class OpenAICompatEngine(InferenceEngine):
    name = "openai"
    display_name = "OpenAI 兼容服务"
    description = (
        "对接任意 OpenAI 兼容的 /v1/chat/completions 服务，"
        "如 vLLM、Ollama、TGI、SGLang、LM Studio 或 OpenAI 官方 API。"
    )
    requires_gpu = False
    default_params = {
        "base_url": "http://127.0.0.1:8000",
        "api_key": "EMPTY",
        "served_model_name": "",
        "max_tokens": 512,
        "temperature": 0.7,
    }
    param_schema = [
        {
            "key": "base_url",
            "label": "服务地址",
            "type": "string",
            "default": "http://127.0.0.1:8000",
            "required": True,
            "help": "OpenAI 兼容服务的根地址，无需带 /v1",
        },
        {
            "key": "api_key",
            "label": "API Key",
            "type": "password",
            "default": "EMPTY",
            "help": "本地服务通常填 EMPTY",
        },
        {
            "key": "served_model_name",
            "label": "服务端模型名",
            "type": "string",
            "default": "",
            "help": "留空则使用平台登记的模型名",
        },
        {"key": "max_tokens", "label": "最大生成长度", "type": "int", "default": 512},
        {
            "key": "temperature",
            "label": "温度",
            "type": "float",
            "default": 0.7,
            "min": 0,
            "max": 2,
            "step": 0.1,
        },
    ]

    _clients: dict[int, OpenAIChatClient] = {}

    def _client(self, ctx: EngineContext) -> OpenAIChatClient:
        base_url = ctx.param("base_url") or self.default_params["base_url"]
        return OpenAIChatClient(base_url, ctx.param("api_key", "EMPTY"))

    async def start(self, ctx: EngineContext) -> dict:
        client = self._client(ctx)
        try:
            models = await client.models()
        except httpx.HTTPError as exc:
            await client.aclose()
            raise EngineError(
                f"无法连接 {client.base_url}/v1/models：{exc}。"
                "请确认服务已启动且地址正确。"
            ) from exc
        self._clients[ctx.deployment_id] = client
        return {
            "engine": self.name,
            "base_url": client.base_url,
            "upstream_models": models,
            "loaded_at": time.time(),
        }

    async def stop(self, ctx: EngineContext) -> None:
        client = self._clients.pop(ctx.deployment_id, None)
        if client is not None:
            await client.aclose()

    async def health(self, ctx: EngineContext) -> bool:
        client = self._clients.get(ctx.deployment_id)
        if client is None:
            return False
        try:
            await client.models()
            return True
        except httpx.HTTPError:
            return False

    async def complete(self, ctx: EngineContext, request) -> GenerationResult:
        return await self._client(ctx).complete(ctx, request)

    async def stream(self, ctx: EngineContext, request) -> AsyncIterator[str]:
        async for chunk in self._client(ctx).stream(ctx, request):
            yield chunk

    async def metrics(self, ctx: EngineContext) -> EngineMetrics:
        client = self._clients.get(ctx.deployment_id)
        if client is None:
            return EngineMetrics()
        return await collect_upstream_metrics(client, ctx)


async def collect_upstream_metrics(
    client: OpenAIChatClient, ctx: EngineContext
) -> EngineMetrics:
    """解析上游 Prometheus 指标（vLLM 格式），供 openai / vllm 引擎共用。"""
    raw = await client.stats()
    if not raw:
        return EngineMetrics()

    def pick(*names: str) -> float:
        for name in names:
            for key, value in raw.items():
                if key.startswith(name):
                    return value
        return 0.0

    prompt_tokens = pick("vllm:prompt_tokens_total", "prompt_tokens_total")
    gen_tokens = pick("vllm:generation_tokens_total", "generation_tokens_total")
    running = pick("vllm:num_requests_running", "num_requests_running")
    waiting = pick("vllm:num_requests_waiting", "num_requests_waiting")
    cache_usage = pick("vllm:gpu_cache_usage_perc", "gpu_cache_usage_perc")
    ttft_sum = pick("vllm:time_to_first_token_seconds_sum")
    ttft_count = pick("vllm:time_to_first_token_seconds_count")
    latency_p50 = ttft_sum / ttft_count * 1000 if ttft_count else 0.0

    return EngineMetrics(
        tokens_per_second=gen_tokens,
        latency_p50_ms=latency_p50,
        gpu_utilization=cache_usage * 100.0,
        total_requests=int(prompt_tokens + gen_tokens),
        running_requests=int(running),
        queue_depth=int(waiting),
    )
