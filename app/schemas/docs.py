from datetime import datetime

from app.schemas.common import ApiModel, NonEmptyText


class BlockRead(ApiModel):
    heading: str
    level: int
    position: int
    start_offset: int
    end_offset: int
    content: str


class DocumentCreate(ApiModel):
    title: NonEmptyText
    raw_markdown: str = ""
    actor: NonEmptyText = "browser"


class DocumentUpdate(ApiModel):
    title: NonEmptyText
    raw_markdown: str
    expected_revision: int
    actor: NonEmptyText = "browser"
    note: str | None = None


class DocumentListItem(ApiModel):
    id: int
    title: str
    revision: int
    updated_at: datetime


class DocumentRead(ApiModel):
    id: int
    title: str
    raw_markdown: str
    revision: int
    default_task_action: str | None = None
    default_task_instruction: str | None = None
    blocks: list[BlockRead]
    updated_at: datetime


class TaskDefaultsUpdate(ApiModel):
    actor: NonEmptyText = "browser"
    default_task_action: str | None = None
    default_task_instruction: str | None = None
