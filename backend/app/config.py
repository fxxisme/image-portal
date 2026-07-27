from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Image Portal"
    # 对外访问时前端可配 VITE_API_BASE；后端自身不强制
    host: str = "0.0.0.0"
    port: int = 8000

    # SQLite；本地默认当前目录；Docker 用环境变量指到 /data
    database_url: str = "sqlite:///./portal.db"

    # 前端静态目录（Docker 单容器为 /app/static；本地开发留空则不托管）
    static_dir: str = ""

    # 用户生成图本地持久化目录（相对 cwd 或绝对路径）
    media_dir: str = "./media"

    # 管理端单口令（仅此与 JWT 仍走环境变量）
    admin_password: str = "change-me-admin"
    jwt_secret: str = "change-me-jwt-secret-please"
    jwt_algorithm: str = "HS256"
    # 用户 token 有效期（小时）
    user_token_expire_hours: int = 24 * 30
    admin_token_expire_hours: int = 24 * 7

    # 上游超时（秒）；连接地址 / key / model 在管理后台配置
    upstream_timeout_seconds: int = 300

    # CORS
    cors_origins: str = "*"


@lru_cache
def get_settings() -> Settings:
    return Settings()
