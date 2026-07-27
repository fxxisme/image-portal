from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import create_token, find_api_key_by_raw, get_current_api_key
from app.config import get_settings
from app.database import get_db
from app.models import ApiKey
from app.schemas import MeResponse, TokenResponse, UserLoginRequest
from app.services.settings import get_or_create_settings

router = APIRouter(prefix="/api/auth", tags=["auth"])
settings = get_settings()


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
