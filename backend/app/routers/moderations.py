import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_api_key_or_raw_key
from app.database import get_db
from app.models import ApiKey, UsageLog
from app.schemas import OpenAIModerationRequest
from app.services.moderation import moderate_texts
from app.services.upstream import UpstreamError

router = APIRouter(prefix="/v1", tags=["moderations"])
logger = logging.getLogger(__name__)


@router.post("/moderations")
async def create_moderation(
    body: OpenAIModerationRequest,
    api_key: ApiKey = Depends(get_current_api_key_or_raw_key),
    db: Session = Depends(get_db),
) -> dict:
    try:
        result = await moderate_texts(db, inputs=body.input_items())
    except UpstreamError as exc:
        logger.warning("moderation upstream error status=%s", exc.status_code)
        db.add(
            UsageLog(
                api_key_id=api_key.id,
                action="moderation",
                cost=0,
                model=None,
                success=False,
                detail=str(exc),
            )
        )
        db.commit()
        raise HTTPException(status_code=502, detail="审核上游服务暂时不可用，请稍后重试") from exc

    db.add(
        UsageLog(
            api_key_id=api_key.id,
            action="moderation",
            cost=0,
            model=result["model"],
            success=True,
            detail=None,
        )
    )
    db.commit()
    return result
