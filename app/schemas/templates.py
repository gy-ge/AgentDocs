from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import NonEmptyText


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