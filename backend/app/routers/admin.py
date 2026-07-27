import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth import create_token, hash_api_key, require_admin
from app.config import get_settings
from app.database import get_db
from app.models import ApiKey, UsageLog
from app.schemas import (
    AdminLoginRequest,
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyOut,
    ApiKeyUpdate,
    SystemSettingsOut,
    SystemSettingsUpdate,
    TokenResponse,
    UsageLogOut,
)
from app.services.settings import apply_settings_update, get_or_create_settings, mask_api_key

router = APIRouter(prefix="/api/admin", tags=["admin"])
settings = get_settings()


def _settings_out(row) -> SystemSettingsOut:
    return SystemSettingsOut(
        upstream_base_url=row.upstream_base_url or "",
        upstream_api_key_masked=mask_api_key(row.upstream_api_key or ""),
        has_upstream_api_key=bool((row.upstream_api_key or "").strip()),
        default_model=row.default_model or "gpt-image-2",
        response_format=row.response_format or "url",
        updated_at=row.updated_at,
    )


@router.post("/login", response_model=TokenResponse)
def admin_login(body: AdminLoginRequest) -> TokenResponse:
    if body.password != settings.admin_password:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="管理员口令错误")
    token = create_token(
        subject="admin",
        role="admin",
        expire_hours=settings.admin_token_expire_hours,
    )
    return TokenResponse(access_token=token)


@router.get("/settings", response_model=SystemSettingsOut)
def get_settings_api(
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> SystemSettingsOut:
    return _settings_out(get_or_create_settings(db))


@router.put("/settings", response_model=SystemSettingsOut)
def update_settings_api(
    body: SystemSettingsUpdate,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> SystemSettingsOut:
    row = apply_settings_update(
        db,
        upstream_base_url=body.upstream_base_url,
        upstream_api_key=body.upstream_api_key,
        default_model=body.default_model,
        response_format=body.response_format,
    )
    return _settings_out(row)


@router.get("/keys", response_model=list[ApiKeyOut])
def list_keys(
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[ApiKey]:
    return db.query(ApiKey).order_by(ApiKey.id.desc()).all()


@router.post("/keys", response_model=ApiKeyCreated)
def create_key(
    body: ApiKeyCreate,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ApiKeyCreated:
    raw = "sk-" + secrets.token_urlsafe(32)
    item = ApiKey(
        key_hash=hash_api_key(raw),
        key_prefix=raw[:10],
        name=body.name or "未命名",
        quota_total=body.quota_total,
        quota_used=0,
        enabled=True,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return ApiKeyCreated(
        id=item.id,
        name=item.name,
        key_prefix=item.key_prefix,
        quota_total=item.quota_total,
        quota_used=item.quota_used,
        quota_remaining=item.quota_remaining,
        enabled=item.enabled,
        created_at=item.created_at,
        updated_at=item.updated_at,
        api_key=raw,
    )


@router.patch("/keys/{key_id}", response_model=ApiKeyOut)
def update_key(
    key_id: int,
    body: ApiKeyUpdate,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ApiKey:
    item = db.get(ApiKey, key_id)
    if not item:
        raise HTTPException(status_code=404, detail="秘钥不存在")
    if body.name is not None:
        item.name = body.name
    if body.quota_total is not None:
        item.quota_total = body.quota_total
    if body.quota_used is not None:
        item.quota_used = body.quota_used
    if body.enabled is not None:
        item.enabled = body.enabled
    db.commit()
    db.refresh(item)
    return item


@router.delete("/keys/{key_id}")
def delete_key(
    key_id: int,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    item = db.get(ApiKey, key_id)
    if not item:
        raise HTTPException(status_code=404, detail="秘钥不存在")
    db.delete(item)
    db.commit()
    return {"ok": True}


@router.get("/usage", response_model=list[UsageLogOut])
def list_usage(
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
    limit: int = Query(default=100, ge=1, le=500),
    api_key_id: int | None = None,
) -> list[UsageLog]:
    q = db.query(UsageLog).order_by(UsageLog.id.desc())
    if api_key_id is not None:
        q = q.filter(UsageLog.api_key_id == api_key_id)
    return q.limit(limit).all()
