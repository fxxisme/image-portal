from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_api_key
from app.database import get_db
from app.models import ApiKey, Conversation, Message, UsageLog
from app.schemas import EditRequest, GenerateRequest, GenerateResponse
from app.services.media import persist_generated_images
from app.services.messages import dump_urls, message_to_out
from app.services.settings import get_or_create_settings
from app.services.upstream import UpstreamError, images_edits, images_generations

router = APIRouter(prefix="/api", tags=["images"])


def _get_owned_conversation(db: Session, api_key: ApiKey, conversation_id: int) -> Conversation:
    item = (
        db.query(Conversation)
        .filter(Conversation.id == conversation_id, Conversation.api_key_id == api_key.id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="会话不存在")
    return item


def _ensure_quota(api_key: ApiKey, n: int) -> None:
    if api_key.quota_remaining < n:
        raise HTTPException(
            status_code=402,
            detail=f"额度不足：剩余 {api_key.quota_remaining} 张，本次需要 {n} 张",
        )


def _touch(conv: Conversation) -> None:
    conv.updated_at = datetime.now(timezone.utc)


def _maybe_title(conv: Conversation, prompt: str) -> None:
    if conv.title in ("", "新对话") and prompt.strip():
        conv.title = prompt.strip()[:40]


@router.post("/generate", response_model=GenerateResponse)
async def generate(
    body: GenerateRequest,
    api_key: ApiKey = Depends(get_current_api_key),
    db: Session = Depends(get_db),
) -> GenerateResponse:
    conv = _get_owned_conversation(db, api_key, body.conversation_id)
    _ensure_quota(api_key, body.n)

    sys = get_or_create_settings(db)
    model = (body.model or sys.default_model or "gpt-image-2").strip()
    user_msg = Message(
        conversation_id=conv.id,
        role="user",
        content=body.prompt,
        action="generate",
        cost=0,
        model=model,
    )
    db.add(user_msg)
    db.flush()

    try:
        urls = await images_generations(db, prompt=body.prompt, model=model, n=body.n)
    except UpstreamError as exc:
        db.add(
            UsageLog(
                api_key_id=api_key.id,
                conversation_id=conv.id,
                action="generate",
                cost=0,
                model=model,
                success=False,
                detail=str(exc),
            )
        )
        db.commit()
        raise HTTPException(status_code=502, detail={"message": str(exc), "body": exc.body}) from exc

    cost = len(urls) or body.n
    api_key.quota_used += cost
    assistant = Message(
        conversation_id=conv.id,
        role="assistant",
        content=f"已生成 {len(urls)} 张图片",
        action="generate",
        image_urls=dump_urls(urls),
        cost=cost,
        model=model,
    )
    db.add(assistant)
    db.flush()

    stored = await persist_generated_images(
        db,
        api_key_id=api_key.id,
        conversation_id=conv.id,
        message_id=assistant.id,
        action="generate",
        prompt=body.prompt,
        urls=urls,
    )
    assistant.image_urls = dump_urls(stored)

    db.add(
        UsageLog(
            api_key_id=api_key.id,
            conversation_id=conv.id,
            action="generate",
            cost=cost,
            model=model,
            success=True,
            detail=None,
        )
    )
    _maybe_title(conv, body.prompt)
    _touch(conv)
    db.commit()
    db.refresh(user_msg)
    db.refresh(assistant)
    db.refresh(api_key)

    return GenerateResponse(
        conversation_id=conv.id,
        user_message=message_to_out(user_msg),
        assistant_message=message_to_out(assistant),
        quota_remaining=api_key.quota_remaining,
    )


@router.post("/edit", response_model=GenerateResponse)
async def edit(
    body: EditRequest,
    api_key: ApiKey = Depends(get_current_api_key),
    db: Session = Depends(get_db),
) -> GenerateResponse:
    conv = _get_owned_conversation(db, api_key, body.conversation_id)
    _ensure_quota(api_key, body.n)

    sys = get_or_create_settings(db)
    model = (body.model or sys.default_model or "gpt-image-2").strip()
    user_msg = Message(
        conversation_id=conv.id,
        role="user",
        content=body.prompt,
        action="edit",
        ref_image_url=body.image_url,
        cost=0,
        model=model,
    )
    db.add(user_msg)
    db.flush()

    try:
        urls = await images_edits(
            db,
            prompt=body.prompt,
            image_url=body.image_url,
            model=model,
            n=body.n,
        )
    except UpstreamError as exc:
        db.add(
            UsageLog(
                api_key_id=api_key.id,
                conversation_id=conv.id,
                action="edit",
                cost=0,
                model=model,
                success=False,
                detail=str(exc),
            )
        )
        db.commit()
        raise HTTPException(status_code=502, detail={"message": str(exc), "body": exc.body}) from exc

    cost = len(urls) or body.n
    api_key.quota_used += cost
    assistant = Message(
        conversation_id=conv.id,
        role="assistant",
        content=f"已编辑生成 {len(urls)} 张图片",
        action="edit",
        ref_image_url=body.image_url,
        image_urls=dump_urls(urls),
        cost=cost,
        model=model,
    )
    db.add(assistant)
    db.flush()

    stored = await persist_generated_images(
        db,
        api_key_id=api_key.id,
        conversation_id=conv.id,
        message_id=assistant.id,
        action="edit",
        prompt=body.prompt,
        urls=urls,
    )
    assistant.image_urls = dump_urls(stored)

    db.add(
        UsageLog(
            api_key_id=api_key.id,
            conversation_id=conv.id,
            action="edit",
            cost=cost,
            model=model,
            success=True,
            detail=None,
        )
    )
    _maybe_title(conv, body.prompt)
    _touch(conv)
    db.commit()
    db.refresh(user_msg)
    db.refresh(assistant)
    db.refresh(api_key)

    return GenerateResponse(
        conversation_id=conv.id,
        user_message=message_to_out(user_msg),
        assistant_message=message_to_out(assistant),
        quota_remaining=api_key.quota_remaining,
    )
