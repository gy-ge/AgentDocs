from datetime import datetime

from app.schemas.common import ApiModel, NonEmptyText


class VersionRead(ApiModel):
    id: int
    revision: int
    actor: str
    note: str | None = None
    created_at: datetime


class RollbackRequest(ApiModel):
    expected_revision: int
    actor: NonEmptyText = "browser"
    note: str | None = None
