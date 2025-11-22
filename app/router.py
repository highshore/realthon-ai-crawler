from __future__ import annotations

import base64
import json
import logging
import os
import sys
from typing import Any, Callable

from app.jobs import korea_university
from app.jobs import linkareer
from app.jobs import ewha_university
from app.jobs import sogang_university
from app.jobs import firecrawl_fallback

BASE_PREFIX_KU = "https://info.korea.ac.kr/info/board/"
BASE_PREFIX_EWHA = "https://www.ewha.ac.kr"
BASE_PREFIX_SOGANG = "https://www.sogang.ac.kr"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO))
LOG = logging.getLogger("router")

RouteHandler = Callable[[dict[str, Any], Any | None], dict[str, Any]]


def match_korea(url: str | None) -> bool:
    return bool(url and url.startswith(BASE_PREFIX_KU))


def match_linkareer(url: str | None) -> bool:
    return bool(url and url.startswith("https://linkareer.com/"))


def match_ewha(url: str | None) -> bool:
    return bool(url and BASE_PREFIX_EWHA in url)


def match_sogang(url: str | None) -> bool:
    return bool(url and BASE_PREFIX_SOGANG in url)


ROUTES: list[tuple[str, Callable[[str | None], bool], RouteHandler]] = [
    ("korea_university", match_korea, korea_university.run),
    ("linkareer", match_linkareer, linkareer.run),
    ("ewha_university", match_ewha, ewha_university.run),
    ("sogang_university", match_sogang, sogang_university.run),
]


def resolve_handler(url: str | None) -> tuple[str, RouteHandler] | tuple[None, None]:
    for name, matcher, handler in ROUTES:
        if matcher(url):
            return name, handler
    return None, None


def pick_route_url(payload: dict[str, Any]) -> str | None:
    for key in ("base_url", "url"):
        value = payload.get(key)
        if value:
            return value
    return None


def _extract_payload(event: dict[str, Any] | None) -> dict[str, Any]:
    if not event:
        return {}
    # When invoked through Lambda Function URLs / API Gateway the body is nested.
    if "body" in event:
        raw_body = event.get("body") or ""
        if event.get("isBase64Encoded"):
            try:
                raw_body = base64.b64decode(raw_body)
            except (base64.binascii.Error, TypeError) as exc:
                raise ValueError(f"invalid base64 body: {exc}") from exc
        if isinstance(raw_body, bytes):
            raw_body = raw_body.decode("utf-8", errors="ignore")
        try:
            payload = json.loads(raw_body or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid json body: {exc}") from exc
        # Merge query params to allow overrides if needed.
        if event.get("queryStringParameters"):
            payload.setdefault("query", event["queryStringParameters"])
        LOG.info("HTTP payload keys: %s", list(payload.keys()))
        return payload
    return event


def lambda_handler(event: dict[str, Any] | None, context: Any | None = None) -> dict[str, Any]:
    try:
        payload = _extract_payload(event)
    except ValueError as exc:
        LOG.exception("Invalid request payload: %s", exc)
        return {"statusCode": 400, "body": json.dumps({"error": str(exc)})}
    url = pick_route_url(payload)
    name, handler = resolve_handler(url)
    if not handler:
        LOG.warning("No specific handler for %s, falling back to Firecrawl", url)
        name, handler = "firecrawl_fallback", firecrawl_fallback.run
    LOG.info("Routing %s to %s", url, name)
    try:
        body = handler(payload, context)
        return {"statusCode": 200, "body": body, "script": name}
    except Exception as exc:
        LOG.exception("Handler error for %s: %s", name, exc)
        return {"statusCode": 500, "body": json.dumps({"error": str(exc), "script": name})}


if __name__ == "__main__":
    payload = json.loads(sys.stdin.read() or "{}")
    print(json.dumps(lambda_handler(payload), ensure_ascii=False, indent=2))

