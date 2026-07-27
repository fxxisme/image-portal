import json

from app.models import Message
from app.schemas import MessageOut


def message_to_out(msg: Message) -> MessageOut:
    urls: list[str] = []
    if msg.image_urls:
        try:
            parsed = json.loads(msg.image_urls)
            if isinstance(parsed, list):
                urls = [str(u) for u in parsed]
        except json.JSONDecodeError:
            urls = []
    return MessageOut(
        id=msg.id,
        role=msg.role,
        content=msg.content,
        action=msg.action,
        ref_image_url=msg.ref_image_url,
        image_urls=urls,
        cost=msg.cost,
        model=msg.model,
        created_at=msg.created_at,
    )


def dump_urls(urls: list[str]) -> str:
    return json.dumps(urls, ensure_ascii=False)
