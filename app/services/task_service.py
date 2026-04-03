"""Task lifecycle service.

Handles task creation, pickup, completion, accept, reject, cancel, retry,
batch-accept, stale detection, cleanup, relocation, diff generation, and
recovery (relocate / requeue-from-current).
"""

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
    RECOVERABLE_STATUSES = {"pending", "processing", "done", "failed", "cancelled", "rejected"}

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
        if (result is not None) == (error_message is not None):
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
        self._validate_batch_accept_filters(start_offset=start_offset, end_offset=end_offset)
        tasks = self._list_batch_accept_tasks(
            db,
            doc_id=doc_id,
            action=action,
            start_offset=start_offset,
            end_offset=end_offset,
            limit=limit,
        )
        rollback_version_id = self._current_version_id(
            db,
            doc_id=doc_id,
            revision=document.revision,
        )
        rollback_revision = document.revision

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
            "rollback_version_id": rollback_version_id if accepted_task_ids else None,
            "rollback_revision": rollback_revision if accepted_task_ids else None,
        }

    def preview_accept_ready_tasks(
        self,
        db: Session,
        doc_id: int,
        action: str | None = None,
        start_offset: int | None = None,
        end_offset: int | None = None,
        limit: int | None = None,
    ) -> dict[str, object]:
        document = self.document_service.get_document(db, doc_id)
        self._validate_batch_accept_filters(start_offset=start_offset, end_offset=end_offset)
        tasks = self._list_batch_accept_tasks(
            db,
            doc_id=doc_id,
            action=action,
            start_offset=start_offset,
            end_offset=end_offset,
            limit=limit,
        )

        working_markdown = document.raw_markdown
        accepted_task_ids: list[int] = []
        accepted_tasks: list[dict[str, object]] = []
        skipped_tasks: list[dict[str, object]] = []
        for task in tasks:
            preview_item = self._serialize_batch_preview_item(working_markdown, task)
            if task.result is None:
                skipped_tasks.append({**preview_item, "reason": "missing_result"})
                continue
            is_stale, _ = self._detect_stale(task, working_markdown)
            if is_stale:
                skipped_tasks.append({**preview_item, "reason": "task_stale"})
                continue

            accepted_task_ids.append(task.id)
            accepted_tasks.append(preview_item)
            if task.result != task.source_text:
                working_markdown = (
                    working_markdown[: task.start_offset]
                    + task.result
                    + working_markdown[task.end_offset :]
                )

        return {
            "doc_id": doc_id,
            "document_revision": document.revision,
            "action": action,
            "start_offset": start_offset,
            "end_offset": end_offset,
            "limit": limit,
            "matched": len(tasks),
            "will_accept": len(accepted_task_ids),
            "will_skip": len(skipped_tasks),
            "accepted_task_ids": accepted_task_ids,
            "accepted_tasks": accepted_tasks,
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

    def preview_task_recovery(self, db: Session, task_id: int) -> dict[str, object]:
        task = self.get_task(db, task_id)
        document = self.document_service.get_document(db, task.doc_id)
        is_stale, stale_reason = self._describe_stale_state(task, document.raw_markdown)
        start_offset, end_offset = self._selection_bounds(document.raw_markdown, task)
        relocation_strategy = self._detect_relocation_strategy(db, task, document.raw_markdown)
        can_requeue, requeue_reason = self._can_requeue_from_current(
            task,
            raw_markdown=document.raw_markdown,
            start_offset=start_offset,
            end_offset=end_offset,
            is_stale=is_stale,
        )

        return {
            "task_id": task.id,
            "doc_id": task.doc_id,
            "task_status": task.status,
            "is_stale": is_stale,
            "stale_reason": stale_reason,
            "current_document_revision": document.revision,
            "current_start_offset": start_offset,
            "current_end_offset": end_offset,
            "current_selection_text": document.raw_markdown[start_offset:end_offset],
            "can_relocate": relocation_strategy is not None,
            "relocation_strategy": relocation_strategy,
            "can_requeue_from_current": can_requeue,
            "requeue_reason": requeue_reason,
            "recommended_mode": self._recommended_recovery_mode(
                is_stale=is_stale,
                relocation_strategy=relocation_strategy,
                can_requeue=can_requeue,
            ),
            "context": self._build_task_context(
                task,
                document_title=document.title,
                document_revision=document.revision,
                raw_markdown=document.raw_markdown,
            ),
        }

    def recover_task(
        self, db: Session, task_id: int, *, mode: str, actor: str
    ) -> dict[str, object]:
        if mode == "relocate":
            task, relocation_strategy = self.relocate_task(db, task_id=task_id)
            description = self.describe_task(db, task)
            return {
                "mode": mode,
                "source_task": self._serialize_task_payload(
                    db,
                    task,
                    description=description,
                ),
                "new_task": None,
                "relocation_strategy": relocation_strategy,
                "closed_source_status": None,
            }

        if mode != "requeue_from_current":
            raise ApiError(422, "validation_error", "unsupported recovery mode")

        task = self.get_task(db, task_id)
        if task.status == "accepted":
            raise ApiError(409, "invalid_state", "accepted task does not need recovery")

        document = self.document_service.get_document(db, task.doc_id)
        is_stale, _ = self._describe_stale_state(task, document.raw_markdown)
        start_offset, end_offset = self._selection_bounds(document.raw_markdown, task)
        can_requeue, requeue_reason = self._can_requeue_from_current(
            task,
            raw_markdown=document.raw_markdown,
            start_offset=start_offset,
            end_offset=end_offset,
            is_stale=is_stale,
        )
        if not can_requeue:
            raise ApiError(409, "conflict", requeue_reason or "task cannot be recovered")

        now = utcnow()
        closed_source_status = self._close_task_for_requeue(task, now=now)
        current_selection_text = document.raw_markdown[start_offset:end_offset]
        new_task = Task(
            doc_id=task.doc_id,
            doc_revision=document.revision,
            start_offset=start_offset,
            end_offset=end_offset,
            source_text=current_selection_text,
            source_hash=self._hash_text(current_selection_text),
            action=task.action,
            instruction=task.instruction,
            status="pending",
        )
        db.add(new_task)
        db.commit()
        db.refresh(task)
        db.refresh(new_task)

        return {
            "mode": mode,
            "source_task": self._serialize_task_payload(db, task),
            "new_task": self._serialize_task_payload(db, new_task),
            "relocation_strategy": None,
            "closed_source_status": closed_source_status,
        }

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
        document = self.document_service.get_document(db, doc_id)
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
        raw_markdown = document.raw_markdown
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

    def _validate_batch_accept_filters(
        self,
        *,
        start_offset: int | None,
        end_offset: int | None,
    ) -> None:
        if (start_offset is None) != (end_offset is None):
            raise ApiError(422, "validation_error", "provide both start_offset and end_offset")
        if start_offset is not None and (start_offset < 0 or end_offset is None or end_offset <= start_offset):
            raise ApiError(422, "validation_error", "invalid batch range")

    def _list_batch_accept_tasks(
        self,
        db: Session,
        *,
        doc_id: int,
        action: str | None,
        start_offset: int | None,
        end_offset: int | None,
        limit: int | None,
    ) -> list[Task]:
        query = db.query(Task).filter(Task.doc_id == doc_id).filter(Task.status == "done")
        if action is not None:
            query = query.filter(Task.action == action)
        if start_offset is not None and end_offset is not None:
            query = query.filter(Task.start_offset >= start_offset).filter(Task.end_offset <= end_offset)
        query = query.order_by(Task.start_offset.desc(), Task.id.desc())
        if limit is not None:
            query = query.limit(limit)
        return query.all()

    def _serialize_batch_preview_item(
        self,
        raw_markdown: str,
        task: Task,
    ) -> dict[str, object]:
        block = self._find_matching_block(raw_markdown, task)
        return {
            "task_id": task.id,
            "action": task.action,
            "heading": None if block is None or not block.heading else block.heading,
            "start_offset": task.start_offset,
            "end_offset": task.end_offset,
            "source_text": task.source_text,
            "result_text": task.result,
            "reason": None,
        }

    def _current_version_id(
        self,
        db: Session,
        *,
        doc_id: int,
        revision: int,
    ) -> int | None:
        version = (
            db.query(DocumentVersion)
            .filter(DocumentVersion.doc_id == doc_id)
            .filter(DocumentVersion.revision == revision)
            .order_by(DocumentVersion.created_at.desc(), DocumentVersion.id.desc())
            .first()
        )
        return None if version is None else int(version.id)

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
        self._sync_related_tasks_after_document_change(
            db,
            document_id=document.id,
            accepted_task_id=task.id,
            raw_markdown=document.raw_markdown,
            revision=document.revision,
        )

    def _sync_related_tasks_after_document_change(
        self,
        db: Session,
        *,
        document_id: int,
        accepted_task_id: int,
        raw_markdown: str,
        revision: int,
    ) -> None:
        related_tasks = (
            db.query(Task)
            .filter(Task.doc_id == document_id)
            .filter(Task.id != accepted_task_id)
            .filter(Task.status.in_(sorted(self.RELOCATABLE_STATUSES)))
            .order_by(Task.id.asc())
            .all()
        )
        for related_task in related_tasks:
            self._sync_task_reference_to_document(
                db,
                task=related_task,
                raw_markdown=raw_markdown,
                revision=revision,
            )

    def _sync_task_reference_to_document(
        self,
        db: Session,
        *,
        task: Task,
        raw_markdown: str,
        revision: int,
    ) -> None:
        current_text = self._current_text(raw_markdown, task)
        if current_text == task.source_text and self._hash_text(current_text) == task.source_hash:
            task.doc_revision = revision
            return

        relocation = self._find_relocation_target(db, task, raw_markdown)
        if relocation is None:
            return

        task.start_offset = int(relocation["start_offset"])
        task.end_offset = int(relocation["end_offset"])
        task.doc_revision = revision

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
        blocks = parse_blocks(raw_markdown)
        block = self._find_matching_block_from_blocks(blocks, start, end)
        block_data: dict[str, object] | None = None
        block_markdown: str | None = None
        if block is not None:
            block_data = self._serialize_context_block(block)
            block_markdown = raw_markdown[block.start_offset : block.end_offset]

        return {
            "document_title": document_title,
            "document_revision": document_revision,
            "current_selection_text": raw_markdown[start:end],
            "block": block_data,
            "block_markdown": block_markdown,
            "heading_path": self._build_heading_path(blocks, block.position if block is not None else None),
            "document_outline": [
                self._serialize_heading(block_item)
                for block_item in blocks
                if block_item.heading
            ],
            "context_before": raw_markdown[max(0, start - self.TASK_CONTEXT_WINDOW) : start],
            "context_after": raw_markdown[end : min(len(raw_markdown), end + self.TASK_CONTEXT_WINDOW)],
        }

    def _selection_bounds(self, raw_markdown: str, task: Task) -> tuple[int, int]:
        start = min(max(task.start_offset, 0), len(raw_markdown))
        end = min(max(task.end_offset, start), len(raw_markdown))
        return start, end

    def _find_matching_block(self, raw_markdown: str, task: Task):
        start, end = self._selection_bounds(raw_markdown, task)
        return self._find_matching_block_from_blocks(parse_blocks(raw_markdown), start, end)

    def _serialize_task_payload(
        self,
        db: Session,
        task: Task,
        *,
        description: dict[str, object] | None = None,
    ) -> dict[str, object]:
        if description is None:
            description = self.describe_task(db, task)
        return {
            "id": task.id,
            "doc_id": task.doc_id,
            "doc_revision": task.doc_revision,
            "start_offset": task.start_offset,
            "end_offset": task.end_offset,
            "source_text": task.source_text,
            "action": task.action,
            "instruction": task.instruction,
            "result": task.result,
            "status": task.status,
            "agent_name": task.agent_name,
            "error_message": task.error_message,
            "is_stale": bool(description.get("is_stale", False)),
            "stale_reason": description.get("stale_reason"),
            "recommended_action": description.get("recommended_action"),
            "context": self.build_task_context(db, task),
            "created_at": task.created_at,
            "started_at": task.started_at,
            "completed_at": task.completed_at,
            "resolved_at": task.resolved_at,
        }

    def _find_matching_block_from_blocks(self, blocks, start: int, end: int):
        for block in blocks:
            if start >= block.start_offset and end <= block.end_offset:
                return block
        return None

    def _detect_relocation_strategy(
        self, db: Session, task: Task, raw_markdown: str
    ) -> str | None:
        if task.status not in self.RELOCATABLE_STATUSES:
            return None

        current_text = self._current_text(raw_markdown, task)
        if current_text == task.source_text and self._hash_text(current_text) == task.source_hash:
            document = self.document_service.get_document(db, task.doc_id)
            if task.doc_revision != document.revision:
                return "current_selection_match"
            return None

        relocation = self._find_relocation_target(db, task, raw_markdown)
        return None if relocation is None else str(relocation["strategy"])

    def _can_requeue_from_current(
        self,
        task: Task,
        *,
        raw_markdown: str,
        start_offset: int,
        end_offset: int,
        is_stale: bool,
    ) -> tuple[bool, str | None]:
        if task.status not in self.RECOVERABLE_STATUSES:
            return False, "current task state does not support recovery"
        if not is_stale:
            return False, "task is not stale"
        if start_offset >= len(raw_markdown) or end_offset <= start_offset:
            return False, "current selection is empty"
        if not raw_markdown[start_offset:end_offset]:
            return False, "current selection is empty"
        if not self._is_within_single_block(raw_markdown, start_offset, end_offset):
            return False, "current selection crosses multiple blocks"
        return True, None

    def _recommended_recovery_mode(
        self,
        *,
        is_stale: bool,
        relocation_strategy: str | None,
        can_requeue: bool,
    ) -> str | None:
        if not is_stale:
            return None
        if relocation_strategy is not None:
            return "relocate"
        if can_requeue:
            return "requeue_from_current"
        return None

    def _close_task_for_requeue(self, task: Task, *, now) -> str | None:
        if task.status in {"pending", "processing"}:
            task.status = "cancelled"
            task.resolved_at = now
            return task.status
        if task.status == "done":
            task.status = "rejected"
            task.resolved_at = now
            return task.status
        if task.status == "failed" and task.resolved_at is None:
            task.resolved_at = now
        return task.status

    def _serialize_context_block(self, block) -> dict[str, object]:
        return {
            "heading": block.heading,
            "level": block.level,
            "position": block.position,
            "start_offset": block.start_offset,
            "end_offset": block.end_offset,
        }

    def _serialize_heading(self, block) -> dict[str, object]:
        return {
            "heading": block.heading,
            "level": block.level,
            "position": block.position,
        }

    def _build_heading_path(self, blocks, current_position: int | None) -> list[dict[str, object]]:
        if current_position is None:
            return []

        heading_path: list[dict[str, object]] = []
        for block in blocks:
            if block.position > current_position:
                break
            if not block.heading:
                continue
            while heading_path and int(heading_path[-1]["level"]) >= block.level:
                heading_path.pop()
            heading_path.append(self._serialize_heading(block))
        return heading_path

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
