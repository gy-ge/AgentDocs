from pydantic import BaseModel


class TaskCreate(BaseModel):
    action: str
    instruction: str | None = None
    source_text: str
    start_offset: int
    end_offset: int
    doc_revision: int
    actor: str = "browser"


class TaskNextRequest(BaseModel):
    agent_name: str


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
    diff: str


class TaskAcceptRequest(BaseModel):
    expected_revision: int
    actor: str = "browser"
    note: str | None = None


class TaskRejectRequest(BaseModel):
    actor: str = "browser"
    note: str | None = None


class TaskCancelRequest(BaseModel):
    actor: str = "browser"
    note: str | None = None
