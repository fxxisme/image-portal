from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 明文只在创建时返回一次；库内仅存 hash + 前缀便于识别
    key_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    # 总额度 / 已用（张）
    quota_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quota_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    conversations: Mapped[list["Conversation"]] = relationship(back_populates="api_key")
    usage_logs: Mapped[list["UsageLog"]] = relationship(back_populates="api_key")
    generated_images: Mapped[list["GeneratedImage"]] = relationship(back_populates="api_key")

    @property
    def quota_remaining(self) -> int:
        return max(0, self.quota_total - self.quota_used)


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    api_key_id: Mapped[int] = mapped_column(ForeignKey("api_keys.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="新对话")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    api_key: Mapped["ApiKey"] = relationship(back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.id",
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    # user | assistant
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    # 用户文本 prompt / 助手说明
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # generate | edit
    action: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # 参考图 URL（改图时）
    ref_image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 生成结果图 URL 列表 JSON 字符串
    image_urls: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 本次消耗张数
    cost: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")


class UsageLog(Base):
    __tablename__ = "usage_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    api_key_id: Mapped[int] = mapped_column(ForeignKey("api_keys.id", ondelete="CASCADE"), index=True)
    conversation_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    cost: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    api_key: Mapped["ApiKey"] = relationship(back_populates="usage_logs")


class SystemSetting(Base):
    """单例配置（id 固定为 1），上游连接信息由管理端维护。"""

    __tablename__ = "system_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    upstream_base_url: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    upstream_api_key: Mapped[str] = mapped_column(Text, nullable=False, default="")
    default_model: Mapped[str] = mapped_column(String(128), nullable=False, default="gpt-image-2")
    response_format: Mapped[str] = mapped_column(String(32), nullable=False, default="url")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class GeneratedImage(Base):
    """用户（秘钥）生成图本地持久化记录。"""

    __tablename__ = "generated_images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    api_key_id: Mapped[int] = mapped_column(ForeignKey("api_keys.id", ondelete="CASCADE"), index=True)
    conversation_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # generate | edit
    action: Mapped[str] = mapped_column(String(32), nullable=False, default="generate")
    prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # 相对 media 根目录，如 {api_key_id}/{uuid}.png
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    # 对外访问路径 /media/...
    public_url: Mapped[str] = mapped_column(String(512), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    api_key: Mapped["ApiKey"] = relationship(back_populates="generated_images")


class GuestTrial(Base):
    """游客免费试用记录：指纹 → ApiKey 映射，防重复领取。"""

    __tablename__ = "guest_trials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fingerprint_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    api_key_id: Mapped[int] = mapped_column(ForeignKey("api_keys.id", ondelete="CASCADE"), index=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    api_key: Mapped["ApiKey"] = relationship()
