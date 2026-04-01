from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints


NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class TaskCreate(BaseModel):
    action: NonEmptyText
    instruction: str | None = None
    source_text: str
    start_offset: int
    end_offset: int
    doc_revision: int


class TaskNextRequest(BaseModel):
    agent_name: NonEmptyText


class TaskCompleteRequest(BaseModel):
    result: str | None = None
    error_message: str | None = None


class TaskDiffRead(BaseModel):
    task_id: int
    doc_id: int
    current_text: str
    source_text: str
    result_text: str
    can_accept: bool
    conflict_reason: str | None = None
    diff: str


class TaskContextBlockRead(BaseModel):
    heading: str
    level: int
    position: int
    start_offset: int
    end_offset: int


class TaskContextRead(BaseModel):
    document_title: str
    document_revision: int
    block: TaskContextBlockRead | None = None
    block_markdown: str | None = None
    context_before: str
    context_after: str


class TaskRead(BaseModel):
    id: int
    doc_id: int
    doc_revision: int
    start_offset: int
    end_offset: int
    source_text: str
    action: str
    instruction: str | None = None
    result: str | None = None
    status: str
    agent_name: str | None = None
    error_message: str | None = None
    is_stale: bool = False
    stale_reason: str | None = None
    recommended_action: str | None = None
    context: TaskContextRead | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    resolved_at: datetime | None = None


class TaskAcceptRequest(BaseModel):
    expected_revision: int
    actor: NonEmptyText = "browser"
    note: str | None = None


class TaskBatchActionRequest(BaseModel):
    actor: NonEmptyText = "browser"
    note: str | None = None
    action: NonEmptyText | None = None
    start_offset: int | None = None
    end_offset: int | None = None
    limit: int | None = Field(default=None, ge=1, le=50)


class TaskRelocateAttemptRead(BaseModel):
    task_id: int
    reason: str


class TaskBatchAcceptRead(BaseModel):
    doc_id: int
    document_revision: int
    accepted: int
    skipped: int
    accepted_task_ids: list[int]
    skipped_tasks: list[TaskRelocateAttemptRead]


class TaskRelocateRead(BaseModel):
    task: TaskRead
    relocation_strategy: str


class CleanupStaleTasksRead(BaseModel):
    doc_id: int
    cancelled: int
    rejected: int
    unchanged: int


