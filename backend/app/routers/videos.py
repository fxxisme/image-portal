import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.auth import get_current_api_key_or_raw_key
from app.database import get_db
from app.models import ApiKey
from app.schemas import (
    VideoGenerationRequest,
    VideoGenerationResponse,
    VideoStatusResponse,
)
from app.services.upstream import (
    UpstreamError,
    video_content_request,
    videos_generations,
    videos_retrieve,
)

router = APIRouter(prefix="/v1/videos", tags=["videos"])
settings = get_settings()


@router.post("/generations", response_model=VideoGenerationResponse)
async def generate_video(
    body: VideoGenerationRequest,
    api_key: ApiKey = Depends(get_current_api_key_or_raw_key),
    db: Session = Depends(get_db),
) -> VideoGenerationResponse:
    try:
        request_id = await videos_generations(db, **body.model_dump())
    except UpstreamError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return VideoGenerationResponse(request_id=request_id)


@router.get("/{request_id}", response_model=VideoStatusResponse)
async def get_video_status(
    request_id: str,
    api_key: ApiKey = Depends(get_current_api_key_or_raw_key),
    db: Session = Depends(get_db),
) -> VideoStatusResponse:
    try:
        data = await videos_retrieve(db, request_id=request_id)
    except UpstreamError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return VideoStatusResponse(
        status=str(data.get("status") or ""),
        model=data.get("model"),
        progress=data.get("progress"),
        video=data.get("video") if isinstance(data.get("video"), dict) else None,
    )


@router.get("/{request_id}/content")
async def get_video_content(
    request_id: str,
    request: Request,
    download: bool = False,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    try:
        endpoint, headers = video_content_request(db, request_id=request_id)
    except UpstreamError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    range_header = request.headers.get("range")
    if range_header:
        headers["Range"] = range_header

    client = httpx.AsyncClient(timeout=settings.upstream_timeout_seconds)
    try:
        upstream = await client.send(client.build_request("GET", endpoint, headers=headers), stream=True)
    except httpx.TimeoutException as exc:
        await client.aclose()
        raise HTTPException(status_code=504, detail="视频内容请求超时") from exc
    except httpx.HTTPError as exc:
        await client.aclose()
        raise HTTPException(status_code=502, detail=f"视频内容请求失败: {exc}") from exc

    if upstream.status_code >= 400:
        body = (await upstream.aread()).decode("utf-8", errors="replace")
        await upstream.aclose()
        await client.aclose()
        raise HTTPException(status_code=502, detail=f"视频上游返回 HTTP {upstream.status_code}: {body[:500]}")

    response_headers = {
        name: upstream.headers[name]
        for name in ("content-type", "content-length", "content-range", "accept-ranges", "etag", "last-modified")
        if name in upstream.headers
    }
    if download:
        response_headers["content-disposition"] = 'attachment; filename="video.mp4"'

    async def stream_content():
        try:
            async for chunk in upstream.aiter_bytes():
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    return StreamingResponse(
        stream_content(),
        status_code=upstream.status_code,
        headers=response_headers,
        media_type=None,
    )
