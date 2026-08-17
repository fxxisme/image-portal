import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.database import init_db
from app.routers import admin, auth, conversations, external_gallery, gallery, images, videos
from app.services.media import media_root

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

app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    docs_url="/docs" if settings.enable_docs else None,
    redoc_url="/redoc" if settings.enable_docs else None,
    openapi_url="/openapi.json" if settings.enable_docs else None,
)

origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if origins != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    # 该站点需要被外部页面 iframe 嵌入，使用 CSP 显式允许嵌入。
    response.headers.setdefault("Content-Security-Policy", "frame-ancestors *")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    return response

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(conversations.router)
app.include_router(images.router)
app.include_router(videos.router)
app.include_router(gallery.router)
app.include_router(external_gallery.router)

# 用户生成图持久化目录（本地/容器均挂载）
_media = media_root()
app.mount("/media", StaticFiles(directory=str(_media)), name="media")


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


def _mount_frontend() -> None:
    """单容器生产：托管 Vite 构建产物；本地开发不设 STATIC_DIR。"""
    raw = (settings.static_dir or "").strip()
    if not raw:
        return
    static_root = Path(raw).resolve()
    if not static_root.is_dir():
        logging.warning("STATIC_DIR 不存在，跳过静态托管: %s", static_root)
        return

    assets = static_root / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(static_root / "index.html")

    @app.get("/{full_path:path}")
    async def spa(full_path: str) -> FileResponse:
        # API / 媒体 / 文档未命中时不要回 SPA
        if (
            full_path == "api"
            or full_path.startswith("api/")
            or full_path == "v1"
            or full_path.startswith("v1/")
            or full_path == "media"
            or full_path.startswith("media/")
            or full_path in {
                "docs",
                "redoc",
                "openapi.json",
            }
        ):
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="Not Found")
        candidate = (static_root / full_path).resolve()
        try:
            candidate.relative_to(static_root)
        except ValueError:
            return FileResponse(static_root / "index.html")
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(static_root / "index.html")


_mount_frontend()
