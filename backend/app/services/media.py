"""将上游返回的图片落盘，供图库持久化访问。"""

from __future__ import annotations

import base64
import logging
import mimetypes
import re
import uuid
from pathlib import Path
from urllib.parse import urlparse

import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import GeneratedImage

logger = logging.getLogger(__name__)

_DATA_URL_RE = re.compile(r"^data:(image/[\w.+-]+);base64,(.+)$", re.IGNORECASE | re.DOTALL)


def media_root() -> Path:
    root = Path(get_settings().media_dir).expanduser()
    if not root.is_absolute():
        root = Path.cwd() / root
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def _ext_from_content_type(ct: str | None) -> str:
    if not ct:
        return ".png"
    ct = ct.split(";")[0].strip().lower()
    ext = mimetypes.guess_extension(ct) or ""
    if ext == ".jpe":
        ext = ".jpg"
    if ext in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        return ".jpg" if ext == ".jpeg" else ext
    return ".png"


async def _fetch_bytes(url: str) -> tuple[bytes, str]:
    """返回 (bytes, 建议扩展名)。"""
    m = _DATA_URL_RE.match(url.strip())
    if m:
        mime, b64 = m.group(1), m.group(2)
        try:
            raw = base64.b64decode(b64, validate=False)
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"无效 data URL: {exc}") from exc
        return raw, _ext_from_content_type(mime)

    if url.startswith("/media/"):
        # 本站已有文件，复制一份归属当前记录也可直接引用；这里读本地
        rel = url[len("/media/") :].lstrip("/\\")
        path = (media_root() / rel).resolve()
        try:
            path.relative_to(media_root())
        except ValueError as exc:
            raise ValueError("非法 media 路径") from exc
        if not path.is_file():
            raise ValueError("本地 media 文件不存在")
        return path.read_bytes(), path.suffix or ".png"

    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
        res = await client.get(url)
        res.raise_for_status()
        ct = res.headers.get("content-type")
        ext = _ext_from_content_type(ct)
        # 尝试从 URL 猜扩展名
        path_ext = Path(urlparse(url).path).suffix.lower()
        if path_ext in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
            ext = ".jpg" if path_ext == ".jpeg" else path_ext
        return res.content, ext


async def persist_generated_images(
    db: Session,
    *,
    api_key_id: int,
    conversation_id: int | None,
    message_id: int | None,
    action: str,
    prompt: str,
    urls: list[str],
) -> list[str]:
    """下载/解码 urls 写入 media，写 GeneratedImage，返回可展示的 public_url 列表。"""
    if not urls:
        return []

    root = media_root()
    owner_dir = root / str(api_key_id)
    owner_dir.mkdir(parents=True, exist_ok=True)

    public_urls: list[str] = []
    for src in urls:
        try:
            raw, ext = await _fetch_bytes(src)
            if not raw:
                raise ValueError("空文件")
            name = f"{uuid.uuid4().hex}{ext}"
            rel = f"{api_key_id}/{name}"
            dest = owner_dir / name
            dest.write_bytes(raw)
            public = f"/media/{rel.replace(chr(92), '/')}"
            row = GeneratedImage(
                api_key_id=api_key_id,
                conversation_id=conversation_id,
                message_id=message_id,
                action=action,
                prompt=(prompt or "")[:4000],
                storage_path=rel.replace("\\", "/"),
                public_url=public,
                source_url=(src[:2000] if not src.startswith("data:") else None),
            )
            db.add(row)
            public_urls.append(public)
        except Exception:
            logger.exception("persist image failed api_key=%s src_prefix=%s", api_key_id, src[:80])
            # 落盘失败仍返回原 URL，对话可用；图库可能缺这条
            public_urls.append(src)

    db.flush()
    return public_urls
