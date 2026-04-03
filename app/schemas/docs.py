from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import NonEmptyText


class BlockRead(BaseModel):
    heading: str
    level: int
    position: int
    start_offset: int
    end_offset: int
    content: str


class DocumentCreate(BaseModel):
    title: NonEmptyText
    raw_markdown: str = ""
    actor: NonEmptyText = "browser"


class DocumentUpdate(BaseModel):
    title: NonEmptyText
    raw_markdown: str
    expected_revision: int
    actor: NonEmptyText = "browser"
    note: str | None = None


class DocumentListItem(BaseModel):
    id: int
    title: str
    revision: int
    updated_at: datetime


class DocumentRead(BaseModel):
    id: int
    title: str
    raw_markdown: str
    revision: int
    default_task_action: str | None = None
    default_task_instruction: str | None = None
    blocks: list[BlockRead]
    updated_at: datetime


class TaskDefaultsUpdate(BaseModel):
    actor: NonEmptyText = "browser"
    default_task_action: str | None = None
    default_task_instruction: str | None = None
