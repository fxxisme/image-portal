from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import ApiKey

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)
settings = get_settings()

Role = Literal["user", "admin"]


def hash_api_key(raw: str) -> str:
    return pwd_context.hash(raw)


def verify_api_key(raw: str, key_hash: str) -> bool:
    try:
        return pwd_context.verify(raw, key_hash)
    except Exception:
        return False


def create_token(subject: str, role: Role, expire_hours: int, extra: dict[str, Any] | None = None) -> str:
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=expire_hours),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效或过期的令牌") from exc


def get_bearer(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> str:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="需要 Bearer 令牌")
    return credentials.credentials


def get_current_api_key(
    token: str = Depends(get_bearer),
    db: Session = Depends(get_db),
) -> ApiKey:
    payload = decode_token(token)
    if payload.get("role") != "user":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="需要用户令牌")
    try:
        key_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="令牌无效") from exc

    api_key = db.get(ApiKey, key_id)
    if not api_key or not api_key.enabled:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="秘钥不存在或已禁用")
    return api_key


def require_admin(token: str = Depends(get_bearer)) -> dict[str, Any]:
    payload = decode_token(token)
    if payload.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return payload


def find_api_key_by_raw(db: Session, raw: str) -> ApiKey | None:
    """登录时遍历校验 hash（秘钥数量通常不大）。"""
    for item in db.query(ApiKey).filter(ApiKey.enabled.is_(True)).all():
        if verify_api_key(raw, item.key_hash):
            return item
    return None
