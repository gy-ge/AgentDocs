from hashlib import sha256
from difflib import unified_diff

from sqlalchemy.orm import Session

from app.errors import ApiError
from app.models import DocumentVersion, Task
from app.services.document_service import DocumentService
from app.services.markdown import parse_blocks
from app.time_utils import utcnow


class TaskService:
    TASK_CONTEXT_WINDOW = 200
    RELOCATABLE_STATUSES = {"pending", "done", "failed", "cancelled", "rejected"}

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

    def build_task_context(self, db: Session, task: Task) -> dict[str, object]:
        document = self.document_service.get_document(db, task.doc_id)
        return self._build_task_context(
            task,
            document_title=document.title,
            document_revision=document.revision,
            raw_markdown=document.raw_markdown,
        )

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

        self._apply_task_accept(db, document, task, actor=actor, note=note)
        db.commit()
        db.refresh(task)
        return task

    def accept_ready_tasks(
        self,
        db: Session,
        doc_id: int,
        actor: str,
        note: str | None,
        action: str | None = None,
        start_offset: int | None = None,
        end_offset: int | None = None,
        limit: int | None = None,
    ) -> dict[str, object]:
        document = self.document_service.get_document(db, doc_id)
        if (start_offset is None) != (end_offset is None):
            raise ApiError(422, "validation_error", "provide both start_offset and end_offset")
        if start_offset is not None and (start_offset < 0 or end_offset is None or end_offset <= start_offset):
            raise ApiError(422, "validation_error", "invalid batch range")

        query = db.query(Task).filter(Task.doc_id == doc_id).filter(Task.status == "done")
        if action is not None:
            query = query.filter(Task.action == action)
        if start_offset is not None and end_offset is not None:
            query = query.filter(Task.start_offset >= start_offset).filter(Task.end_offset <= end_offset)
        query = query.order_by(Task.start_offset.desc(), Task.id.desc())
        if limit is not None:
            query = query.limit(limit)
        tasks = query.all()

        accepted_task_ids: list[int] = []
        skipped_tasks: list[dict[str, object]] = []
        for task in tasks:
            if task.result is None:
                skipped_tasks.append({"task_id": task.id, "reason": "missing_result"})
                continue
            is_stale, _ = self._detect_stale(task, document.raw_markdown)
            if is_stale:
                skipped_tasks.append({"task_id": task.id, "reason": "task_stale"})
                continue
            try:
                self._apply_task_accept(db, document, task, actor=actor, note=note or "bulk accept")
            except ApiError as exc:
                skipped_tasks.append({"task_id": task.id, "reason": exc.code})
                continue
            accepted_task_ids.append(task.id)

        db.commit()
        return {
            "doc_id": doc_id,
            "document_revision": document.revision,
            "accepted": len(accepted_task_ids),
            "skipped": len(skipped_tasks),
            "accepted_task_ids": accepted_task_ids,
            "skipped_tasks": skipped_tasks,
        }

    def relocate_task(self, db: Session, task_id: int) -> tuple[Task, str]:
        task = self.get_task(db, task_id)
        if task.status == "processing":
            raise ApiError(409, "invalid_state", "processing task cannot be relocated")
        if task.status == "accepted":
            raise ApiError(409, "invalid_state", "accepted task does not need relocation")
        if task.status not in self.RELOCATABLE_STATUSES:
            raise ApiError(409, "invalid_state", "task cannot be relocated")

        document = self.document_service.get_document(db, task.doc_id)
        current_text = self._current_text(document.raw_markdown, task)
        if current_text == task.source_text and self._hash_text(current_text) == task.source_hash:
            task.doc_revision = document.revision
            db.commit()
            db.refresh(task)
            return task, "current_selection_match"

        relocation = self._find_relocation_target(db, task, document.raw_markdown)
        if relocation is None:
            raise ApiError(409, "conflict", "unable to relocate task on current document")

        task.start_offset = relocation["start_offset"]
        task.end_offset = relocation["end_offset"]
        task.doc_revision = document.revision
        db.commit()
        db.refresh(task)
        return task, str(relocation["strategy"])

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

    def _apply_task_accept(
        self,
        db: Session,
        document,
        task: Task,
        *,
        actor: str,
        note: str | None,
    ) -> None:
        current_text = document.raw_markdown[task.start_offset : task.end_offset]
        if current_text != task.source_text:
            raise ApiError(409, "conflict", "task source no longer matches document")
        if self._hash_text(current_text) != task.source_hash:
            raise ApiError(409, "conflict", "task source hash mismatch")

        now = utcnow()
        if task.result == task.source_text:
            task.status = "accepted"
            task.resolved_at = now
            return

        document.raw_markdown = (
            document.raw_markdown[: task.start_offset]
            + task.result
            + document.raw_markdown[task.end_offset :]
        )
        document.revision += 1
        document.updated_at = now
        self.document_service._create_version(
            db,
            doc_id=document.id,
            revision=document.revision,
            snapshot=document.raw_markdown,
            actor=actor,
            note=note or "accept task result",
        )
        task.status = "accepted"
        task.resolved_at = now

    def _current_text(self, raw_markdown: str, task: Task) -> str:
        start, end = self._selection_bounds(raw_markdown, task)
        return raw_markdown[start:end]

    def _build_task_context(
        self,
        task: Task,
        *,
        document_title: str,
        document_revision: int,
        raw_markdown: str,
    ) -> dict[str, object]:
        start, end = self._selection_bounds(raw_markdown, task)
        block = self._find_matching_block(raw_markdown, task)
        block_data: dict[str, object] | None = None
        block_markdown: str | None = None
        if block is not None:
            block_data = {
                "heading": block.heading,
                "level": block.level,
                "position": block.position,
                "start_offset": block.start_offset,
                "end_offset": block.end_offset,
            }
            block_markdown = raw_markdown[block.start_offset : block.end_offset]

        return {
            "document_title": document_title,
            "document_revision": document_revision,
            "block": block_data,
            "block_markdown": block_markdown,
            "context_before": raw_markdown[max(0, start - self.TASK_CONTEXT_WINDOW) : start],
            "context_after": raw_markdown[end : min(len(raw_markdown), end + self.TASK_CONTEXT_WINDOW)],
        }

    def _selection_bounds(self, raw_markdown: str, task: Task) -> tuple[int, int]:
        start = min(max(task.start_offset, 0), len(raw_markdown))
        end = min(max(task.end_offset, start), len(raw_markdown))
        return start, end

    def _find_matching_block(self, raw_markdown: str, task: Task):
        start, end = self._selection_bounds(raw_markdown, task)
        for block in parse_blocks(raw_markdown):
            if start >= block.start_offset and end <= block.end_offset:
                return block
        return None

    def _find_relocation_target(
        self, db: Session, task: Task, raw_markdown: str
    ) -> dict[str, object] | None:
        original_snapshot = self._snapshot_for_revision(db, task.doc_id, task.doc_revision)
        original_block = None
        if original_snapshot is not None:
            original_block = self._find_matching_block(original_snapshot, task)

        if original_block is not None:
            candidate = self._find_same_block_relocation(raw_markdown, task.source_text, original_block)
            if candidate is not None:
                return candidate

        return self._find_document_unique_relocation(raw_markdown, task.source_text)

    def _snapshot_for_revision(
        self, db: Session, doc_id: int, revision: int
    ) -> str | None:
        version = (
            db.query(DocumentVersion)
            .filter(DocumentVersion.doc_id == doc_id)
            .filter(DocumentVersion.revision == revision)
            .order_by(DocumentVersion.created_at.desc(), DocumentVersion.id.desc())
            .first()
        )
        return None if version is None else version.snapshot

    def _find_same_block_relocation(
        self, raw_markdown: str, source_text: str, original_block
    ) -> dict[str, object] | None:
        blocks = parse_blocks(raw_markdown)
        if original_block.position < len(blocks):
            positioned_block = blocks[original_block.position]
            if (
                positioned_block.heading == original_block.heading
                and positioned_block.level == original_block.level
            ):
                matches = self._find_text_matches(
                    raw_markdown,
                    source_text,
                    start_offset=positioned_block.start_offset,
                    end_offset=positioned_block.end_offset,
                )
                if len(matches) == 1:
                    start_offset, end_offset = matches[0]
                    return {
                        "start_offset": start_offset,
                        "end_offset": end_offset,
                        "strategy": "same_block_position_match",
                    }

        heading_matches = [
            block
            for block in blocks
            if block.heading == original_block.heading and block.level == original_block.level
        ]
        if len(heading_matches) != 1:
            return None

        matches = self._find_text_matches(
            raw_markdown,
            source_text,
            start_offset=heading_matches[0].start_offset,
            end_offset=heading_matches[0].end_offset,
        )
        if len(matches) != 1:
            return None

        start_offset, end_offset = matches[0]
        return {
            "start_offset": start_offset,
            "end_offset": end_offset,
            "strategy": "same_heading_unique_match",
        }

    def _find_document_unique_relocation(
        self, raw_markdown: str, source_text: str
    ) -> dict[str, object] | None:
        matches = self._find_text_matches(raw_markdown, source_text)
        if len(matches) != 1:
            return None

        start_offset, end_offset = matches[0]
        if not self._is_within_single_block(raw_markdown, start_offset, end_offset):
            return None
        return {
            "start_offset": start_offset,
            "end_offset": end_offset,
            "strategy": "document_unique_match",
        }

    def _find_text_matches(
        self,
        raw_markdown: str,
        source_text: str,
        *,
        start_offset: int = 0,
        end_offset: int | None = None,
    ) -> list[tuple[int, int]]:
        if not source_text:
            return []

        end_offset = len(raw_markdown) if end_offset is None else end_offset
        matches: list[tuple[int, int]] = []
        search_start = start_offset
        while search_start < end_offset:
            found_at = raw_markdown.find(source_text, search_start, end_offset)
            if found_at == -1:
                break
            matches.append((found_at, found_at + len(source_text)))
            search_start = found_at + 1
        return matches

    def _is_within_single_block(
        self, raw_markdown: str, start_offset: int, end_offset: int
    ) -> bool:
        blocks = parse_blocks(raw_markdown)
        return any(
            start_offset >= block.start_offset and end_offset <= block.end_offset
            for block in blocks
        )

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
