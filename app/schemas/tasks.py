from pydantic import BaseModel


class TaskCreate(BaseModel):
    block_id: int
    action: str
    instruction: str | None = None
    source_text: str
    start_offset: int
    end_offset: int
    doc_revision: int
    auto_apply: bool = False
    actor: str = "browser"


class TaskClaimRequest(BaseModel):
    agent_name: str
    limit: int = 1
    lease_seconds: int = 300


class TaskHeartbeatRequest(BaseModel):
    claim_token: str
    lease_seconds: int = 300


class TaskCompleteRequest(BaseModel):
    claim_token: str
    result: str | None = None
    error_message: str | None = None


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
