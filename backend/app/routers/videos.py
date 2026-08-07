from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_api_key
from app.database import get_db
from app.models import ApiKey
from app.schemas import (
    VideoGenerationRequest,
    VideoGenerationResponse,
    VideoStatusResponse,
)
from app.services.upstream import UpstreamError, videos_generations, videos_retrieve

router = APIRouter(prefix="/api/videos", tags=["videos"])


@router.post("/generations", response_model=VideoGenerationResponse)
async def generate_video(
    body: VideoGenerationRequest,
    _: ApiKey = Depends(get_current_api_key),
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
    _: ApiKey = Depends(get_current_api_key),
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
