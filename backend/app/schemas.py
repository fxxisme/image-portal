from datetime import datetime

from pydantic import BaseModel, Field


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


# ---------- System settings (admin) ----------
class SystemSettingsOut(BaseModel):
    upstream_base_url: str
    # 脱敏展示；完整 key 不回传
    upstream_api_key_masked: str
    has_upstream_api_key: bool
    default_model: str
    response_format: str
    updated_at: datetime | None = None


class SystemSettingsUpdate(BaseModel):
    upstream_base_url: str | None = Field(default=None, max_length=512)
    # 传空或不传 = 不修改现有 key
    upstream_api_key: str | None = None
    default_model: str | None = Field(default=None, max_length=128)
    response_format: str | None = Field(default=None, max_length=32)


# ---------- Admin keys ----------
class ApiKeyCreate(BaseModel):
    name: str = Field(default="", max_length=128)
    quota_total: int = Field(default=10, ge=0)


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


class EditRequest(BaseModel):
    conversation_id: int
    prompt: str = Field(min_length=1)
    # 要编辑的参考图 URL（通常来自上一轮 assistant）
    image_url: str = Field(min_length=1)
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
