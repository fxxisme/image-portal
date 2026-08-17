import logging
import mimetypes
from collections import deque
from pathlib import PurePosixPath
from urllib.parse import quote, unquote, urlparse
from xml.etree import ElementTree

import httpx
from fastapi import APIRouter, HTTPException, Query, Response

from app.config import get_settings

router = APIRouter(prefix="/api/external-gallery", tags=["external-gallery"])
logger = logging.getLogger(__name__)

_IMAGE_EXTENSIONS = {".avif", ".bmp", ".gif", ".heic", ".jpeg", ".jpg", ".png", ".svg", ".webp"}
_DAV = "{DAV:}"


def _settings_or_503():
    settings = get_settings()
    base_url = settings.external_gallery_webdav_url.strip().rstrip("/")
    parsed = urlparse(base_url)
    if not base_url or parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=503, detail="外部图库尚未配置")
    return settings, base_url


def _normalise_path(value: str) -> str:
    path = unquote(value or "").replace("\\", "/").strip("/")
    if not path:
        return ""
    parts = PurePosixPath(path).parts
    if any(part in {"", ".", ".."} for part in parts):
        raise HTTPException(status_code=400, detail="图片路径无效")
    return "/".join(parts)


def _webdav_url(base_url: str, relative_path: str) -> str:
    relative_path = _normalise_path(relative_path)
    if not relative_path:
        return base_url
    return f"{base_url}/{quote(relative_path, safe='/')}"


def _relative_href(href: str, requested_url: str) -> str | None:
    path = unquote(urlparse(href).path or href).replace("\\", "/").rstrip("/")
    requested_path = unquote(urlparse(requested_url).path).replace("\\", "/").rstrip("/")
    if path == requested_path:
        return ""
    prefix = f"{requested_path}/"
    if path.startswith(prefix):
        return path[len(prefix) :].strip("/")
    return None


def _parse_multistatus(payload: bytes, requested_url: str) -> list[tuple[str, bool]]:
    try:
        root = ElementTree.fromstring(payload)
    except ElementTree.ParseError as exc:
        raise ValueError("WebDAV 返回了无效目录数据") from exc

    entries: list[tuple[str, bool]] = []
    for response in root.findall(f"{_DAV}response"):
        href = response.findtext(f"{_DAV}href")
        if not href:
            continue
        relative = _relative_href(href, requested_url)
        if not relative:
            continue
        is_directory = response.find(f".//{_DAV}resourcetype/{_DAV}collection") is not None
        entries.append((relative, is_directory))
    return entries


async def _list_directory(client: httpx.AsyncClient, base_url: str, path: str) -> list[tuple[str, bool]]:
    url = _webdav_url(base_url, path)
    response = await client.request("PROPFIND", url, headers={"Depth": "1"})
    if response.status_code not in {200, 207}:
        raise ValueError(f"WebDAV 目录读取失败（HTTP {response.status_code}）")
    return _parse_multistatus(response.content, url)


@router.get("/")
async def list_external_gallery() -> dict:
    settings, base_url = _settings_or_503()
    root_path = _normalise_path(settings.external_gallery_webdav_path)
    max_items = max(1, min(settings.external_gallery_max_items, 10000))
    max_depth = max(1, min(settings.external_gallery_max_depth, 32))
    auth = (
        (settings.external_gallery_webdav_username, settings.external_gallery_webdav_password)
        if settings.external_gallery_webdav_username
        else None
    )
    directories: dict[str, list[dict]] = {}
    pending = deque([(root_path, 0)])
    seen = {root_path}
    total = 0
    truncated = False

    try:
        async with httpx.AsyncClient(timeout=30, auth=auth, follow_redirects=True) as client:
            while pending and total < max_items:
                directory, depth = pending.popleft()
                for relative, is_directory in await _list_directory(client, base_url, directory):
                    full_path = _normalise_path(f"{directory}/{relative}" if directory else relative)
                    if is_directory:
                        if depth < max_depth and full_path not in seen:
                            seen.add(full_path)
                            pending.append((full_path, depth + 1))
                        continue
                    suffix = PurePosixPath(full_path).suffix.lower()
                    if suffix not in _IMAGE_EXTENSIONS:
                        continue
                    group = str(PurePosixPath(full_path).parent)
                    group = "" if group == "." else group
                    directories.setdefault(group, []).append(
                        {
                            "path": full_path,
                            "name": PurePosixPath(full_path).name,
                            "url": f"/api/external-gallery/content?path={quote(full_path, safe='')}",
                        }
                    )
                    total += 1
                    if total >= max_items:
                        truncated = True
                        break
    except httpx.HTTPError as exc:
        logger.warning("external gallery WebDAV unavailable: %s", exc)
        raise HTTPException(status_code=502, detail="外部图库暂时无法读取") from exc
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {
        "total": total,
        "truncated": truncated,
        "directories": [
            {"path": path, "items": items}
            for path, items in sorted(directories.items(), key=lambda item: item[0].lower())
        ],
    }


@router.get("/content")
async def read_external_image(path: str = Query(min_length=1, max_length=2048)) -> Response:
    settings, base_url = _settings_or_503()
    relative_path = _normalise_path(path)
    if PurePosixPath(relative_path).suffix.lower() not in _IMAGE_EXTENSIONS:
        raise HTTPException(status_code=404, detail="图片不存在")
    auth = (
        (settings.external_gallery_webdav_username, settings.external_gallery_webdav_password)
        if settings.external_gallery_webdav_username
        else None
    )
    try:
        async with httpx.AsyncClient(timeout=120, auth=auth, follow_redirects=True) as client:
            upstream = await client.get(_webdav_url(base_url, relative_path))
    except httpx.HTTPError as exc:
        logger.warning("external gallery image unavailable: %s", exc)
        raise HTTPException(status_code=502, detail="图片暂时无法读取") from exc
    if upstream.status_code == 404:
        raise HTTPException(status_code=404, detail="图片不存在")
    if upstream.status_code >= 400:
        raise HTTPException(status_code=502, detail="图片暂时无法读取")

    media_type = upstream.headers.get("content-type", "").split(";", 1)[0].lower()
    if not media_type.startswith("image/"):
        media_type = mimetypes.guess_type(relative_path)[0] or "application/octet-stream"
    return Response(
        content=upstream.content,
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=3600"},
    )
