from __future__ import annotations

import re
from typing import Any


SECRET_KEY_RE = re.compile(
    r"(secret|password|credential|api[_-]?key|access[_-]?token|refresh[_-]?token|bot[_-]?token|authorization|cookie)",
    re.IGNORECASE,
)

SECRET_VALUE_RE = re.compile(
    r"(sk-[A-Za-z0-9_\-]{12,}|xai-[A-Za-z0-9_\-]{12,}|oc-[A-Za-z0-9_\-]{12,}|Bearer\s+[A-Za-z0-9._\-]{12,})",
    re.IGNORECASE,
)


def is_secret_key(key: str) -> bool:
    return bool(SECRET_KEY_RE.search(key))


def redact_string(value: str, *, max_length: int = 240) -> str:
    redacted = SECRET_VALUE_RE.sub("[redacted]", value)
    if len(redacted) > max_length:
        return redacted[: max_length - 1] + "..."
    return redacted


def sanitize(value: Any, *, key: str = "", max_depth: int = 8) -> Any:
    if is_secret_key(key):
        if value in (None, "", False):
            return bool(value)
        return "[redacted]"
    if max_depth <= 0:
        return type(value).__name__
    if isinstance(value, dict):
        return {str(k): sanitize(v, key=str(k), max_depth=max_depth - 1) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize(item, max_depth=max_depth - 1) for item in value[:100]]
    if isinstance(value, tuple):
        return [sanitize(item, max_depth=max_depth - 1) for item in value[:100]]
    if isinstance(value, str):
        return redact_string(value)
    return value


def safe_preview(value: Any, *, limit: int = 180) -> str:
    if value is None:
        return ""
    return redact_string(str(value), max_length=limit)
