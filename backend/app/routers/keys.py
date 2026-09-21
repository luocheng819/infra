"""API Key 管理路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import ApiKey, User
from ..schemas import ApiKeyCreate, ApiKeyCreated, ApiKeyOut
from ..security import generate_api_key, get_current_user

router = APIRouter(prefix="/api/keys", tags=["API Key"])


@router.get("", response_model=list[ApiKeyOut], summary="API Key 列表")
def list_keys(
    db: Session = Depends(get_db), _: User = Depends(get_current_user)
) -> list[ApiKeyOut]:
    keys = db.scalars(select(ApiKey).order_by(ApiKey.id.desc())).all()
    return [ApiKeyOut.model_validate(k) for k in keys]


@router.post(
    "",
    response_model=ApiKeyCreated,
    status_code=status.HTTP_201_CREATED,
    summary="创建 API Key（明文仅返回一次）",
)
def create_key(
    payload: ApiKeyCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ApiKeyCreated:
    raw, prefix, hashed = generate_api_key()
    key = ApiKey(name=payload.name, prefix=prefix, hashed_key=hashed, owner=user.username)
    db.add(key)
    db.commit()
    db.refresh(key)
    out = ApiKeyCreated.model_validate(key)
    out.key = raw
    return out


@router.post("/{key_id}/toggle", response_model=ApiKeyOut, summary="启用/禁用")
def toggle_key(
    key_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)
) -> ApiKeyOut:
    key = db.get(ApiKey, key_id)
    if key is None:
        raise HTTPException(status_code=404, detail="API Key 不存在")
    key.is_active = not key.is_active
    db.commit()
    db.refresh(key)
    return ApiKeyOut.model_validate(key)


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除")
def delete_key(
    key_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)
) -> None:
    key = db.get(ApiKey, key_id)
    if key is None:
        raise HTTPException(status_code=404, detail="API Key 不存在")
    db.delete(key)
    db.commit()
