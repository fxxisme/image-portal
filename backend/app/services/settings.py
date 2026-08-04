from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import SystemSetting


def get_or_create_settings(db: Session) -> SystemSetting:
    row = db.get(SystemSetting, 1)
    if row is None:
        row = SystemSetting(
            id=1,
            upstream_base_url="",
            upstream_api_key="",
            default_model="gpt-image-2",
            response_format="url",
            webdav_url="",
            webdav_username="",
            webdav_password="",
            webdav_path="",
            webdav_public_base_url="",
        )
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def mask_api_key(raw: str) -> str:
    raw = raw or ""
    if not raw:
        return ""
    if len(raw) <= 8:
        return "*" * len(raw)
    return raw[:4] + "…" + raw[-4:]


def apply_settings_update(
    db: Session,
    *,
    upstream_base_url: str | None = None,
    upstream_api_key: str | None = None,
    default_model: str | None = None,
    response_format: str | None = None,
    webdav_url: str | None = None,
    webdav_username: str | None = None,
    webdav_password: str | None = None,
    webdav_path: str | None = None,
    webdav_public_base_url: str | None = None,
) -> SystemSetting:
    row = get_or_create_settings(db)
    if upstream_base_url is not None:
        row.upstream_base_url = upstream_base_url.strip()
    # 空字符串表示不改 key；只有非 None 且非空才更新
    if upstream_api_key is not None and upstream_api_key.strip() != "":
        row.upstream_api_key = upstream_api_key.strip()
    if default_model is not None:
        row.default_model = default_model.strip() or "gpt-image-2"
    if response_format is not None:
        row.response_format = response_format.strip() or "url"
    if webdav_url is not None:
        row.webdav_url = webdav_url.strip().rstrip("/")
    if webdav_username is not None:
        row.webdav_username = webdav_username.strip()
    if webdav_password is not None and webdav_password.strip() != "":
        row.webdav_password = webdav_password.strip()
    if webdav_path is not None:
        row.webdav_path = webdav_path.strip().strip("/")
    if webdav_public_base_url is not None:
        row.webdav_public_base_url = webdav_public_base_url.strip().rstrip("/")
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return row
