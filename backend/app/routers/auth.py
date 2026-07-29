from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import create_token, find_api_key_by_raw, get_current_api_key, hash_api_key
from app.config import get_settings
from app.database import get_db
from app.models import ApiKey, GuestTrial
from app.schemas import (
    GuestRegisterRequest,
    GuestRegisterResponse,
    MeResponse,
    TokenResponse,
    UserLoginRequest,
)
from app.services.settings import get_or_create_settings

import hashlib
import secrets

router = APIRouter(prefix="/api/auth", tags=["auth"])
settings = get_settings()


def _make_fingerprint(ip: str, ua: str, device_id: str) -> str:
    raw = f"{ip}|{ua[:256]}|{device_id}"
    return hashlib.sha256(raw.encode()).hexdigest()


@router.post("/guest-register", response_model=GuestRegisterResponse)
def guest_register(
    body: GuestRegisterRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> GuestRegisterResponse:
    ip = request.client.host if request.client else "127.0.0.1"
    ua = request.headers.get("user-agent", "")
    fingerprint = _make_fingerprint(ip, ua, body.device_id)

    existing = db.query(GuestTrial).filter(GuestTrial.fingerprint_hash == fingerprint).first()
    if existing:
        api_key = db.get(ApiKey, existing.api_key_id)
        if not api_key or not api_key.enabled:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="试用账号已被禁用")
        token = create_token(subject=str(api_key.id), role="user", expire_hours=settings.user_token_expire_hours)
        return GuestRegisterResponse(access_token=token, is_new=False)

    # 首次访问：创建游客 ApiKey + 试用记录
    raw_key = "guest-" + secrets.token_urlsafe(24)
    api_key = ApiKey(
        key_hash=hash_api_key(raw_key),
        key_prefix=raw_key[:10],
        name="访客",
        quota_total=2,
        quota_used=0,
        enabled=True,
    )
    db.add(api_key)
    db.flush()

    trial = GuestTrial(
        fingerprint_hash=fingerprint,
        api_key_id=api_key.id,
        ip_address=ip,
        user_agent=ua[:512],
    )
    db.add(trial)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        # 并发冲突：另一个请求已插入同指纹记录
        existing = db.query(GuestTrial).filter(GuestTrial.fingerprint_hash == fingerprint).first()
        if existing:
            api_key = db.get(ApiKey, existing.api_key_id)
            if not api_key or not api_key.enabled:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="试用账号已被禁用")
            token = create_token(subject=str(api_key.id), role="user", expire_hours=settings.user_token_expire_hours)
            return GuestRegisterResponse(access_token=token, is_new=False)
        raise  # 理论上不会到这里

    token = create_token(subject=str(api_key.id), role="user", expire_hours=settings.user_token_expire_hours)
    return GuestRegisterResponse(access_token=token, is_new=True)


@router.post("/login", response_model=TokenResponse)
def user_login(body: UserLoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    raw = body.api_key.strip()
    api_key = find_api_key_by_raw(db, raw)
    if not api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="秘钥无效或已禁用")
    token = create_token(
        subject=str(api_key.id),
        role="user",
        expire_hours=settings.user_token_expire_hours,
    )
    return TokenResponse(access_token=token)


@router.get("/me", response_model=MeResponse)
def me(
    api_key: ApiKey = Depends(get_current_api_key),
    db: Session = Depends(get_db),
) -> MeResponse:
    sys = get_or_create_settings(db)
    return MeResponse(
        id=api_key.id,
        name=api_key.name,
        key_prefix=api_key.key_prefix,
        quota_total=api_key.quota_total,
        quota_used=api_key.quota_used,
        quota_remaining=api_key.quota_remaining,
        enabled=api_key.enabled,
        default_model=sys.default_model or "gpt-image-2",
    )
