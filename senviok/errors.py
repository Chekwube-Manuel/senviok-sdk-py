"""Error types raised by the Senviok SDK."""

from __future__ import annotations

from typing import Any, Dict, Optional


class SenviokError(Exception):
    """Base class for all Senviok SDK errors."""

    def __init__(self, message: str, *, status_code: Optional[int] = None):
        self.status_code = status_code
        super().__init__(message)


class AuthenticationError(SenviokError):
    """API key was missing, invalid, or rejected (HTTP 401/403)."""


class RateLimitError(SenviokError):
    """The tenant rate limit was exceeded (HTTP 429)."""


class ApiError(SenviokError):
    """The API returned an error response (HTTP 4xx/5xx)."""

    def __init__(self, message: str, *, status_code: Optional[int] = None, body: Any = None):
        self.body = body
        super().__init__(message, status_code=status_code)


def _error_message(payload: Any) -> str:
    """Best-effort extraction of a human-readable message from an error payload."""
    if isinstance(payload, dict):
        for key in ("message", "error", "title", "detail"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value
        if isinstance(payload.get("errors"), dict):
            details = "; ".join(
                f"{field}: {', '.join(errors)}"
                for field, errors in payload["errors"].items()
            )
            if details:
                return details
        return str(payload)
    if isinstance(payload, str) and payload:
        return payload
    return "Request failed"
