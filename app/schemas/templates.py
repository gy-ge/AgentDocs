from datetime import datetime

from app.schemas.common import ApiModel, NonEmptyText


class TaskTemplateCreate(ApiModel):
    name: NonEmptyText
    action: NonEmptyText
    instruction: NonEmptyText


class TaskTemplateUpdate(ApiModel):
    name: NonEmptyText
    action: NonEmptyText
    instruction: NonEmptyText


class TaskTemplateRead(ApiModel):
    id: int
    name: str
    action: str
    instruction: str
    created_at: datetime
    updated_at: datetime
