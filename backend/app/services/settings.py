import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import SystemSetting

DEFAULT_TEXT_TO_IMAGE_MODELS = ["gpt-image-2", "grok-imagine-image"]
DEFAULT_IMAGE_TO_IMAGE_MODELS = ["gpt-image-2"]


def _clean_model_names(value, fallback: list[str]) -> list[str]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            value = []
    if not isinstance(value, list):
        value = []

    result: list[str] = []
    for item in value:
        name = str(item).strip()
        if name and name not in result:
            result.append(name)
    return result or list(fallback)


def _dump_model_names(value, fallback: list[str]) -> str:
    return json.dumps(_clean_model_names(value, fallback), ensure_ascii=False)


def get_text_to_image_models(row: SystemSetting) -> list[str]:
    return _clean_model_names(row.text_to_image_models, DEFAULT_TEXT_TO_IMAGE_MODELS)


def get_image_to_image_models(row: SystemSetting) -> list[str]:
    return _clean_model_names(row.image_to_image_models, DEFAULT_IMAGE_TO_IMAGE_MODELS)


def get_or_create_settings(db: Session) -> SystemSetting:
    row = db.get(SystemSetting, 1)
    if row is None:
        row = SystemSetting(
            id=1,
            upstream_base_url="",
            upstream_api_key="",
            default_model="gpt-image-2",
            text_to_image_models=json.dumps(DEFAULT_TEXT_TO_IMAGE_MODELS),
            image_to_image_models=json.dumps(DEFAULT_IMAGE_TO_IMAGE_MODELS),
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
    text_to_image_models: list[str] | None = None,
    image_to_image_models: list[str] | None = None,
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
    if text_to_image_models is not None:
        row.text_to_image_models = _dump_model_names(
            text_to_image_models, DEFAULT_TEXT_TO_IMAGE_MODELS
        )
    if image_to_image_models is not None:
        row.image_to_image_models = _dump_model_names(
            image_to_image_models, DEFAULT_IMAGE_TO_IMAGE_MODELS
        )
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
