"""Document and task API endpoints.

Provides document CRUD, task creation, stale cleanup,
and batch-accept operations under ``/api/docs``.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_api_key
from app.api.serializers import (
    serialize_batch_accept,
    serialize_batch_accept_preview,
    serialize_document,
    serialize_document_list_item,
    serialize_stale_cleanup,
    serialize_task,
)
from app.db import get_db
from app.schemas.docs import DocumentCreate, DocumentUpdate, TaskDefaultsUpdate
from app.schemas.tasks import TaskBatchActionRequest, TaskCreate
from app.services.document_service import DocumentService
from app.services.task_events import task_event_broker
from app.services.task_service import TaskService

router = APIRouter(prefix="/api/docs", tags=["docs"], dependencies=[Depends(require_api_key)])
service = DocumentService()
task_service = TaskService()


@router.get("")
def list_docs(db: Session = Depends(get_db)):
    documents = service.list_documents(db)
    data = [serialize_document_list_item(document).model_dump(mode="json") for document in documents]
    return {"ok": True, "data": data}


@router.post("")
def create_doc(payload: DocumentCreate, db: Session = Depends(get_db)):
    document = service.create_document(
        db, title=payload.title, raw_markdown=payload.raw_markdown, actor=payload.actor
    )
    task_event_broker.publish_document(
        kind="created",
        doc_id=document.id,
        revision=document.revision,
    )
    return {
        "ok": True,
        "data": {
            "id": document.id,
            "title": document.title,
            "revision": document.revision,
        },
    }


@router.get("/{doc_id}")
def get_doc(doc_id: int, db: Session = Depends(get_db)):
    document = service.get_document(db, doc_id)
    blocks = service.parse_document(document.raw_markdown)
    return {"ok": True, "data": serialize_document(document, blocks).model_dump(mode="json")}


@router.put("/{doc_id}")
def update_doc(doc_id: int, payload: DocumentUpdate, db: Session = Depends(get_db)):
    document = service.update_document(
        db,
        doc_id=doc_id,
        title=payload.title,
        raw_markdown=payload.raw_markdown,
        expected_revision=payload.expected_revision,
        actor=payload.actor,
        note=payload.note,
    )
    task_event_broker.publish_document(
        kind="updated",
        doc_id=document.id,
        revision=document.revision,
    )
    blocks = service.parse_document(document.raw_markdown)
    return {"ok": True, "data": serialize_document(document, blocks).model_dump(mode="json")}


@router.delete("/{doc_id}")
def delete_doc(doc_id: int, db: Session = Depends(get_db)):
    service.delete_document(db, doc_id)
    task_event_broker.publish_document(
        kind="deleted",
        doc_id=doc_id,
        revision=None,
    )
    return {"ok": True, "data": {"id": doc_id}}


@router.post("/{doc_id}/task-defaults")
def update_doc_task_defaults(
    doc_id: int, payload: TaskDefaultsUpdate, db: Session = Depends(get_db)
):
    document = service.update_task_defaults(
        db,
        doc_id,
        actor=payload.actor,
        default_task_action=payload.default_task_action,
        default_task_instruction=payload.default_task_instruction,
    )
    task_event_broker.publish_document(
        kind="task_defaults_updated",
        doc_id=document.id,
        revision=document.revision,
    )
    blocks = service.parse_document(document.raw_markdown)
    return {"ok": True, "data": serialize_document(document, blocks).model_dump(mode="json")}


@router.post("/{doc_id}/tasks")
def create_doc_task(doc_id: int, payload: TaskCreate, db: Session = Depends(get_db)):
    task = task_service.create_task(
        db,
        doc_id=doc_id,
        action=payload.action,
        instruction=payload.instruction,
        source_text=payload.source_text,
        start_offset=payload.start_offset,
        end_offset=payload.end_offset,
        doc_revision=payload.doc_revision,
    )
    task_event_broker.publish_task(
        kind="created",
        task_id=task.id,
        doc_id=task.doc_id,
        status=task.status,
        doc_revision=task.doc_revision,
    )
    return {
        "ok": True,
        "data": serialize_task(task).model_dump(mode="json"),
    }


@router.post("/{doc_id}/tasks/cleanup-stale")
def cleanup_doc_stale_tasks(doc_id: int, db: Session = Depends(get_db)):
    result = task_service.cleanup_stale_tasks(db, doc_id)
    task_event_broker.publish_tasks(
        kind="cleanup_stale",
        doc_id=doc_id,
        cancelled=result["cancelled"],
        rejected=result["rejected"],
    )
    return {
        "ok": True,
        "data": serialize_stale_cleanup(doc_id, **result).model_dump(mode="json"),
    }


@router.post("/{doc_id}/tasks/accept-ready-preview")
def preview_accept_ready_doc_tasks(
    doc_id: int, payload: TaskBatchActionRequest, db: Session = Depends(get_db)
):
    result = task_service.preview_accept_ready_tasks(
        db,
        doc_id=doc_id,
        action=payload.action,
        start_offset=payload.start_offset,
        end_offset=payload.end_offset,
        limit=payload.limit,
    )
    return {"ok": True, "data": serialize_batch_accept_preview(result).model_dump(mode="json")}


@router.post("/{doc_id}/tasks/accept-ready")
def accept_ready_doc_tasks(
    doc_id: int, payload: TaskBatchActionRequest, db: Session = Depends(get_db)
):
    result = task_service.accept_ready_tasks(
        db,
        doc_id=doc_id,
        actor=payload.actor,
        note=payload.note,
        action=payload.action,
        start_offset=payload.start_offset,
        end_offset=payload.end_offset,
        limit=payload.limit,
    )
    task_event_broker.publish_tasks(
        kind="accept_ready",
        doc_id=doc_id,
        doc_revision=int(result["document_revision"]),
        document_changed=bool(result["accepted"]),
        accepted_task_ids=list(result["accepted_task_ids"]),
        skipped=int(result["skipped"]),
    )
    if result["accepted"]:
        task_event_broker.publish_document(
            kind="tasks_accepted",
            doc_id=doc_id,
            revision=int(result["document_revision"]),
        )
    return {"ok": True, "data": serialize_batch_accept(result).model_dump(mode="json")}
