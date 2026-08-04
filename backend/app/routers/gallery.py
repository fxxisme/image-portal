from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.auth import get_current_api_key
from app.database import get_db
from app.models import ApiKey, GeneratedImage
from app.schemas import GalleryItemOut, GalleryListOut
from app.services.media import (
    delete_generated_image,
    has_valid_image_signature,
    image_content_url,
    load_generated_image_bytes,
)

router = APIRouter(prefix="/api/gallery", tags=["gallery"])


@router.get("/", response_model=GalleryListOut)
def list_gallery(
    offset: int = Query(0, ge=0),
    limit: int = Query(48, ge=1, le=100),
    api_key: ApiKey = Depends(get_current_api_key),
    db: Session = Depends(get_db),
) -> GalleryListOut:
    q = db.query(GeneratedImage).filter(GeneratedImage.api_key_id == api_key.id)
    total = q.count()
    rows = (
        q.order_by(GeneratedImage.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return GalleryListOut(
        total=total,
        items=[
            GalleryItemOut(
                id=r.id,
                public_url=image_content_url(r),
                prompt=r.prompt,
                action=r.action,
                conversation_id=r.conversation_id,
                created_at=r.created_at,
            )
            for r in rows
        ],
    )


@router.get("/{image_id}/content")
def read_gallery_image(
    image_id: int,
    sig: str = Query(default=""),
    db: Session = Depends(get_db),
) -> Response:
    row = db.get(GeneratedImage, image_id)
    if not row or not has_valid_image_signature(row, sig):
        raise HTTPException(status_code=404, detail="图片不存在")
    try:
        content, media_type = load_generated_image_bytes(db, row)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="图片文件不存在") from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail="图片暂时无法读取") from exc
    return Response(
        content=content,
        media_type=media_type,
        headers={"Cache-Control": "private, max-age=300"},
    )


@router.delete("/{image_id}")
def delete_gallery_item(
    image_id: int,
    api_key: ApiKey = Depends(get_current_api_key),
    db: Session = Depends(get_db),
) -> dict:
    row = (
        db.query(GeneratedImage)
        .filter(GeneratedImage.id == image_id, GeneratedImage.api_key_id == api_key.id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="图片不存在")

    delete_generated_image(db, row)

    db.delete(row)
    db.commit()
    return {"ok": True}
