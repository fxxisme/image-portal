from collections.abc import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

settings = get_settings()

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)


@event.listens_for(engine, "connect")
def _sqlite_pragma(dbapi_connection, connection_record) -> None:  # type: ignore[no-untyped-def]
    if settings.database_url.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    if settings.database_url.startswith("sqlite"):
        _ensure_sqlite_columns()


def _ensure_sqlite_columns() -> None:
    """为未使用迁移工具的既有 SQLite 数据库补齐新增字段。"""
    additions = {
        "system_settings": {
            "webdav_url": "TEXT NOT NULL DEFAULT ''",
            "webdav_username": "TEXT NOT NULL DEFAULT ''",
            "webdav_password": "TEXT NOT NULL DEFAULT ''",
            "webdav_path": "TEXT NOT NULL DEFAULT ''",
            "webdav_public_base_url": "TEXT NOT NULL DEFAULT ''",
            "text_to_image_models": "TEXT NOT NULL DEFAULT '[\"gpt-image-2\", \"grok-imagine-image\"]'",
            "image_to_image_models": "TEXT NOT NULL DEFAULT '[\"gpt-image-2\"]'",
        },
        "generated_images": {
            "storage_backend": "TEXT NOT NULL DEFAULT 'local'",
        },
    }
    with engine.begin() as conn:
        for table, columns in additions.items():
            existing = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}
            for name, definition in columns.items():
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {definition}"))
