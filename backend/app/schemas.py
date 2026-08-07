from datetime import datetime

from pydantic import BaseModel, Field, field_validator


# ---------- Auth ----------
class UserLoginRequest(BaseModel):
    api_key: str = Field(min_length=8)


class AdminLoginRequest(BaseModel):
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MeResponse(BaseModel):
    id: int
    name: str
    key_prefix: str
    quota_total: int
    quota_used: int
    quota_remaining: int
    enabled: bool
    default_model: str = ""
    text_to_image_models: list[str] = Field(default_factory=list)
    image_to_image_models: list[str] = Field(default_factory=list)


# ---------- System settings (admin) ----------
class SystemSettingsOut(BaseModel):
    upstream_base_url: str
    # 脱敏展示；完整 key 不回传
    upstream_api_key_masked: str
    has_upstream_api_key: bool
    default_model: str
    text_to_image_models: list[str]
    image_to_image_models: list[str]
    response_format: str
    webdav_url: str
    webdav_username: str
    webdav_password_masked: str
    has_webdav_password: bool
    webdav_path: str
    webdav_public_base_url: str
    updated_at: datetime | None = None


class SystemSettingsUpdate(BaseModel):
    upstream_base_url: str | None = Field(default=None, max_length=512)
    # 传空或不传 = 不修改现有 key
    upstream_api_key: str | None = None
    default_model: str | None = Field(default=None, max_length=128)
    text_to_image_models: list[str] | None = None
    image_to_image_models: list[str] | None = None
    response_format: str | None = Field(default=None, max_length=32)
    webdav_url: str | None = Field(default=None, max_length=512)
    webdav_username: str | None = Field(default=None, max_length=256)
    # 传空或不传 = 不修改现有密码
    webdav_password: str | None = None
    webdav_path: str | None = Field(default=None, max_length=512)
    webdav_public_base_url: str | None = Field(default=None, max_length=512)


class UpstreamModelsOut(BaseModel):
    models: list[str]


# ---------- Admin keys ----------
class ApiKeyCreate(BaseModel):
    name: str = Field(default="", max_length=128)
    quota_total: int = Field(default=10, ge=0)
    # 留空时由服务端生成随机密钥。
    api_key: str | None = Field(default=None, min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")

    @field_validator("api_key", mode="before")
    @classmethod
    def normalize_api_key(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, str):
            return value
        return value.strip() or None


class ApiKeyUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    quota_total: int | None = Field(default=None, ge=0)
    enabled: bool | None = None
    # 增量调整已用（可选，谨慎）
    quota_used: int | None = Field(default=None, ge=0)


class ApiKeyOut(BaseModel):
    id: int
    name: str
    key_prefix: str
    quota_total: int
    quota_used: int
    quota_remaining: int
    enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ApiKeyCreated(ApiKeyOut):
    # 仅创建时返回一次明文
    api_key: str


class UsageLogOut(BaseModel):
    id: int
    api_key_id: int
    conversation_id: int | None
    action: str
    cost: int
    model: str | None
    success: bool
    detail: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------- Conversations ----------
class ConversationCreate(BaseModel):
    title: str = Field(default="新对话", max_length=200)


class ConversationOut(BaseModel):
    id: int
    title: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    action: str | None
    ref_image_url: str | None
    image_urls: list[str] = []
    cost: int
    model: str | None
    created_at: datetime


class ConversationDetail(ConversationOut):
    messages: list[MessageOut] = []


# ---------- Generate / Edit ----------
class GenerateRequest(BaseModel):
    conversation_id: int
    prompt: str = Field(min_length=1)
    n: int = Field(default=1, ge=1, le=4)
    model: str | None = None


class EditImage(BaseModel):
    url: str = Field(min_length=1)


class EditRequest(BaseModel):
    conversation_id: int
    prompt: str = Field(min_length=1)
    images: list[EditImage] = Field(min_length=1, max_length=4)
    n: int = Field(default=1, ge=1, le=4)
    model: str | None = None


class GenerateResponse(BaseModel):
    conversation_id: int
    user_message: MessageOut
    assistant_message: MessageOut
    quota_remaining: int


# ---------- Gallery ----------
class GalleryItemOut(BaseModel):
    id: int
    public_url: str
    prompt: str
    action: str
    conversation_id: int | None = None
    created_at: datetime


class GalleryListOut(BaseModel):
    total: int
    items: list[GalleryItemOut]


class AdminGalleryItemOut(GalleryItemOut):
    api_key_id: int
    api_key_name: str


class AdminGalleryListOut(BaseModel):
    total: int
    items: list[AdminGalleryItemOut]
