"""路由聚合。"""

from . import auth, deployments, inference, keys, metrics, models, overview

__all__ = [
    "auth",
    "deployments",
    "inference",
    "keys",
    "metrics",
    "models",
    "overview",
]
