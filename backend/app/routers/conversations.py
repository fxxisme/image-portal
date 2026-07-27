from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.auth import get_current_api_key
from app.database import get_db
from app.models import ApiKey, Conversation
from app.schemas import ConversationCreate, ConversationDetail, ConversationOut
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
    return ConversationDetail(
        id=item.id,
        title=item.title,
        created_at=item.created_at,
        updated_at=item.updated_at,
        messages=[message_to_out(m) for m in item.messages],
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
