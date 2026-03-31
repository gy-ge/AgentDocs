from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_api_key
from app.db import get_db
from app.schemas.tasks import (
    TaskAcceptRequest,
    TaskCancelRequest,
    TaskCompleteRequest,
    TaskNextRequest,
    TaskRejectRequest,
)
from app.services.task_service import TaskService

router = APIRouter(prefix="/api/tasks", tags=["tasks"], dependencies=[Depends(require_api_key)])
service = TaskService()


def serialize_task(task):
    return {
        "id": task.id,
        "doc_id": task.doc_id,
        "doc_revision": task.doc_revision,
        "start_offset": task.start_offset,
        "end_offset": task.end_offset,
        "source_text": task.source_text,
        "action": task.action,
        "instruction": task.instruction,
        "result": task.result,
        "status": task.status,
        "agent_name": task.agent_name,
        "error_message": task.error_message,
        "created_at": task.created_at,
        "started_at": task.started_at,
        "completed_at": task.completed_at,
        "resolved_at": task.resolved_at,
    }


@router.get("")
def list_tasks(
    status: str | None = Query(default=None),
    doc_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    tasks = service.list_tasks(db, status=status, doc_id=doc_id)
    return {"ok": True, "data": [serialize_task(task) for task in tasks]}


@router.get("/{task_id}")
def get_task(task_id: int, db: Session = Depends(get_db)):
    task = service.get_task(db, task_id)
    return {"ok": True, "data": serialize_task(task)}


@router.get("/{task_id}/diff")
def get_task_diff(task_id: int, db: Session = Depends(get_db)):
    diff_data = service.get_task_diff(db, task_id)
    return {"ok": True, "data": diff_data}


@router.post("/next")
def pickup_next_task(payload: TaskNextRequest, db: Session = Depends(get_db)):
    task = service.pickup_next_task(db, agent_name=payload.agent_name)
    return {"ok": True, "data": None if task is None else serialize_task(task)}


@router.post("/{task_id}/complete")
def complete_task(
    task_id: int, payload: TaskCompleteRequest, db: Session = Depends(get_db)
):
    task = service.complete_task(
        db,
        task_id=task_id,
        result=payload.result,
        error_message=payload.error_message,
    )
    return {"ok": True, "data": serialize_task(task)}


@router.post("/{task_id}/accept")
def accept_task(
    task_id: int, payload: TaskAcceptRequest, db: Session = Depends(get_db)
):
    task = service.accept_task(
        db,
        task_id=task_id,
        expected_revision=payload.expected_revision,
        actor=payload.actor,
        note=payload.note,
    )
    return {"ok": True, "data": serialize_task(task)}


@router.post("/{task_id}/reject")
def reject_task(
    task_id: int, payload: TaskRejectRequest, db: Session = Depends(get_db)
):
    task = service.reject_task(db, task_id=task_id)
    return {"ok": True, "data": serialize_task(task)}


@router.post("/{task_id}/cancel")
def cancel_task(
    task_id: int, payload: TaskCancelRequest, db: Session = Depends(get_db)
):
    task = service.cancel_task(db, task_id=task_id)
    return {"ok": True, "data": serialize_task(task)}


@router.post("/{task_id}/retry")
def retry_task(task_id: int, db: Session = Depends(get_db)):
    task = service.retry_task(db, task_id=task_id)
    return {"ok": True, "data": serialize_task(task)}
