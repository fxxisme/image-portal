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
            "video_base_url": "TEXT NOT NULL DEFAULT ''",
            "video_api_key": "TEXT NOT NULL DEFAULT ''",
            "video_model": "TEXT NOT NULL DEFAULT ''",
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
        _migrate_sqlite_generated_images(conn)


def _migrate_sqlite_generated_images(conn) -> None:
    """为旧库补上图片到会话/消息的真实外键，消除删除会话后的孤儿图片。"""
    foreign_keys = {
        row[3]: (row[2], row[6])
        for row in conn.execute(text("PRAGMA foreign_key_list(generated_images)"))
    }
    required = {
        "conversation_id": ("conversations", "CASCADE"),
        "message_id": ("messages", "CASCADE"),
    }
    if all(foreign_keys.get(column) == target for column, target in required.items()):
        return

    conn.execute(
        text(
            """
            CREATE TABLE generated_images_new (
                id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                api_key_id INTEGER NOT NULL REFERENCES api_keys(id) ON DELETE CASCADE,
                conversation_id INTEGER REFERENCES conversations(id) ON DELETE CASCADE,
                message_id INTEGER REFERENCES messages(id) ON DELETE CASCADE,
                action VARCHAR(32) NOT NULL DEFAULT 'generate',
                prompt TEXT NOT NULL DEFAULT '',
                storage_path VARCHAR(512) NOT NULL,
                storage_backend VARCHAR(32) NOT NULL DEFAULT 'local',
                public_url VARCHAR(512) NOT NULL,
                source_url TEXT,
                created_at DATETIME NOT NULL
            )
            """
        )
    )
    conn.execute(
        text(
            """
            INSERT INTO generated_images_new (
                id, api_key_id, conversation_id, message_id, action, prompt,
                storage_path, storage_backend, public_url, source_url, created_at
            )
            SELECT
                image.id, image.api_key_id, image.conversation_id, image.message_id,
                image.action, image.prompt, image.storage_path, image.storage_backend,
                image.public_url, image.source_url, image.created_at
            FROM generated_images AS image
            WHERE EXISTS (
                SELECT 1
                FROM messages AS message
                JOIN conversations AS conversation ON conversation.id = message.conversation_id
                WHERE message.id = image.message_id
                  AND message.role = 'assistant'
                  AND message.conversation_id = image.conversation_id
                  AND conversation.api_key_id = image.api_key_id
                  AND image.created_at >= message.created_at
            )
            """
        )
    )
    conn.execute(text("DROP TABLE generated_images"))
    conn.execute(text("ALTER TABLE generated_images_new RENAME TO generated_images"))
    conn.execute(text("CREATE INDEX ix_generated_images_api_key_id ON generated_images (api_key_id)"))
    conn.execute(text("CREATE INDEX ix_generated_images_conversation_id ON generated_images (conversation_id)"))
    conn.execute(text("CREATE INDEX ix_generated_images_message_id ON generated_images (message_id)"))
