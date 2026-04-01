from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_api_key
from app.api.serializers import serialize_document, serialize_version
from app.db import get_db
from app.schemas.versions import RollbackRequest
from app.services.document_service import DocumentService

router = APIRouter(prefix="/api/docs", tags=["versions"], dependencies=[Depends(require_api_key)])
service = DocumentService()


@router.get("/{doc_id}/versions")
def list_versions(doc_id: int, db: Session = Depends(get_db)):
    versions = service.list_versions(db, doc_id)
    data = [serialize_version(version).model_dump(mode="json") for version in versions]
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
    return {"ok": True, "data": serialize_document(document, blocks).model_dump(mode="json")}
