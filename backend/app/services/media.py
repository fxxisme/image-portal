"""将上游返回的图片落盘，供图库持久化访问。"""

from __future__ import annotations

import base64
import logging
import mimetypes
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from urllib.parse import urlparse

import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import GeneratedImage
from app.services.settings import get_or_create_settings

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


def _webdav_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{quote(path.strip('/'), safe='/')}"


def _webdav_storage_path(root_path: str, name: str) -> str:
    """WebDAV 不按用户隔离；未配置目录时使用 image-portal/YYYY-MM-DD。"""
    root = (root_path or "").strip("/") or "image-portal"
    date_dir = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    parts = [part for part in root.split("/") if part]
    parts.extend([date_dir, name])
    return "/".join(parts)


async def _upload_webdav(row, storage_path: str, raw: bytes) -> str:
    """创建目录并上传，返回用于浏览器展示的公开 URL。"""
    base_url = (row.webdav_url or "").strip().rstrip("/")
    if not base_url:
        raise ValueError("未配置 WebDAV 地址")

    auth = (row.webdav_username, row.webdav_password) if row.webdav_username else None
    directory = storage_path.rsplit("/", 1)[0] if "/" in storage_path else ""
    segments = [part for part in directory.split("/") if part]
    async with httpx.AsyncClient(timeout=120, auth=auth, follow_redirects=True) as client:
        current: list[str] = []
        for segment in segments:
            current.append(segment)
            response = await client.request("MKCOL", _webdav_url(base_url, "/".join(current)))
            if response.status_code not in (200, 201, 204, 301, 302, 405):
                raise ValueError(f"WebDAV 创建目录失败（HTTP {response.status_code}）")
        response = await client.put(
            _webdav_url(base_url, storage_path),
            content=raw,
            headers={"Content-Type": "application/octet-stream"},
        )
        if response.status_code not in (200, 201, 204):
            raise ValueError(f"WebDAV 上传失败（HTTP {response.status_code}）")

    public_base = (row.webdav_public_base_url or base_url).strip().rstrip("/")
    return _webdav_url(public_base, storage_path)


def delete_generated_image(db: Session, row: GeneratedImage) -> None:
    """删除图片记录对应的存储对象；失败时仍由调用方删除数据库记录。"""
    if row.storage_backend == "webdav":
        settings_row = get_or_create_settings(db)
        base_url = (settings_row.webdav_url or "").strip().rstrip("/")
        if not base_url:
            logger.warning("skip WebDAV delete for image=%s: WebDAV is no longer configured", row.id)
            return
        auth = (
            (settings_row.webdav_username, settings_row.webdav_password)
            if settings_row.webdav_username
            else None
        )
        try:
            with httpx.Client(timeout=30, auth=auth, follow_redirects=True) as client:
                response = client.delete(_webdav_url(base_url, row.storage_path))
            if response.status_code not in (200, 202, 204, 404):
                logger.warning("WebDAV delete failed image=%s status=%s", row.id, response.status_code)
        except httpx.HTTPError:
            logger.exception("WebDAV delete failed image=%s", row.id)
        return

    path = (media_root() / row.storage_path).resolve()
    try:
        path.relative_to(media_root())
        if path.is_file():
            path.unlink()
    except (OSError, ValueError):
        logger.exception("local media delete failed image=%s", row.id)


def load_generated_image_bytes(db: Session, row: GeneratedImage) -> tuple[bytes, str]:
    """按存储后端读取原图，供管理员受鉴权下载。"""
    if row.storage_backend == "webdav":
        settings_row = get_or_create_settings(db)
        base_url = (settings_row.webdav_url or "").strip().rstrip("/")
        if not base_url:
            raise FileNotFoundError("WebDAV 未配置")
        auth = (
            (settings_row.webdav_username, settings_row.webdav_password)
            if settings_row.webdav_username
            else None
        )
        with httpx.Client(timeout=120, auth=auth, follow_redirects=True) as client:
            response = client.get(_webdav_url(base_url, row.storage_path))
            response.raise_for_status()
        media_type = response.headers.get("content-type", "").split(";", 1)[0]
        if not media_type.startswith("image/"):
            media_type = mimetypes.guess_type(row.storage_path)[0] or "application/octet-stream"
        return response.content, media_type

    path = (media_root() / row.storage_path).resolve()
    try:
        path.relative_to(media_root())
    except ValueError as exc:
        raise FileNotFoundError("非法本地图片路径") from exc
    if not path.is_file():
        raise FileNotFoundError("本地图片不存在")
    return path.read_bytes(), mimetypes.guess_type(path.name)[0] or "application/octet-stream"


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
    """下载/解码结果图，优先上传 WebDAV，失败时回退本地 media。"""
    if not urls:
        return []

    webdav_settings = get_or_create_settings(db)
    use_webdav = bool((webdav_settings.webdav_url or "").strip())
    root = media_root()
    owner_dir = root / str(api_key_id)

    public_urls: list[str] = []
    for src in urls:
        try:
            raw, ext = await _fetch_bytes(src)
            if not raw:
                raise ValueError("空文件")
            name = f"{uuid.uuid4().hex}{ext}"
            rel = f"{api_key_id}/{name}"
            storage_backend = "local"
            public = f"/media/{rel.replace(chr(92), '/')}"
            if use_webdav:
                remote_path = _webdav_storage_path(webdav_settings.webdav_path, name)
                try:
                    public = await _upload_webdav(webdav_settings, remote_path, raw)
                    rel = remote_path
                    storage_backend = "webdav"
                except Exception:
                    logger.exception("WebDAV upload failed; falling back to local media api_key=%s", api_key_id)
            if storage_backend == "local":
                owner_dir.mkdir(parents=True, exist_ok=True)
                dest = owner_dir / name
                dest.write_bytes(raw)
            row = GeneratedImage(
                api_key_id=api_key_id,
                conversation_id=conversation_id,
                message_id=message_id,
                action=action,
                prompt=(prompt or "")[:4000],
                storage_path=rel.replace("\\", "/"),
                storage_backend=storage_backend,
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
