from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, StringConstraints


NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class TaskTemplateCreate(BaseModel):
    name: NonEmptyText
    action: NonEmptyText
    instruction: NonEmptyText


class TaskTemplateUpdate(BaseModel):
    name: NonEmptyText
    action: NonEmptyText
    instruction: NonEmptyText


class TaskTemplateRead(BaseModel):
    id: int
    name: str
    action: str
    instruction: str
    created_at: datetime
    updated_at: datetime