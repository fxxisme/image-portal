from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.auth import get_current_api_key
from app.database import get_db
from app.models import ApiKey, Conversation, GeneratedImage
from app.schemas import ConversationCreate, ConversationDetail, ConversationOut
from app.services.media import image_content_url
from app.services.messages import message_to_out

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.get("", response_model=list[ConversationOut])
def list_conversations(
    api_key: ApiKey = Depends(get_current_api_key),
    db: Session = Depends(get_db),
) -> list[Conversation]:
    return (
        db.query(Conversation)
        .filter(Conversation.api_key_id == api_key.id)
        .order_by(Conversation.updated_at.desc())
        .all()
    )


@router.post("", response_model=ConversationOut)
def create_conversation(
    body: ConversationCreate,
    api_key: ApiKey = Depends(get_current_api_key),
    db: Session = Depends(get_db),
) -> Conversation:
    item = Conversation(api_key_id=api_key.id, title=body.title or "新对话")
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get("/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    conversation_id: int,
    api_key: ApiKey = Depends(get_current_api_key),
    db: Session = Depends(get_db),
) -> ConversationDetail:
    item = (
        db.query(Conversation)
        .options(joinedload(Conversation.messages))
        .filter(Conversation.id == conversation_id, Conversation.api_key_id == api_key.id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="会话不存在")
    message_ids = [message.id for message in item.messages]
    image_rows = (
        db.query(GeneratedImage)
        .filter(
            GeneratedImage.api_key_id == api_key.id,
            GeneratedImage.conversation_id == item.id,
            GeneratedImage.message_id.in_(message_ids),
        )
        .order_by(GeneratedImage.id.asc())
        .all()
        if message_ids
        else []
    )
    images_by_message: dict[int, list[GeneratedImage]] = {}
    for image in image_rows:
        if image.message_id is not None:
            images_by_message.setdefault(image.message_id, []).append(image)

    messages = []
    for message in item.messages:
        output = message_to_out(message)
        # 会话详情以生成图片表为唯一来源，避免旧消息字段中的脏数据在刷新后回放。
        output.image_urls = (
            [
                image_content_url(image)
                for image in images_by_message.get(message.id, [])[: message.cost]
            ]
            if message.role == "assistant"
            else []
        )
        messages.append(output)

    return ConversationDetail(
        id=item.id,
        title=item.title,
        created_at=item.created_at,
        updated_at=item.updated_at,
        messages=messages,
    )


@router.patch("/{conversation_id}", response_model=ConversationOut)
def rename_conversation(
    conversation_id: int,
    body: ConversationCreate,
    api_key: ApiKey = Depends(get_current_api_key),
    db: Session = Depends(get_db),
) -> Conversation:
    item = (
        db.query(Conversation)
        .filter(Conversation.id == conversation_id, Conversation.api_key_id == api_key.id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="会话不存在")
    item.title = body.title
    item.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/{conversation_id}")
def delete_conversation(
    conversation_id: int,
    api_key: ApiKey = Depends(get_current_api_key),
    db: Session = Depends(get_db),
) -> dict:
    item = (
        db.query(Conversation)
        .filter(Conversation.id == conversation_id, Conversation.api_key_id == api_key.id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="会话不存在")
    db.delete(item)
    db.commit()
    return {"ok": True}
