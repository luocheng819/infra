"""运行时配置。

所有配置均可通过环境变量或 backend/.env 覆盖，前缀 ``LLMD_``。
默认值保证零外部依赖：SQLite + 本地文件存储 + Mock 引擎。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="LLMD_",
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "LLM Deploy"
    debug: bool = True

    # 存储
    data_dir: Path = BACKEND_DIR / "data"

    # 认证
    secret_key: str = "dev-secret-change-me-in-production"
    access_token_ttl_minutes: int = 60 * 12
    bootstrap_admin_username: str = "admin"
    bootstrap_admin_password: str = "admin123"

    # 推理引擎
    default_engine: str = "mock"
    # 部署容器（模型实例）默认监听端口区间，编排器按此分配 host_port
    port_range_start: int = 8100
    port_range_end: int = 8199
    engine_start_timeout_seconds: int = 30
    health_check_interval_seconds: int = 5

    # 指标采集
    metrics_collect_interval_seconds: int = 3
    metrics_retention_points: int = 240

    # 跨域，前端开发服务器地址
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.data_dir / 'llmd.db'}"

    @property
    def models_dir(self) -> Path:
        return self.data_dir / "models"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    def ensure_dirs(self) -> None:
        for path in (self.data_dir, self.models_dir, self.logs_dir):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings
