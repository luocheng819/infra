"""FastAPI 应用入口。"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from . import __version__
from .config import REPO_DIR, get_settings
from .db import SessionLocal, init_db
from .engines import load_builtin_engines
from .models import Model, ModelSource, User
from .orchestrator import monitor, shutdown_all_engines
from .routers import auth, deployments, inference, keys, metrics, models, overview
from .security import hash_password

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s | %(message)s"
)
logger = logging.getLogger("llmd")

settings = get_settings()

SEED_MODELS = [
    {
        "name": "qwen2.5-7b-instruct",
        "display_name": "Qwen2.5-7B-Instruct",
        "description": "通义千问 2.5 7B 指令微调版，中文对话与通用任务的稳妥基线。",
        "source": ModelSource.HUGGINGFACE,
        "source_ref": "Qwen/Qwen2.5-7B-Instruct",
        "parameter_count": "7B",
        "quantization": None,
        "size_bytes": 15_200_000_000,
        "tags": ["中文", "对话", "通用"],
        "default_engine_params": {"max_tokens": 512, "temperature": 0.7},
    },
    {
        "name": "qwen2.5-14b-instruct-awq",
        "display_name": "Qwen2.5-14B-Instruct (AWQ)",
        "description": "14B 的 4bit 量化版本，单卡 24G 即可部署，质量接近 BF16。",
        "source": ModelSource.HUGGINGFACE,
        "source_ref": "Qwen/Qwen2.5-14B-Instruct-AWQ",
        "parameter_count": "14B",
        "quantization": "awq",
        "size_bytes": 9_600_000_000,
        "tags": ["中文", "量化", "AWQ"],
        "default_engine_params": {"quantization": "awq", "gpu_memory_utilization": 0.9},
    },
    {
        "name": "llama-3.1-8b-instruct",
        "display_name": "Llama-3.1-8B-Instruct",
        "description": "Meta Llama 3.1 8B 指令版，英文与多语言能力均衡。",
        "source": ModelSource.HUGGINGFACE,
        "source_ref": "meta-llama/Llama-3.1-8B-Instruct",
        "parameter_count": "8B",
        "quantization": None,
        "size_bytes": 16_100_000_000,
        "tags": ["英文", "多语言", "对话"],
        "default_engine_params": {"max_tokens": 512, "temperature": 0.6},
    },
    {
        "name": "bge-m3",
        "display_name": "BGE-M3 向量模型",
        "description": "多语言文本向量模型，常用于 RAG 检索与语义召回。",
        "source": ModelSource.MODELSCOPE,
        "source_ref": "BAAI/bge-m3",
        "parameter_count": "0.6B",
        "quantization": None,
        "size_bytes": 2_300_000_000,
        "tags": ["向量", "RAG", "检索"],
        "default_engine_params": {"max_tokens": 256, "temperature": 0.0},
    },
]


def seed(db) -> None:
    """首次启动时写入演示账号与示例模型目录。"""
    if db.scalar(select(User).where(User.username == settings.bootstrap_admin_username)) is None:
        db.add(
            User(
                username=settings.bootstrap_admin_username,
                email="admin@example.com",
                hashed_password=hash_password(settings.bootstrap_admin_password),
                is_admin=True,
            )
        )
        logger.info(
            "已创建初始管理员：%s / %s（请尽快修改）",
            settings.bootstrap_admin_username,
            settings.bootstrap_admin_password,
        )

    if db.scalar(select(Model).limit(1)) is None:
        for item in SEED_MODELS:
            db.add(Model(**item))
        logger.info("已写入 %d 个示例模型", len(SEED_MODELS))
    db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.ensure_dirs()
    init_db()
    load_builtin_engines()
    db = SessionLocal()
    try:
        seed(db)
    finally:
        db.close()
    monitor.start()
    logger.info("%s v%s 已启动，数据目录 %s", settings.app_name, __version__, settings.data_dir)
    try:
        yield
    finally:
        await monitor.shutdown()
        await shutdown_all_engines()
        logger.info("已关闭并回收所有引擎实例")


app = FastAPI(
    title=settings.app_name,
    description=(
        "大模型部署推理管理平台：模型仓库、部署生命周期编排、"
        "可插拔推理引擎、在线推理测试台与可观测性。"
    ),
    version=__version__,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(models.router)
app.include_router(deployments.router)
app.include_router(inference.router)
app.include_router(metrics.router)
app.include_router(keys.router)
app.include_router(overview.router)


@app.get("/api/health", tags=["系统"], summary="服务健康检查")
def health() -> dict:
    return {"status": "ok", "app": settings.app_name, "version": __version__}


# --------------------------------------------------------------------------- #
# 前端静态资源
#
# 若已执行 `npm run build`，这里直接把 SPA 挂到根路径，实现单进程部署；
# 未构建时（走 vite dev server）自动跳过，不影响 API 使用。
# --------------------------------------------------------------------------- #
FRONTEND_DIST = REPO_DIR / "frontend" / "dist"

if FRONTEND_DIST.is_dir():
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    app.mount(
        "/assets",
        StaticFiles(directory=FRONTEND_DIST / "assets"),
        name="assets",
    )

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str) -> FileResponse:
        """未匹配的路径统一回落到 index.html，交给前端路由处理。"""
        candidate = FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")

    logger.info("已挂载前端静态资源：%s", FRONTEND_DIST)
else:
    logger.info("未找到前端构建产物，仅提供 API（开发时请运行 npm run dev）")
