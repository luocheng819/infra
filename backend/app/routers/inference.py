"""推理路由。

包含两套入口：
1. 平台控制台专用（``/api/inference/...``）—— 用平台登录态鉴权，供测试台使用；
2. OpenAI 兼容入口（``/v1/chat/completions`` 等）—— 用 API Key 鉴权，供业务系统调用。
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import orchestrator
from ..db import get_db
from ..models import ApiKey, Deployment, DeploymentStatus, Model, User
from ..schemas import (
    ChatChoice,
    ChatRequest,
    ChatResponse,
    CompletionRequest,
    CompletionResponse,
    OpenAIChatRequest,
    OpenAICompletionRequest,
    Usage,
)
from ..security import authenticate_api_key, get_current_user

router = APIRouter(tags=["推理"])


# --------------------------------------------------------------------------- #
# 工具
# --------------------------------------------------------------------------- #
def _ensure_running(db: Session, deployment: Deployment) -> Model:
    if deployment.status != DeploymentStatus.RUNNING:
        raise HTTPException(
            status_code=409,
            detail=f"部署 {deployment.name} 未在运行（当前 {deployment.status.value}）",
        )
    model = db.get(Model, deployment.model_id)
    if model is None:
        raise HTTPException(status_code=404, detail="关联模型不存在")
    return model


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _stream_response(db: Session, deployment: Deployment, request, api_key_id=None):
    """把编排器的流式产出包装成 SSE。"""

    async def event_stream():
        started = time.perf_counter()
        try:
            async for chunk in orchestrator.stream_completion(
                db, deployment.id, request, api_key_id=api_key_id
            ):
                yield _sse("delta", {"text": chunk})
            elapsed = (time.perf_counter() - started) * 1000
            yield _sse(
                "done",
                {
                    "deployment": deployment.name,
                    "latency_ms": round(elapsed, 2),
                    "finish_reason": "stop",
                },
            )
        except orchestrator.OrchestratorError as exc:
            yield _sse("error", {"message": str(exc)})
        except Exception as exc:  # noqa: BLE001
            yield _sse("error", {"message": f"推理中断：{exc}"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _openai_chunk(
    request_id: str,
    model_name: str,
    *,
    delta: dict | None = None,
    finish_reason: str | None = None,
    usage: dict | None = None,
) -> str:
    """构造 OpenAI 兼容的流式分片。"""
    payload: dict = {
        "id": request_id,
        "object": "chat.completion.chunk",
        "created": int(datetime.now(timezone.utc).timestamp()),
        "model": model_name,
        "choices": [{"index": 0, "delta": delta or {}, "finish_reason": finish_reason}],
    }
    if usage is not None:
        payload["usage"] = usage
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _openai_stream_response(db: Session, deployment: Deployment, request, api_key_id=None):
    """OpenAI 兼容的流式响应：分片格式必须符合官方 SDK 的解析预期。"""

    async def event_stream():
        request_id = f"cmpl-{uuid.uuid4().hex[:24]}"
        yield _openai_chunk(request_id, deployment.name, delta={"role": "assistant"})
        collected: list[str] = []
        try:
            async for chunk in orchestrator.stream_completion(
                db,
                deployment.id,
                request,
                api_key_id=api_key_id,
                request_id=request_id,
            ):
                collected.append(chunk)
                yield _openai_chunk(request_id, deployment.name, delta={"content": chunk})
        except orchestrator.OrchestratorError as exc:
            yield f"data: {json.dumps({'error': {'message': str(exc)}})}\n\n"
        finally:
            tokens = max(1, len("".join(collected)) // 3) if collected else 0
            yield _openai_chunk(
                request_id,
                deployment.name,
                delta={},
                finish_reason="stop",
                usage={
                    "prompt_tokens": 0,
                    "completion_tokens": tokens,
                    "total_tokens": tokens,
                },
            )
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _openai_text_stream_response(
    db: Session, deployment: Deployment, request, api_key_id=None
):
    """``/v1/completions`` 的流式格式（text 字段而非 delta）。"""

    async def event_stream():
        request_id = f"cmpl-{uuid.uuid4().hex[:24]}"
        try:
            async for chunk in orchestrator.stream_completion(
                db,
                deployment.id,
                request,
                api_key_id=api_key_id,
                request_id=request_id,
            ):
                payload = {
                    "id": request_id,
                    "object": "text_completion",
                    "created": int(datetime.now(timezone.utc).timestamp()),
                    "model": deployment.name,
                    "choices": [{"index": 0, "text": chunk, "finish_reason": None}],
                }
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
        except orchestrator.OrchestratorError as exc:
            yield f"data: {json.dumps({'error': {'message': str(exc)}})}\n\n"
        finally:
            payload = {
                "id": request_id,
                "object": "text_completion",
                "created": int(datetime.now(timezone.utc).timestamp()),
                "model": deployment.name,
                "choices": [{"index": 0, "text": "", "finish_reason": "stop"}],
            }
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _resolve_deployment(db: Session, key: str) -> Deployment:
    """按部署名或 ID 定位 RUNNING 部署。"""
    deployment = None
    if key.isdigit():
        deployment = db.get(Deployment, int(key))
    if deployment is None:
        deployment = db.scalar(select(Deployment).where(Deployment.name == key))
    if deployment is None:
        raise HTTPException(status_code=404, detail=f"未找到部署 {key!r}")
    return deployment


# --------------------------------------------------------------------------- #
# 控制台入口（登录态）
# --------------------------------------------------------------------------- #
@router.post(
    "/api/inference/{deployment_id}/completions",
    summary="文本补全（控制台）",
)
async def console_completion(
    deployment_id: int,
    payload: CompletionRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    deployment = db.get(Deployment, deployment_id)
    if deployment is None:
        raise HTTPException(status_code=404, detail="部署不存在")
    model = _ensure_running(db, deployment)

    if payload.stream:
        return _stream_response(db, deployment, payload)

    try:
        result, request_id, latency_ms = await orchestrator.run_completion(
            db, deployment_id, payload
        )
    except orchestrator.OrchestratorError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return CompletionResponse(
        id=request_id,
        deployment=deployment.name,
        model=model.name,
        text=result.text,
        finish_reason=result.finish_reason,
        usage=Usage(
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            total_tokens=result.prompt_tokens + result.completion_tokens,
        ),
        latency_ms=round(latency_ms, 2),
    )


@router.post(
    "/api/inference/{deployment_id}/chat/completions",
    summary="对话补全（控制台）",
)
async def console_chat(
    deployment_id: int,
    payload: ChatRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    deployment = db.get(Deployment, deployment_id)
    if deployment is None:
        raise HTTPException(status_code=404, detail="部署不存在")
    model = _ensure_running(db, deployment)

    if payload.stream:
        return _stream_response(db, deployment, payload)

    try:
        result, request_id, latency_ms = await orchestrator.run_completion(
            db, deployment_id, payload
        )
    except orchestrator.OrchestratorError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return ChatResponse(
        id=request_id,
        deployment=deployment.name,
        model=model.name,
        choices=[
            ChatChoice(
                message={"role": "assistant", "content": result.text},
                finish_reason=result.finish_reason,
            )
        ],
        usage=Usage(
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            total_tokens=result.prompt_tokens + result.completion_tokens,
        ),
        latency_ms=round(latency_ms, 2),
    )


# --------------------------------------------------------------------------- #
# OpenAI 兼容入口（API Key）
# --------------------------------------------------------------------------- #
def _api_key_auth(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="x-api-key"),
    db: Session = Depends(get_db),
) -> ApiKey | None:
    raw = x_api_key
    if not raw and authorization and authorization.lower().startswith("bearer "):
        raw = authorization[7:].strip()
    if not raw:
        raise HTTPException(
            status_code=401, detail="缺少 API Key（Authorization: Bearer sk-...）"
        )
    key = authenticate_api_key(db, raw)
    if key is None:
        raise HTTPException(status_code=401, detail="API Key 无效或已禁用")
    return key


@router.get("/v1/models", summary="列出可用模型（OpenAI 兼容）")
def openai_models(
    db: Session = Depends(get_db), _: ApiKey | None = Depends(_api_key_auth)
) -> dict:
    rows = db.scalars(
        select(Deployment).where(Deployment.status == DeploymentStatus.RUNNING)
    ).all()
    return {
        "object": "list",
        "data": [
            {
                "id": d.name,
                "object": "model",
                "created": int(d.created_at.timestamp()),
                "owned_by": "llm-deploy",
            }
            for d in rows
        ],
    }


@router.post("/v1/chat/completions", summary="对话补全（OpenAI 兼容）")
async def openai_chat(
    payload: OpenAIChatRequest,
    db: Session = Depends(get_db),
    key: ApiKey | None = Depends(_api_key_auth),
    model_header: str | None = Header(default=None, alias="x-deployment"),
):
    """模型名即部署名。也可用 X-Deployment 头显式指定。"""
    target = model_header or payload.model
    if not target:
        raise HTTPException(
            status_code=400,
            detail="请在请求体 model 字段或 X-Deployment 头中指定部署名",
        )
    deployment = await _resolve_deployment(db, target)
    _ensure_running(db, deployment)
    api_key_id = key.id if key else None

    if payload.stream:
        return _openai_stream_response(db, deployment, payload, api_key_id)

    try:
        result, request_id, _ = await orchestrator.run_completion(
            db, deployment.id, payload, api_key_id=api_key_id
        )
    except orchestrator.OrchestratorError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {
        "id": request_id,
        "object": "chat.completion",
        "created": int(datetime.now(timezone.utc).timestamp()),
        "model": deployment.name,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": result.text},
                "finish_reason": result.finish_reason,
            }
        ],
        "usage": {
            "prompt_tokens": result.prompt_tokens,
            "completion_tokens": result.completion_tokens,
            "total_tokens": result.prompt_tokens + result.completion_tokens,
        },
    }


@router.post("/v1/completions", summary="文本补全（OpenAI 兼容）")
async def openai_completion(
    payload: OpenAICompletionRequest,
    db: Session = Depends(get_db),
    key: ApiKey | None = Depends(_api_key_auth),
    deployment_header: str | None = Header(default=None, alias="x-deployment"),
):
    target = deployment_header or payload.model
    if not target:
        raise HTTPException(
            status_code=400,
            detail="请在请求体 model 字段或 X-Deployment 头中指定部署名",
        )
    deployment = await _resolve_deployment(db, target)
    _ensure_running(db, deployment)
    api_key_id = key.id if key else None

    if payload.stream:
        return _openai_text_stream_response(db, deployment, payload, api_key_id)

    try:
        result, request_id, _ = await orchestrator.run_completion(
            db, deployment.id, payload, api_key_id=api_key_id
        )
    except orchestrator.OrchestratorError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {
        "id": request_id,
        "object": "text_completion",
        "created": int(datetime.now(timezone.utc).timestamp()),
        "model": deployment.name,
        "choices": [
            {"index": 0, "text": result.text, "finish_reason": result.finish_reason}
        ],
        "usage": {
            "prompt_tokens": result.prompt_tokens,
            "completion_tokens": result.completion_tokens,
            "total_tokens": result.prompt_tokens + result.completion_tokens,
        },
    }


_ = uuid  # 保留引用，避免误删导入
