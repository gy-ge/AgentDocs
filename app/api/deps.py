from fastapi import Header

from app.config import get_settings
from app.errors import ApiError


def require_api_key(authorization: str | None = Header(default=None)) -> None:
    settings = get_settings()
    expected = f"Bearer {settings.api_key}"
    if authorization != expected:
        raise ApiError(401, "unauthorized", "invalid api key")