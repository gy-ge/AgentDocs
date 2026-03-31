from datetime import datetime

from pydantic import BaseModel


class BlockRead(BaseModel):
    heading: str
    level: int
    position: int
    start_offset: int
    end_offset: int
    content: str


class DocumentCreate(BaseModel):
    title: str
    raw_markdown: str = ""
    actor: str = "browser"


class DocumentUpdate(BaseModel):
    title: str
    raw_markdown: str
    expected_revision: int
    actor: str = "browser"
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
    blocks: list[BlockRead]
    updated_at: datetime
