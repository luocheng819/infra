"""Mock 引擎：零依赖的本地仿真推理后端。

用途：
1. 平台在没有 GPU / 没有真实权重时也能完整跑通部署与推理链路；
2. 作为引擎接口的参考实现（``start``/``stop``/``health``/``complete``/``stream``/``metrics``）。

它会依据提示词生成结构化的模拟回复，并按请求量模拟吞吐、延迟与显存占用曲线，
使监控面板有真实形状的数据可看。
"""

from __future__ import annotations

import asyncio
import math
import random
import time
from typing import AsyncIterator

from ..schemas import ChatRequest, CompletionRequest
from .base import EngineContext, EngineMetrics, GenerationResult, InferenceEngine
from . import register_engine


@register_engine
class MockEngine(InferenceEngine):
    name = "mock"
    display_name = "Mock 仿真引擎"
    description = (
        "内置仿真引擎，无需 GPU 与权重文件即可完整体验部署、推理与监控链路。"
        "按提示词生成确定性占位回复，并模拟吞吐/延迟/显存曲线。"
    )
    requires_gpu = False
    default_params = {
        "max_tokens": 256,
        "temperature": 0.7,
        "top_p": 1.0,
        "simulated_tps": 45.0,  # 模拟每 token 耗时基准
        "simulated_gpu_memory_mb": 8192,
        "failure_rate": 0.0,
    }
    param_schema = [
        {
            "key": "max_tokens",
            "label": "最大生成长度",
            "type": "int",
            "default": 256,
            "min": 1,
            "max": 8192,
            "help": "单次请求最多生成的 token 数",
        },
        {
            "key": "temperature",
            "label": "温度",
            "type": "float",
            "default": 0.7,
            "min": 0.0,
            "max": 2.0,
            "step": 0.1,
        },
        {
            "key": "simulated_tps",
            "label": "模拟吞吐 (token/s)",
            "type": "float",
            "default": 45.0,
            "min": 1.0,
            "max": 2000.0,
            "help": "仅影响仿真速度与指标曲线",
        },
        {
            "key": "simulated_gpu_memory_mb",
            "label": "模拟显存占用 (MB)",
            "type": "int",
            "default": 8192,
            "min": 0,
            "max": 262144,
        },
    ]

    #: 进程内状态：deployment_id -> stats
    _state: dict[int, dict] = {}

    async def start(self, ctx: EngineContext) -> dict:
        await asyncio.sleep(0.2)  # 模拟加载耗时
        self._state[ctx.deployment_id] = {
            "started_at": time.time(),
            "requests": 0,
            "failed": 0,
            "running": 0,
            "latencies": [],
            "tokens": 0,
            "rng": random.Random(ctx.deployment_id),
        }
        return {
            "engine": self.name,
            "pid": None,
            "loaded_at": time.time(),
            "model_path": ctx.model_path,
        }

    async def stop(self, ctx: EngineContext) -> None:
        self._state.pop(ctx.deployment_id, None)

    async def health(self, ctx: EngineContext) -> bool:
        return ctx.deployment_id in self._state

    # ------------------------------------------------------------------ #
    def _stats(self, ctx: EngineContext) -> dict:
        return self._state.setdefault(
            ctx.deployment_id,
            {
                "started_at": time.time(),
                "requests": 0,
                "failed": 0,
                "running": 0,
                "latencies": [],
                "tokens": 0,
                "rng": random.Random(ctx.deployment_id),
            },
        )

    def _compose(self, ctx: EngineContext, request) -> str:
        """生成模拟回复，包含足够信息以验证链路。"""
        if isinstance(request, ChatRequest):
            last_user = next(
                (m.content for m in reversed(request.messages) if m.role == "user"), ""
            )
            system = next((m.content for m in request.messages if m.role == "system"), "")
            turns = len(request.messages)
            head = f"[{ctx.model_name} @ {ctx.deployment_name}]"
            body = (
                f"收到 {turns} 条消息，最后一条用户输入为「{last_user}」。\n"
                f"这是 Mock 引擎生成的模拟回复，用于验证平台链路。"
            )
            if system:
                body += f"\n已应用系统提示词：{system[:60]}…"
            return f"{head}\n{body}"
        return (
            f"[{ctx.model_name} @ {ctx.deployment_name}]\n"
            f"针对提示词「{request.prompt}」的模拟补全结果。\n"
            f"Mock 引擎不执行真实推理，仅用于验证部署、路由、计量与监控。"
        )

    async def complete(self, ctx: EngineContext, request) -> GenerationResult:
        stats = self._stats(ctx)
        tps = float(ctx.param("simulated_tps", 45.0))
        text = self._compose(ctx, request)
        completion_tokens = max(1, int(len(text) / 2.5))
        prompt_tokens = (
            sum(len(m.content) for m in request.messages) // 3 + 4
            if isinstance(request, ChatRequest)
            else len(request.prompt) // 3 + 4
        )
        delay = completion_tokens / max(tps, 1.0)
        await asyncio.sleep(min(delay, 3.0))

        stats["requests"] += 1
        stats["tokens"] += completion_tokens
        stats["latencies"].append(delay * 1000)
        stats["latencies"] = stats["latencies"][-200:]

        if stats["rng"].random() < float(ctx.param("failure_rate", 0.0)):
            stats["failed"] += 1
            raise RuntimeError("Mock 引擎注入的模拟失败")

        return GenerationResult(
            text=text,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            finish_reason="stop",
        )

    async def stream(self, ctx: EngineContext, request) -> AsyncIterator[str]:
        stats = self._stats(ctx)
        text = self._compose(ctx, request)
        tps = float(ctx.param("simulated_tps", 45.0))
        stats["running"] += 1
        stats["requests"] += 1
        started = time.time()
        try:
            # 按小块吐字，模拟真实流式体验
            step = max(1, len(text) // 40)
            for i in range(0, len(text), step):
                chunk = text[i : i + step]
                await asyncio.sleep(step / max(tps * 2.5, 1.0))
                yield chunk
        finally:
            stats["running"] -= 1
            stats["latencies"].append((time.time() - started) * 1000)
            stats["latencies"] = stats["latencies"][-200:]

    async def metrics(self, ctx: EngineContext) -> EngineMetrics:
        stats = self._stats(ctx)
        latencies = sorted(stats["latencies"])
        uptime = max(time.time() - stats["started_at"], 1e-6)
        rng: random.Random = stats["rng"]

        def percentile(p: float) -> float:
            if not latencies:
                return 0.0
            idx = min(int(len(latencies) * p), len(latencies) - 1)
            return latencies[idx]

        gpu_total = float(ctx.param("simulated_gpu_memory_mb", 8192))
        # 显存随累计请求缓慢爬升，并带小幅抖动
        load = min(stats["requests"] / 200.0, 1.0)
        gpu_used = gpu_total * (0.55 + 0.35 * load) + rng.uniform(-50, 50)
        util = min(95.0, 25.0 + 60.0 * load) + rng.uniform(-4, 4)

        return EngineMetrics(
            qps=stats["requests"] / uptime,
            tokens_per_second=stats["tokens"] / uptime,
            latency_p50_ms=percentile(0.5),
            latency_p95_ms=percentile(0.95),
            gpu_utilization=max(0.0, util),
            gpu_memory_used_mb=max(0.0, gpu_used),
            gpu_memory_total_mb=gpu_total,
            total_requests=stats["requests"],
            failed_requests=stats["failed"],
            running_requests=stats["running"],
            queue_depth=max(0, stats["running"] - 1),
        )
