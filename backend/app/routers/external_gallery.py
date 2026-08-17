import base64
import json
import logging
import mimetypes
from binascii import Error as BinasciiError
from datetime import date
from pathlib import PurePosixPath
from urllib.parse import quote, unquote, urlparse
from xml.etree import ElementTree

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.settings import get_or_create_settings

router = APIRouter(prefix="/api/external-gallery", tags=["external-gallery"])
logger = logging.getLogger(__name__)

_IMAGE_EXTENSIONS = {".avif", ".bmp", ".gif", ".heic", ".jpeg", ".jpg", ".png", ".svg", ".webp"}
_DAV = "{DAV:}"


def _settings_or_503(db: Session):
    settings = get_or_create_settings(db)
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


def _join_path(*parts: str) -> str:
    return _normalise_path("/".join(part.strip("/") for part in parts if part))


def _date_from_parts(year_name: str, month_name: str, day_name: str) -> date | None:
    if not (year_name.isdigit() and month_name.isdigit() and day_name.isdigit()):
        return None
    if len(year_name) != 4:
        return None
    try:
        return date(int(year_name), int(month_name), int(day_name))
    except ValueError:
        return None


def _encode_cursor(day: date, relative_path: str, offset: int) -> str:
    payload = json.dumps(
        {"date": day.isoformat(), "path": relative_path, "offset": offset},
        separators=(",", ":"),
    ).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _decode_cursor(value: str) -> tuple[date, str, int]:
    try:
        padding = "=" * (-len(value) % 4)
        payload = json.loads(base64.urlsafe_b64decode(f"{value}{padding}").decode())
        day = date.fromisoformat(payload["date"])
        relative_path = _normalise_path(payload["path"])
        offset = int(payload["offset"])
        parts = relative_path.split("/")
        path_day = _date_from_parts(*parts) if len(parts) == 3 else None
        if path_day != day or offset < 0:
            raise ValueError
        return day, relative_path, offset
    except (BinasciiError, KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="分页游标无效") from exc


async def _iter_date_directories(
    client: httpx.AsyncClient,
    base_url: str,
    root_path: str,
    before: date | None,
):
    root_entries = await _list_directory(client, base_url, root_path)
    years = sorted(
        (
            (int(name), name)
            for name, is_directory in root_entries
            if is_directory and len(name) == 4 and name.isascii() and name.isdigit()
        ),
        reverse=True,
    )
    for year_number, year_name in years:
        if before and year_number > before.year:
            continue
        year_path = _join_path(root_path, year_name)
        month_entries = await _list_directory(client, base_url, year_path)
        months = sorted(
            (
                (int(name), name)
                for name, is_directory in month_entries
                if is_directory and name.isascii() and name.isdigit() and 1 <= int(name) <= 12
            ),
            reverse=True,
        )
        for month_number, month_name in months:
            if before and year_number == before.year and month_number > before.month:
                continue
            month_path = _join_path(year_path, month_name)
            day_entries = await _list_directory(client, base_url, month_path)
            days = sorted(
                (
                    (int(name), name)
                    for name, is_directory in day_entries
                    if is_directory and name.isascii() and name.isdigit() and 1 <= int(name) <= 31
                ),
                reverse=True,
            )
            for _, day_name in days:
                current_day = _date_from_parts(year_name, month_name, day_name)
                if current_day is None or (before and current_day >= before):
                    continue
                yield current_day, _join_path(year_name, month_name, day_name)


async def _list_day_images(
    client: httpx.AsyncClient,
    base_url: str,
    root_path: str,
    day: date,
    relative_path: str,
) -> list[dict]:
    directory_path = _join_path(root_path, relative_path)
    entries = await _list_directory(client, base_url, directory_path)
    images = sorted(
        (name for name, is_directory in entries if not is_directory and PurePosixPath(name).suffix.lower() in _IMAGE_EXTENSIONS),
        key=str.lower,
        reverse=True,
    )
    return [
        {
            "path": _join_path(directory_path, name),
            "name": name,
            "date": day.isoformat(),
            "url": f"/api/external-gallery/content?path={quote(_join_path(directory_path, name), safe='')}",
        }
        for name in images
    ]


@router.get("/")
async def list_external_gallery(
    cursor: str | None = Query(default=None, max_length=512),
    db: Session = Depends(get_db),
) -> dict:
    settings, base_url = _settings_or_503(db)
    root_path = _normalise_path(settings.external_gallery_webdav_path)
    page_size = max(1, min(settings.external_gallery_max_items or 60, 200))
    resume = _decode_cursor(cursor) if cursor else None
    auth = (
        (settings.external_gallery_webdav_username, settings.external_gallery_webdav_password)
        if settings.external_gallery_webdav_username
        else None
    )
    items: list[dict] = []

    async def append_day(current_day: date, relative_path: str, offset: int = 0) -> str | None:
        day_items = await _list_day_images(client, base_url, root_path, current_day, relative_path)
        remaining = day_items[offset:]
        capacity = page_size - len(items)
        items.extend(remaining[:capacity])
        if len(items) >= page_size:
            return _encode_cursor(current_day, relative_path, offset + min(len(remaining), capacity))
        return None

    try:
        async with httpx.AsyncClient(timeout=30, auth=auth, follow_redirects=True) as client:
            if resume:
                resume_day, resume_path, resume_offset = resume
                next_cursor = await append_day(resume_day, resume_path, resume_offset)
                if next_cursor:
                    return {"items": items, "next_cursor": next_cursor}
                before = resume_day
            else:
                before = None

            async for current_day, relative_path in _iter_date_directories(client, base_url, root_path, before):
                next_cursor = await append_day(current_day, relative_path)
                if next_cursor:
                    return {"items": items, "next_cursor": next_cursor}
    except httpx.HTTPError as exc:
        logger.warning("external gallery WebDAV unavailable: %s", exc)
        raise HTTPException(status_code=502, detail="外部图库暂时无法读取") from exc
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {"items": items, "next_cursor": None}


@router.get("/content")
async def read_external_image(
    path: str = Query(min_length=1, max_length=2048),
    db: Session = Depends(get_db),
) -> Response:
    settings, base_url = _settings_or_503(db)
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
