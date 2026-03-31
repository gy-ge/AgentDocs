from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_api_key
from app.db import get_db
from app.schemas.versions import RollbackRequest
from app.services.document_service import DocumentService

router = APIRouter(prefix="/api/docs", tags=["versions"], dependencies=[Depends(require_api_key)])
service = DocumentService()


@router.get("/{doc_id}/versions")
def list_versions(doc_id: int, db: Session = Depends(get_db)):
    versions = service.list_versions(db, doc_id)
    data = [
        {
            "id": version.id,
            "revision": version.revision,
            "actor": version.actor,
            "note": version.note,
            "created_at": version.created_at,
        }
        for version in versions
    ]
    return {"ok": True, "data": data}


@router.post("/{doc_id}/versions/{version_id}/rollback")
def rollback_version(
    doc_id: int,
    version_id: int,
    payload: RollbackRequest,
    db: Session = Depends(get_db),
):
    document = service.rollback_version(
        db,
        doc_id=doc_id,
        version_id=version_id,
        expected_revision=payload.expected_revision,
        actor=payload.actor,
        note=payload.note,
    )
    blocks = service.parse_document(document.raw_markdown)
    return {
        "ok": True,
        "data": {
            "id": document.id,
            "title": document.title,
            "raw_markdown": document.raw_markdown,
            "revision": document.revision,
            "blocks": [block.__dict__ for block in blocks],
            "updated_at": document.updated_at,
        },
    }
