import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import init_db
from app.routers import admin, auth, conversations, images

logging.basicConfig(level=logging.INFO)
settings = get_settings()

# 确保 sqlite 目录存在
if settings.database_url.startswith("sqlite:///"):
    raw = settings.database_url.replace("sqlite:///", "", 1)
    # ////data/x -> /data/x on unix-style
    db_path = Path(raw)
    if raw.startswith("/") or raw.startswith("\\"):
        db_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        Path(raw).parent.mkdir(parents=True, exist_ok=True)

app = FastAPI(title=settings.app_name, version="1.0.0")

origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if origins != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(conversations.router)
app.include_router(images.router)


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    # 确保 system_settings 单例行存在
    from app.database import SessionLocal
    from app.services.settings import get_or_create_settings

    db = SessionLocal()
    try:
        get_or_create_settings(db)
    finally:
        db.close()


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}
