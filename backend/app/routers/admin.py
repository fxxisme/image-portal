import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.auth import create_token, find_api_key_by_raw, hash_api_key, require_admin
from app.config import get_settings
from app.database import get_db
from app.models import ApiKey, GeneratedImage, UsageLog
from app.schemas import (
    AdminLoginRequest,
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyOut,
    ApiKeyUpdate,
    AdminGalleryItemOut,
    AdminGalleryListOut,
    SystemSettingsOut,
    SystemSettingsUpdate,
    TokenResponse,
    UpstreamModelsOut,
    UsageLogOut,
)
from app.services.settings import (
    apply_settings_update,
    get_image_to_image_models,
    get_or_create_settings,
    get_text_to_image_models,
    mask_api_key,
)
from app.services.media import image_content_url, load_generated_image_bytes
from app.services.upstream import UpstreamError, fetch_upstream_models

router = APIRouter(prefix="/api/admin", tags=["admin"])
settings = get_settings()


def _settings_out(row) -> SystemSettingsOut:
    return SystemSettingsOut(
        upstream_base_url=row.upstream_base_url or "",
        upstream_api_key_masked=mask_api_key(row.upstream_api_key or ""),
        has_upstream_api_key=bool((row.upstream_api_key or "").strip()),
        default_model=row.default_model or "gpt-image-2",
        text_to_image_models=get_text_to_image_models(row),
        image_to_image_models=get_image_to_image_models(row),
        video_base_url=row.video_base_url or "",
        video_api_key_masked=mask_api_key(row.video_api_key or ""),
        has_video_api_key=bool((row.video_api_key or "").strip()),
        video_model=row.video_model or "",
        response_format=row.response_format or "url",
        webdav_url=row.webdav_url or "",
        webdav_username=row.webdav_username or "",
        webdav_password_masked=mask_api_key(row.webdav_password or ""),
        has_webdav_password=bool((row.webdav_password or "").strip()),
        webdav_path=row.webdav_path or "",
        webdav_public_base_url=row.webdav_public_base_url or "",
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
        text_to_image_models=body.text_to_image_models,
        image_to_image_models=body.image_to_image_models,
        video_base_url=body.video_base_url,
        video_api_key=body.video_api_key,
        video_model=body.video_model,
        response_format=body.response_format,
        webdav_url=body.webdav_url,
        webdav_username=body.webdav_username,
        webdav_password=body.webdav_password,
        webdav_path=body.webdav_path,
        webdav_public_base_url=body.webdav_public_base_url,
    )
    return _settings_out(row)


@router.get("/upstream-models", response_model=UpstreamModelsOut)
async def list_upstream_models(
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> UpstreamModelsOut:
    try:
        models = await fetch_upstream_models(db)
    except UpstreamError as exc:
        raise HTTPException(status_code=502, detail="上游模型服务暂时不可用，请稍后重试") from exc
    return UpstreamModelsOut(models=models)


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
    raw = body.api_key or "sk-" + secrets.token_urlsafe(32)
    if body.api_key and find_api_key_by_raw(db, raw, enabled_only=False):
        raise HTTPException(status_code=409, detail="自定义秘钥已存在")
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


@router.get("/images", response_model=AdminGalleryListOut)
def list_all_images(
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=48, ge=1, le=100),
    api_key_id: int | None = None,
) -> AdminGalleryListOut:
    q = db.query(GeneratedImage).order_by(GeneratedImage.id.desc())
    if api_key_id is not None:
        q = q.filter(GeneratedImage.api_key_id == api_key_id)
    total = q.count()
    rows = q.offset(offset).limit(limit).all()
    return AdminGalleryListOut(
        total=total,
        items=[
            AdminGalleryItemOut(
                id=row.id,
                public_url=image_content_url(row),
                prompt=row.prompt,
                action=row.action,
                conversation_id=row.conversation_id,
                created_at=row.created_at,
                api_key_id=row.api_key_id,
                api_key_name=row.api_key.name if row.api_key else "已删除用户",
            )
            for row in rows
        ],
    )


@router.get("/images/{image_id}/download")
def download_image(
    image_id: int,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Response:
    row = db.get(GeneratedImage, image_id)
    if not row:
        raise HTTPException(status_code=404, detail="图片不存在")
    try:
        content, media_type = load_generated_image_bytes(db, row)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="图片文件不存在") from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"读取图片失败: {exc}") from exc

    filename = Path(row.storage_path).name or f"image-{row.id}.png"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
