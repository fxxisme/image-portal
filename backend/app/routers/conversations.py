from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload

from app.auth import get_current_api_key
from app.database import get_db
from app.models import ApiKey, Conversation, GeneratedImage, Message
from app.schemas import ConversationCreate, ConversationDetail, ConversationOut
from app.services.media import delete_generated_image, image_content_url
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
        .options(selectinload(Conversation.messages).selectinload(Message.generated_images))
        .filter(Conversation.id == conversation_id, Conversation.api_key_id == api_key.id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="会话不存在")
    messages = []
    for message in item.messages:
        output = message_to_out(message)
        # 只回放当前助手消息的直属图片，避免跨会话或孤儿记录参与匹配。
        output.image_urls = (
            [image_content_url(image) for image in message.generated_images[: message.cost]]
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
    image_rows = (
        db.query(GeneratedImage)
        .filter(
            GeneratedImage.api_key_id == api_key.id,
            GeneratedImage.conversation_id == item.id,
        )
        .all()
    )
    for image in image_rows:
        delete_generated_image(db, image)
        db.delete(image)
    db.delete(item)
    db.commit()
    return {"ok": True}
