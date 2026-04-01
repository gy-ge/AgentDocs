from hashlib import sha256
from difflib import unified_diff

from sqlalchemy.orm import Session

from app.errors import ApiError
from app.models import Task
from app.services.document_service import DocumentService
from app.services.markdown import parse_blocks
from app.time_utils import utcnow


class TaskService:
    def __init__(self) -> None:
        self.document_service = DocumentService()

    STALE_TRACKED_STATUSES = {"pending", "processing", "done"}

    def list_tasks(
        self, db: Session, status: str | None = None, doc_id: int | None = None
    ) -> list[Task]:
        query = db.query(Task)
        if status is not None:
            query = query.filter(Task.status == status)
        if doc_id is not None:
            query = query.filter(Task.doc_id == doc_id)
        return query.order_by(Task.created_at.desc(), Task.id.desc()).all()

    def describe_task(self, db: Session, task: Task) -> dict[str, object]:
        document = self.document_service.get_document(db, task.doc_id)
        is_stale, stale_reason = self._describe_stale_state(task, document.raw_markdown)
        return {
            "is_stale": is_stale,
            "stale_reason": stale_reason,
            "recommended_action": self._recommended_action(task.status, is_stale),
        }

    def describe_tasks(self, db: Session, tasks: list[Task]) -> dict[int, dict[str, object]]:
        documents: dict[int, str] = {}
        descriptions: dict[int, dict[str, object]] = {}
        for task in tasks:
            raw_markdown = documents.get(task.doc_id)
            if raw_markdown is None:
                raw_markdown = self.document_service.get_document(db, task.doc_id).raw_markdown
                documents[task.doc_id] = raw_markdown
            is_stale, stale_reason = self._describe_stale_state(task, raw_markdown)
            descriptions[task.id] = {
                "is_stale": is_stale,
                "stale_reason": stale_reason,
                "recommended_action": self._recommended_action(task.status, is_stale),
            }
        return descriptions

    def get_task(self, db: Session, task_id: int) -> Task:
        task = db.get(Task, task_id)
        if task is None:
            raise ApiError(404, "not_found", "task not found")
        return task

    def get_task_diff(self, db: Session, task_id: int) -> dict[str, object]:
        task = self.get_task(db, task_id)
        if task.result is None:
            raise ApiError(409, "invalid_state", "task has no result diff")

        document = self.document_service.get_document(db, task.doc_id)
        current_text = self._current_text(document.raw_markdown, task)
        is_stale, conflict_reason = self._describe_stale_state(task, document.raw_markdown)
        can_accept = task.status == "done" and not is_stale
        diff = "\n".join(
            unified_diff(
                task.source_text.splitlines(),
                task.result.splitlines(),
                fromfile="source",
                tofile="result",
                lineterm="",
            )
        )
        return {
            "task_id": task.id,
            "doc_id": task.doc_id,
            "current_text": current_text,
            "source_text": task.source_text,
            "result_text": task.result,
            "can_accept": can_accept,
            "conflict_reason": conflict_reason,
            "recommended_action": self._recommended_action(task.status, is_stale),
            "diff": diff,
        }

    def create_task(
        self,
        db: Session,
        doc_id: int,
        action: str,
        instruction: str | None,
        source_text: str,
        start_offset: int,
        end_offset: int,
        doc_revision: int,
    ) -> Task:
        document = self.document_service.get_document(db, doc_id)
        if document.revision != doc_revision:
            raise ApiError(409, "conflict", "document revision mismatch")
        self._validate_range(document.raw_markdown, source_text, start_offset, end_offset)
        self._validate_single_block(document.raw_markdown, start_offset, end_offset)

        task = Task(
            doc_id=doc_id,
            doc_revision=doc_revision,
            start_offset=start_offset,
            end_offset=end_offset,
            source_text=source_text,
            source_hash=self._hash_text(source_text),
            action=action,
            instruction=instruction,
            status="pending",
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        return task

    def pickup_next_task(self, db: Session, agent_name: str) -> Task | None:
        task = (
            db.query(Task)
            .filter(Task.status == "pending")
            .order_by(Task.created_at.asc(), Task.id.asc())
            .first()
        )
        if task is None:
            return None

        task.status = "processing"
        task.agent_name = agent_name
        task.started_at = utcnow()
        db.commit()
        db.refresh(task)
        return task

    def complete_task(
        self,
        db: Session,
        task_id: int,
        result: str | None,
        error_message: str | None,
    ) -> Task:
        task = self.get_task(db, task_id)
        if task.status != "processing":
            raise ApiError(409, "invalid_state", "task is not processing")
        if bool(result) == bool(error_message):
            raise ApiError(
                422,
                "validation_error",
                "provide either result or error_message",
            )

        task.result = result
        task.error_message = error_message
        task.status = "done" if result is not None else "failed"
        task.completed_at = utcnow()
        db.commit()
        db.refresh(task)
        return task

    def accept_task(
        self,
        db: Session,
        task_id: int,
        expected_revision: int,
        actor: str,
        note: str | None,
    ) -> Task:
        task = self.get_task(db, task_id)
        if task.status != "done" or task.result is None:
            raise ApiError(409, "invalid_state", "task is not ready to accept")

        document = self.document_service.get_document(db, task.doc_id)
        if document.revision != expected_revision:
            raise ApiError(409, "conflict", "document revision mismatch")

        current_text = document.raw_markdown[task.start_offset : task.end_offset]
        if current_text != task.source_text:
            raise ApiError(409, "conflict", "task source no longer matches document")
        if self._hash_text(current_text) != task.source_hash:
            raise ApiError(409, "conflict", "task source hash mismatch")

        if task.result == task.source_text:
            task.status = "accepted"
            task.resolved_at = utcnow()
            db.commit()
            db.refresh(task)
            return task

        document.raw_markdown = (
            document.raw_markdown[: task.start_offset]
            + task.result
            + document.raw_markdown[task.end_offset :]
        )
        document.revision += 1
        document.updated_at = utcnow()
        self.document_service._create_version(
            db,
            doc_id=document.id,
            revision=document.revision,
            snapshot=document.raw_markdown,
            actor=actor,
            note=note or "accept task result",
        )
        task.status = "accepted"
        task.resolved_at = utcnow()
        db.commit()
        db.refresh(task)
        return task

    def reject_task(self, db: Session, task_id: int) -> Task:
        task = self.get_task(db, task_id)
        if task.status != "done":
            raise ApiError(409, "invalid_state", "task is not ready to reject")

        task.status = "rejected"
        task.resolved_at = utcnow()
        db.commit()
        db.refresh(task)
        return task

    def cancel_task(self, db: Session, task_id: int) -> Task:
        task = self.get_task(db, task_id)
        if task.status not in {"pending", "processing"}:
            raise ApiError(409, "invalid_state", "task cannot be cancelled")

        task.status = "cancelled"
        task.resolved_at = utcnow()
        db.commit()
        db.refresh(task)
        return task

    def retry_task(self, db: Session, task_id: int) -> Task:
        task = self.get_task(db, task_id)
        if task.status not in {"failed", "cancelled", "rejected"}:
            raise ApiError(409, "invalid_state", "task cannot be retried")

        document = self.document_service.get_document(db, task.doc_id)
        self._validate_range(
            document.raw_markdown,
            task.source_text,
            task.start_offset,
            task.end_offset,
        )
        self._validate_single_block(
            document.raw_markdown,
            task.start_offset,
            task.end_offset,
        )

        task.doc_revision = document.revision
        task.result = None
        task.status = "pending"
        task.agent_name = None
        task.error_message = None
        task.started_at = None
        task.completed_at = None
        task.resolved_at = None
        db.commit()
        db.refresh(task)
        return task

    def cleanup_stale_tasks(self, db: Session, doc_id: int) -> dict[str, int]:
        self.document_service.get_document(db, doc_id)
        tasks = (
            db.query(Task)
            .filter(Task.doc_id == doc_id)
            .filter(Task.status.in_(["pending", "processing", "done"]))
            .order_by(Task.id.asc())
            .all()
        )
        cancelled = 0
        rejected = 0
        unchanged = 0
        raw_markdown = self.document_service.get_document(db, doc_id).raw_markdown
        now = utcnow()
        for task in tasks:
            is_stale, _ = self._detect_stale(task, raw_markdown)
            if not is_stale:
                unchanged += 1
                continue
            if task.status == "done":
                task.status = "rejected"
                task.resolved_at = now
                rejected += 1
                continue
            task.status = "cancelled"
            task.resolved_at = now
            cancelled += 1
        db.commit()
        return {
            "cancelled": cancelled,
            "rejected": rejected,
            "unchanged": unchanged,
        }

    def _validate_range(
        self, raw_markdown: str, source_text: str, start_offset: int, end_offset: int
    ) -> None:
        if start_offset < 0 or end_offset <= start_offset:
            raise ApiError(422, "validation_error", "invalid source range")
        if end_offset > len(raw_markdown):
            raise ApiError(422, "validation_error", "source range exceeds document")
        if raw_markdown[start_offset:end_offset] != source_text:
            raise ApiError(422, "validation_error", "source_text mismatch")

    def _validate_single_block(
        self, raw_markdown: str, start_offset: int, end_offset: int
    ) -> None:
        blocks = parse_blocks(raw_markdown)
        for block in blocks:
            if start_offset >= block.start_offset and end_offset <= block.end_offset:
                return
        raise ApiError(422, "validation_error", "task range must stay within one block")

    def _hash_text(self, value: str) -> str:
        return sha256(value.encode("utf-8")).hexdigest()

    def _current_text(self, raw_markdown: str, task: Task) -> str:
        start = min(max(task.start_offset, 0), len(raw_markdown))
        end = min(max(task.end_offset, start), len(raw_markdown))
        return raw_markdown[start:end]

    def _describe_stale_state(
        self, task: Task, raw_markdown: str
    ) -> tuple[bool, str | None]:
        if task.status not in self.STALE_TRACKED_STATUSES:
            return False, None
        return self._detect_stale(task, raw_markdown)

    def _detect_stale(self, task: Task, raw_markdown: str) -> tuple[bool, str | None]:
        current_text = self._current_text(raw_markdown, task)
        if current_text == task.source_text and self._hash_text(current_text) == task.source_hash:
            return False, None
        return True, self._build_conflict_reason(task, raw_markdown)

    def _recommended_action(self, status: str, is_stale: bool) -> str | None:
        if not is_stale:
            return None
        if status == "done":
            return "reject"
        if status in {"pending", "processing"}:
            return "cancel"
        return None

    def _build_conflict_reason(self, task: Task, raw_markdown: str) -> str:
        current_text = self._current_text(raw_markdown, task)
        if task.start_offset >= len(raw_markdown):
            return "selection_removed"
        if not current_text:
            return "selection_removed"
        if len(current_text) != len(task.source_text):
            return "selection_shifted"
        return "source_changed"
