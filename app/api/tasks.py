from fastapi import APIRouter

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("")
def list_tasks():
    return {"ok": True, "data": []}


@router.post("/claim")
def claim_tasks():
    return {"ok": True, "data": []}
