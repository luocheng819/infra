"""一键启动脚本：构建前端并启动后端（单进程同时提供 API 与界面）。

用法：
    python start.py              # 默认 127.0.0.1:8000
    python start.py --port 9000
    python start.py --reload     # 开发模式
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = REPO_DIR / "frontend"


def build_frontend() -> None:
    if not FRONTEND_DIR.is_dir():
        print("[skip] 未找到 frontend 目录，仅启动 API")
        return
    if shutil.which("npm") is None:
        print("[skip] 未找到 npm，跳过前端构建；界面可通过 vite dev 运行")
        return

    print("[1/2] 构建前端 ...")
    result = subprocess.run(
        ["npm", "run", "build"], cwd=FRONTEND_DIR, shell=(sys.platform == "win32")
    )
    if result.returncode != 0:
        print("[warn] 前端构建失败，将以纯 API 模式启动")
        return
    print("[1/2] 前端构建完成")


def main() -> None:
    parser = argparse.ArgumentParser(description="启动 LLM Deploy 平台")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true", help="代码变更自动重载")
    parser.add_argument("--skip-build", action="store_true", help="跳过前端构建")
    args = parser.parse_args()

    if not args.skip_build:
        build_frontend()
    else:
        print("[skip] 按要求跳过前端构建")

    print(f"[2/2] 启动服务 http://{args.host}:{args.port}")
    print(f"      API 文档 http://{args.host}:{args.port}/docs")
    print("      默认账号 admin / admin123")

    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        args.host,
        "--port",
        str(args.port),
    ]
    if args.reload:
        cmd.append("--reload")
    subprocess.run(cmd, cwd=REPO_DIR / "backend")


if __name__ == "__main__":
    main()
