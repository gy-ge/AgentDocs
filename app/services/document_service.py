from sqlalchemy.orm import Session

from app.errors import ApiError
from app.models import Document, DocumentVersion
from app.services.markdown import parse_blocks
from app.time_utils import utcnow


class DocumentService:
    def list_documents(self, db: Session) -> list[Document]:
        return db.query(Document).order_by(Document.updated_at.desc()).all()

    def get_document(self, db: Session, doc_id: int) -> Document:
        document = db.get(Document, doc_id)
        if document is None:
            raise ApiError(404, "not_found", "document not found")
        return document

    def parse_document(self, raw_markdown: str):
        return parse_blocks(raw_markdown)

    def create_document(
        self, db: Session, title: str, raw_markdown: str, actor: str
    ) -> Document:
        document = Document(title=title, raw_markdown=raw_markdown)
        db.add(document)
        db.flush()
        self._create_version(
            db,
            doc_id=document.id,
            revision=document.revision,
            snapshot=document.raw_markdown,
            actor=actor,
            note="document created",
        )
        db.commit()
        db.refresh(document)
        return document

    def update_document(
        self,
        db: Session,
        doc_id: int,
        title: str,
        raw_markdown: str,
        expected_revision: int,
        actor: str,
        note: str | None,
    ) -> Document:
        document = self.get_document(db, doc_id)
        if document.revision != expected_revision:
            raise ApiError(409, "conflict", "document revision mismatch")

        title_changed = document.title != title
        content_changed = document.raw_markdown != raw_markdown

        if not title_changed and not content_changed:
            return document

        document.title = title
        document.updated_at = utcnow()

        if not content_changed:
            db.commit()
            db.refresh(document)
            return document

        document.raw_markdown = raw_markdown
        document.revision += 1
        self._create_version(
            db,
            doc_id=document.id,
            revision=document.revision,
            snapshot=document.raw_markdown,
            actor=actor,
            note=note or "manual edit",
        )
        db.commit()
        db.refresh(document)
        return document

    def delete_document(self, db: Session, doc_id: int) -> None:
        document = self.get_document(db, doc_id)
        db.delete(document)
        db.commit()

    def list_versions(self, db: Session, doc_id: int) -> list[DocumentVersion]:
        self.get_document(db, doc_id)
        return (
            db.query(DocumentVersion)
            .filter(DocumentVersion.doc_id == doc_id)
            .order_by(DocumentVersion.revision.desc(), DocumentVersion.created_at.desc())
            .all()
        )

    def rollback_version(
        self,
        db: Session,
        doc_id: int,
        version_id: int,
        expected_revision: int,
        actor: str,
        note: str | None,
    ) -> Document:
        document = self.get_document(db, doc_id)
        if document.revision != expected_revision:
            raise ApiError(409, "conflict", "document revision mismatch")

        version = db.get(DocumentVersion, version_id)
        if version is None or version.doc_id != doc_id:
            raise ApiError(404, "not_found", "version not found")

        if document.raw_markdown == version.snapshot:
            return document

        document.raw_markdown = version.snapshot
        document.revision += 1
        document.updated_at = utcnow()
        self._create_version(
            db,
            doc_id=document.id,
            revision=document.revision,
            snapshot=document.raw_markdown,
            actor=actor,
            note=note or f"rollback to version {version.id}",
        )
        db.commit()
        db.refresh(document)
        return document

    def _create_version(
        self,
        db: Session,
        doc_id: int,
        revision: int,
        snapshot: str,
        actor: str,
        note: str | None,
    ) -> DocumentVersion:
        version = DocumentVersion(
            doc_id=doc_id,
            revision=revision,
            snapshot=snapshot,
            actor=actor,
            note=note,
        )
        db.add(version)
        return version
