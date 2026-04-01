from app.schemas.docs import BlockRead, DocumentListItem, DocumentRead
from app.schemas.tasks import (
    CleanupStaleTasksRead,
    TaskBatchAcceptRead,
    TaskRead,
    TaskRelocateRead,
)
from app.schemas.versions import VersionRead


def serialize_document_list_item(document) -> DocumentListItem:
    return DocumentListItem(
        id=document.id,
        title=document.title,
        revision=document.revision,
        updated_at=document.updated_at,
    )


def serialize_document(document, blocks) -> DocumentRead:
    return DocumentRead(
        id=document.id,
        title=document.title,
        raw_markdown=document.raw_markdown,
        revision=document.revision,
        blocks=[
            BlockRead(
                heading=block.heading,
                level=block.level,
                position=block.position,
                start_offset=block.start_offset,
                end_offset=block.end_offset,
                content=block.content,
            )
            for block in blocks
        ],
        updated_at=document.updated_at,
    )


def serialize_task(
    task,
    *,
    is_stale: bool = False,
    stale_reason: str | None = None,
    recommended_action: str | None = None,
    context: dict[str, object] | None = None,
) -> TaskRead:
    return TaskRead(
        id=task.id,
        doc_id=task.doc_id,
        doc_revision=task.doc_revision,
        start_offset=task.start_offset,
        end_offset=task.end_offset,
        source_text=task.source_text,
        action=task.action,
        instruction=task.instruction,
        result=task.result,
        status=task.status,
        agent_name=task.agent_name,
        error_message=task.error_message,
        is_stale=is_stale,
        stale_reason=stale_reason,
        recommended_action=recommended_action,
        context=context,
        created_at=task.created_at,
        started_at=task.started_at,
        completed_at=task.completed_at,
        resolved_at=task.resolved_at,
    )


def serialize_stale_cleanup(
    doc_id: int, *, cancelled: int, rejected: int, unchanged: int
) -> CleanupStaleTasksRead:
    return CleanupStaleTasksRead(
        doc_id=doc_id,
        cancelled=cancelled,
        rejected=rejected,
        unchanged=unchanged,
    )


def serialize_batch_accept(result: dict[str, object]) -> TaskBatchAcceptRead:
    return TaskBatchAcceptRead(**result)


def serialize_task_relocation(
    task,
    *,
    relocation_strategy: str,
    is_stale: bool = False,
    stale_reason: str | None = None,
    recommended_action: str | None = None,
    context: dict[str, object] | None = None,
) -> TaskRelocateRead:
    return TaskRelocateRead(
        task=serialize_task(
            task,
            is_stale=is_stale,
            stale_reason=stale_reason,
            recommended_action=recommended_action,
            context=context,
        ),
        relocation_strategy=relocation_strategy,
    )


def serialize_version(version) -> VersionRead:
    return VersionRead(
        id=version.id,
        revision=version.revision,
        actor=version.actor,
        note=version.note,
        created_at=version.created_at,
    )