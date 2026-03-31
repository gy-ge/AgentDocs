from sqlalchemy.orm import Session

from app.models import Document
from app.services.markdown import parse_blocks


class DocumentService:
    def list_documents(self, db: Session) -> list[Document]:
        return db.query(Document).order_by(Document.updated_at.desc()).all()

    def parse_document(self, raw_markdown: str):
        return parse_blocks(raw_markdown)

    def create_document(self, db: Session, title: str, raw_markdown: str) -> Document:
        document = Document(title=title, raw_markdown=raw_markdown)
        db.add(document)
        db.commit()
        db.refresh(document)
        return document
