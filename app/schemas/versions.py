from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, StringConstraints


NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


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
