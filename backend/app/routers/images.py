import base64
from datetime import datetime, timezone
import logging
import re
from urllib.parse import parse_qs, urlparse

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_api_key
from app.database import get_db
from app.models import ApiKey, Conversation, GeneratedImage, Message, UsageLog
from app.schemas import EditRequest, GenerateRequest, GenerateResponse
from app.services.media import (
    has_valid_image_signature,
    load_generated_image_bytes,
    persist_generated_images,
)
from app.services.messages import dump_urls, message_to_out
from app.services.settings import (
    get_image_to_image_models,
    get_or_create_settings,
    get_text_to_image_models,
)
from app.services.upstream import UpstreamError, images_edits, images_generations

router = APIRouter(prefix="/api", tags=["images"])
logger = logging.getLogger(__name__)
_GALLERY_CONTENT_PATH_RE = re.compile(r"^/api/gallery/(\d+)/content$")


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


def _upstream_error_detail(exc: UpstreamError) -> str:
    message = _upstream_error_message(exc.body)
    if exc.status_code and message:
        return f"上游服务错误（HTTP {exc.status_code}）：{message}"
    if exc.status_code:
        return f"上游服务错误（HTTP {exc.status_code}）"
    return str(exc)


def _upstream_error_message(body: object) -> str:
    """提取上游返回的简短错误文本，避免将完整响应直接展示给用户。"""
    if isinstance(body, str):
        message = body
    elif isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict):
            message = error.get("message") or error.get("detail") or ""
        elif isinstance(error, str):
            message = error
        else:
            message = body.get("message") or body.get("detail") or ""
    else:
        message = ""

    if not isinstance(message, str):
        return ""
    return " ".join(message.split())[:500]


def _resolve_edit_image(db: Session, api_key: ApiKey, image_url: str) -> str:
    """将图库受控地址转为 data URL，供上游改图接口读取。"""
    parsed = urlparse(image_url)
    match = _GALLERY_CONTENT_PATH_RE.match(parsed.path)
    if not match:
        return image_url
    row = (
        db.query(GeneratedImage)
        .filter(GeneratedImage.id == int(match.group(1)), GeneratedImage.api_key_id == api_key.id)
        .first()
    )
    sig = parse_qs(parsed.query).get("sig", [""])[0]
    if not row or not has_valid_image_signature(row, sig):
        raise HTTPException(status_code=404, detail="参考图不存在")
    try:
        raw, media_type = load_generated_image_bytes(db, row)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="参考图文件不存在") from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail="参考图暂时无法读取") from exc
    return f"data:{media_type};base64,{base64.b64encode(raw).decode()}"


@router.post("/generate", response_model=GenerateResponse)
async def generate(
    body: GenerateRequest,
    api_key: ApiKey = Depends(get_current_api_key),
    db: Session = Depends(get_db),
) -> GenerateResponse:
    conv = _get_owned_conversation(db, api_key, body.conversation_id)
    _ensure_quota(api_key, body.n)

    sys = get_or_create_settings(db)
    available_models = get_text_to_image_models(sys)
    requested_model = (body.model or "").strip()
    if requested_model and requested_model not in available_models:
        raise HTTPException(status_code=400, detail="所选文生图模型不可用")
    model = requested_model or (
        sys.default_model if sys.default_model in available_models else available_models[0]
    )
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
        logger.warning("image generation upstream error: %s body=%r", exc, exc.body)
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
        raise HTTPException(status_code=502, detail=_upstream_error_detail(exc)) from exc

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
    if len(stored) != len(urls):
        assistant.content = f"已生成 {len(urls)} 张图片，其中 {len(stored)} 张已保存并可展示"

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
    available_models = get_image_to_image_models(sys)
    model = (body.model or available_models[0]).strip()
    if model not in available_models:
        raise HTTPException(status_code=400, detail="所选图生图模型不可用")
    image_urls = [image.url for image in body.images]
    user_msg = Message(
        conversation_id=conv.id,
        role="user",
        content=body.prompt,
        action="edit",
        ref_image_url=image_urls[0],
        cost=0,
        model=model,
    )
    db.add(user_msg)
    db.flush()

    resolved_image_urls = [
        _resolve_edit_image(db, api_key, image_url) for image_url in image_urls
    ]
    try:
        urls = await images_edits(
            db,
            prompt=body.prompt,
            image_urls=resolved_image_urls,
            model=model,
            n=body.n,
        )
    except UpstreamError as exc:
        logger.warning("image edit upstream error: %s body=%r", exc, exc.body)
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
        raise HTTPException(status_code=502, detail=_upstream_error_detail(exc)) from exc

    cost = len(urls) or body.n
    api_key.quota_used += cost
    assistant = Message(
        conversation_id=conv.id,
        role="assistant",
        content=f"已编辑生成 {len(urls)} 张图片",
        action="edit",
        ref_image_url=image_urls[0],
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
    if len(stored) != len(urls):
        assistant.content = f"已编辑生成 {len(urls)} 张图片，其中 {len(stored)} 张已保存并可展示"

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
