"""调用上游 OpenAI 兼容图片接口（chatgpt2api / New API）。

对齐 newapi-image-test.html：
  POST {base}/v1/images/generations
  Authorization: Bearer {apiKey}
  body: { model, prompt, messages, n, response_format }

上游 base_url / api_key / default_model 从 SQLite 管理配置读取。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.services.settings import get_or_create_settings

logger = logging.getLogger(__name__)


class UpstreamError(Exception):
    def __init__(self, message: str, status_code: int | None = None, body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


@dataclass
class UpstreamConfig:
    base_url: str
    api_key: str
    default_model: str
    response_format: str


def normalize_base(raw: str) -> str:
    base = (raw or "").strip().rstrip("/")
    if base.lower().endswith("/v1"):
        base = base[:-3].rstrip("/")
    return base


def load_upstream_config(db: Session) -> UpstreamConfig:
    row = get_or_create_settings(db)
    return UpstreamConfig(
        base_url=row.upstream_base_url or "",
        api_key=row.upstream_api_key or "",
        default_model=row.default_model or "gpt-image-2",
        response_format=row.response_format or "url",
    )


def _require_config(cfg: UpstreamConfig) -> None:
    if not cfg.base_url.strip():
        raise UpstreamError("未配置上游地址，请在管理后台填写 Upstream Base URL")
    if not cfg.api_key.strip():
        raise UpstreamError("未配置上游 API Key，请在管理后台填写")


def _client() -> httpx.AsyncClient:
    settings = get_settings()
    return httpx.AsyncClient(timeout=settings.upstream_timeout_seconds)


async def images_generations(
    db: Session,
    *,
    prompt: str,
    model: str | None = None,
    n: int = 1,
    response_format: str | None = None,
) -> list[str]:
    cfg = load_upstream_config(db)
    _require_config(cfg)

    base = normalize_base(cfg.base_url)
    endpoint = f"{base}/v1/images/generations"
    use_model = (model or cfg.default_model).strip() or cfg.default_model
    fmt = response_format or cfg.response_format or "url"

    body: dict[str, Any] = {
        "model": use_model,
        "prompt": prompt,
        "messages": prompt,
        "n": n,
        "response_format": fmt,
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg.api_key}",
    }

    logger.info("upstream generations %s model=%s n=%s", endpoint, use_model, n)

    async with _client() as client:
        try:
            res = await client.post(endpoint, headers=headers, json=body)
        except httpx.TimeoutException as exc:
            raise UpstreamError("上游生图超时") from exc
        except httpx.HTTPError as exc:
            raise UpstreamError(f"上游网络错误: {exc}") from exc

    return _extract_urls(res)


async def images_edits(
    db: Session,
    *,
    prompt: str,
    image_url: str,
    model: str | None = None,
    n: int = 1,
    response_format: str | None = None,
) -> list[str]:
    cfg = load_upstream_config(db)
    _require_config(cfg)

    base = normalize_base(cfg.base_url)
    endpoint = f"{base}/v1/images/edits"
    use_model = (model or cfg.default_model).strip() or cfg.default_model
    fmt = response_format or cfg.response_format or "url"

    body: dict[str, Any] = {
        "model": use_model,
        "prompt": prompt,
        "n": n,
        "response_format": fmt,
        "image_url": image_url,
        "image": image_url,
        "images": [{"image_url": image_url}],
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg.api_key}",
    }

    logger.info("upstream edits %s model=%s n=%s", endpoint, use_model, n)

    async with _client() as client:
        try:
            res = await client.post(endpoint, headers=headers, json=body)
        except httpx.TimeoutException as exc:
            raise UpstreamError("上游改图超时") from exc
        except httpx.HTTPError as exc:
            raise UpstreamError(f"上游网络错误: {exc}") from exc

    return _extract_urls(res)


def _extract_urls(res: httpx.Response) -> list[str]:
    text = res.text
    try:
        data = res.json() if text else None
    except Exception:
        data = None

    if res.status_code >= 400:
        detail = data if data is not None else text
        raise UpstreamError(
            f"上游返回 HTTP {res.status_code}",
            status_code=res.status_code,
            body=detail,
        )

    items = (data or {}).get("data") or []
    if not items:
        raise UpstreamError("上游成功但未返回 data 图片", body=data)

    urls: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("url"):
            urls.append(item["url"])
        elif item.get("b64_json"):
            urls.append(f"data:image/png;base64,{item['b64_json']}")

    if not urls:
        raise UpstreamError("上游 data 中无 url/b64_json", body=data)
    return urls
