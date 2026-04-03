from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import NonEmptyText


class VersionRead(BaseModel):
    id: int
    revision: int
    actor: str
    note: str | None = None
    created_at: datetime


class RollbackRequest(BaseModel):
    expected_revision: int
    actor: NonEmptyText = "browser"
    note: str | None = None
