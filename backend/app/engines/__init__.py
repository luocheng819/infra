"""引擎注册表。

用装饰器注册，编排器通过名字查表拿到单例适配器。
"""

from __future__ import annotations

from .base import EngineError, EngineContext, EngineMetrics, GenerationResult, InferenceEngine

_REGISTRY: dict[str, InferenceEngine] = {}


def register_engine(cls: type[InferenceEngine]) -> type[InferenceEngine]:
    if not cls.name:
        raise ValueError(f"{cls.__name__} 缺少 name")
    if cls.name in _REGISTRY:
        raise ValueError(f"引擎 {cls.name!r} 重复注册")
    _REGISTRY[cls.name] = cls()
    return cls


def get_engine(name: str) -> InferenceEngine:
    try:
        return _REGISTRY[name]
    except KeyError as exc:
        raise EngineError(
            f"未知引擎 {name!r}，可用引擎：{', '.join(sorted(_REGISTRY))}"
        ) from exc


def list_engines() -> list[InferenceEngine]:
    return [_REGISTRY[name] for name in sorted(_REGISTRY)]


def load_builtin_engines() -> None:
    """导入内置引擎以触发注册。"""
    from . import mock, openai_compat, vllm  # noqa: F401


__all__ = [
    "EngineContext",
    "EngineError",
    "EngineMetrics",
    "GenerationResult",
    "InferenceEngine",
    "get_engine",
    "list_engines",
    "load_builtin_engines",
    "register_engine",
]
