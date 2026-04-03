from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import NonEmptyText


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
    recommended_action: str | None = None
    diff: str


class TaskContextBlockRead(BaseModel):
    heading: str
    level: int
    position: int
    start_offset: int
    end_offset: int


class TaskContextHeadingRead(BaseModel):
    heading: str
    level: int
    position: int


class TaskContextRead(BaseModel):
    document_title: str
    document_revision: int
    current_selection_text: str
    block: TaskContextBlockRead | None = None
    block_markdown: str | None = None
    heading_path: list[TaskContextHeadingRead] = Field(default_factory=list)
    document_outline: list[TaskContextHeadingRead] = Field(default_factory=list)
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


class TaskBatchPreviewItemRead(BaseModel):
    task_id: int
    action: str
    heading: str | None = None
    start_offset: int
    end_offset: int
    source_text: str
    result_text: str | None = None
    reason: str | None = None


class TaskBatchPreviewRead(BaseModel):
    doc_id: int
    document_revision: int
    action: str | None = None
    start_offset: int | None = None
    end_offset: int | None = None
    limit: int | None = None
    matched: int
    will_accept: int
    will_skip: int
    accepted_task_ids: list[int]
    accepted_tasks: list[TaskBatchPreviewItemRead]
    skipped_tasks: list[TaskBatchPreviewItemRead]


class TaskBatchAcceptRead(BaseModel):
    doc_id: int
    document_revision: int
    accepted: int
    skipped: int
    accepted_task_ids: list[int]
    skipped_tasks: list[TaskRelocateAttemptRead]
    rollback_version_id: int | None = None
    rollback_revision: int | None = None


class TaskRelocateRead(BaseModel):
    task: TaskRead
    relocation_strategy: str


class CleanupStaleTasksRead(BaseModel):
    doc_id: int
    cancelled: int
    rejected: int
    unchanged: int


class TaskRecoveryPreviewRead(BaseModel):
    task_id: int
    doc_id: int
    task_status: str
    is_stale: bool
    stale_reason: str | None = None
    current_document_revision: int
    current_start_offset: int
    current_end_offset: int
    current_selection_text: str
    can_relocate: bool = False
    relocation_strategy: str | None = None
    can_requeue_from_current: bool = False
    requeue_reason: str | None = None
    recommended_mode: str | None = None
    context: TaskContextRead | None = None


class TaskRecoverRequest(BaseModel):
    mode: Literal["relocate", "requeue_from_current"]
    actor: NonEmptyText = "browser"


class TaskRecoveryResultRead(BaseModel):
    mode: str
    source_task: TaskRead
    new_task: TaskRead | None = None
    relocation_strategy: str | None = None
    closed_source_status: str | None = None


