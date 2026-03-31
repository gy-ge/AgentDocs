from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_api_key
from app.db import get_db
from app.schemas.docs import DocumentCreate, DocumentUpdate
from app.schemas.tasks import TaskCreate
from app.services.document_service import DocumentService
from app.services.task_service import TaskService

router = APIRouter(prefix="/api/docs", tags=["docs"], dependencies=[Depends(require_api_key)])
service = DocumentService()
task_service = TaskService()


def serialize_document(document, blocks):
    return {
        "id": document.id,
        "title": document.title,
        "raw_markdown": document.raw_markdown,
        "revision": document.revision,
        "blocks": [block.__dict__ for block in blocks],
        "updated_at": document.updated_at,
    }


@router.get("")
def list_docs(db: Session = Depends(get_db)):
    documents = service.list_documents(db)
    data = [
        {
            "id": document.id,
            "title": document.title,
            "revision": document.revision,
            "updated_at": document.updated_at,
        }
        for document in documents
    ]
    return {"ok": True, "data": data}


@router.post("")
def create_doc(payload: DocumentCreate, db: Session = Depends(get_db)):
    document = service.create_document(
        db, title=payload.title, raw_markdown=payload.raw_markdown, actor=payload.actor
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
    return {"ok": True, "data": serialize_document(document, blocks)}


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
    blocks = service.parse_document(document.raw_markdown)
    return {"ok": True, "data": serialize_document(document, blocks)}


@router.delete("/{doc_id}")
def delete_doc(doc_id: int, db: Session = Depends(get_db)):
    service.delete_document(db, doc_id)
    return {"ok": True, "data": {"id": doc_id}}


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
    return {
        "ok": True,
        "data": {
            "id": task.id,
            "doc_id": task.doc_id,
            "status": task.status,
            "action": task.action,
        },
    }
