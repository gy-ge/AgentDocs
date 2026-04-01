from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_api_key
from app.api.serializers import serialize_task, serialize_task_diff, serialize_task_relocation
from app.db import get_db
from app.schemas.tasks import (
    TaskAcceptRequest,
    TaskCompleteRequest,
    TaskNextRequest,
)
from app.services.task_service import TaskService

router = APIRouter(prefix="/api/tasks", tags=["tasks"], dependencies=[Depends(require_api_key)])
service = TaskService()


@router.get("")
def list_tasks(
    status: str | None = Query(default=None),
    doc_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    tasks = service.list_tasks(db, status=status, doc_id=doc_id)
    task_descriptions = service.describe_tasks(db, tasks)
    return {
        "ok": True,
        "data": [
            serialize_task(task, **task_descriptions[task.id]).model_dump(mode="json")
            for task in tasks
        ],
    }


@router.get("/{task_id}")
def get_task(task_id: int, db: Session = Depends(get_db)):
    task = service.get_task(db, task_id)
    description = service.describe_task(db, task)
    return {
        "ok": True,
        "data": serialize_task(
            task,
            **description,
            context=service.build_task_context(db, task),
        ).model_dump(mode="json"),
    }


@router.get("/{task_id}/diff")
def get_task_diff(task_id: int, db: Session = Depends(get_db)):
    diff_data = service.get_task_diff(db, task_id)
    return {"ok": True, "data": serialize_task_diff(diff_data).model_dump(mode="json")}


@router.post("/next")
def pickup_next_task(payload: TaskNextRequest, db: Session = Depends(get_db)):
    task = service.pickup_next_task(db, agent_name=payload.agent_name)
    description = None if task is None else service.describe_task(db, task)
    return {
        "ok": True,
        "data": None
        if task is None
        else serialize_task(
            task,
            **description,
            context=service.build_task_context(db, task),
        ).model_dump(mode="json"),
    }


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
    return {"ok": True, "data": serialize_task(task).model_dump(mode="json")}


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
    return {"ok": True, "data": serialize_task(task).model_dump(mode="json")}


@router.post("/{task_id}/reject")
def reject_task(task_id: int, db: Session = Depends(get_db)):
    task = service.reject_task(db, task_id=task_id)
    return {"ok": True, "data": serialize_task(task).model_dump(mode="json")}


@router.post("/{task_id}/cancel")
def cancel_task(task_id: int, db: Session = Depends(get_db)):
    task = service.cancel_task(db, task_id=task_id)
    return {"ok": True, "data": serialize_task(task).model_dump(mode="json")}


@router.post("/{task_id}/retry")
def retry_task(task_id: int, db: Session = Depends(get_db)):
    task = service.retry_task(db, task_id=task_id)
    return {"ok": True, "data": serialize_task(task).model_dump(mode="json")}


@router.post("/{task_id}/relocate")
def relocate_task(task_id: int, db: Session = Depends(get_db)):
    task, relocation_strategy = service.relocate_task(db, task_id=task_id)
    description = service.describe_task(db, task)
    return {
        "ok": True,
        "data": serialize_task_relocation(
            task,
            relocation_strategy=relocation_strategy,
            **description,
            context=service.build_task_context(db, task),
        ).model_dump(mode="json"),
    }
