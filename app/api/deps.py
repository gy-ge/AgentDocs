"""API dependency functions for authentication and authorization."""

import hmac

from fastapi import Header

from app.config import get_settings
from app.errors import ApiError


def require_api_key(authorization: str | None = Header(default=None)) -> None:
    """Validate the ``Authorization: Bearer <key>`` header against the configured API key."""
    settings = get_settings()
    expected = f"Bearer {settings.api_key}"
    if not authorization or not hmac.compare_digest(authorization, expected):
        raise ApiError(401, "unauthorized", "invalid api key")