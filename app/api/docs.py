from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.docs import DocumentCreate
from app.services.document_service import DocumentService

router = APIRouter(prefix="/api/docs", tags=["docs"])
service = DocumentService()


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
        db, title=payload.title, raw_markdown=payload.raw_markdown
    )
    return {
        "ok": True,
        "data": {
            "id": document.id,
            "title": document.title,
            "revision": document.revision,
        },
    }
