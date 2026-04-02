# API Contract

This document describes the API shape implemented by the current FastAPI application.

## Common Rules

Base URL:

- /api

Authentication:

- Every /api route requires Authorization: Bearer <API_KEY>

Success envelope:

```json
{
  "ok": true,
  "data": {}
}
```

Error envelope:

```json
{
  "ok": false,
  "error": {
    "code": "conflict",
    "message": "document revision mismatch"
  }
}
```

Common error codes:

- unauthorized
- not_found
- validation_error
- conflict
- invalid_state

## Documents

### GET /api/docs

Returns document list items:

- id
- title
- revision
- updated_at

### POST /api/docs

Request:

```json
{
  "title": "Project Notes",
  "raw_markdown": "# Project Notes\n",
  "actor": "browser"
}
```

Response data contains:

- id
- title
- revision

Notes:

- title is trimmed and must not be blank
- a version snapshot is created immediately when the document is created

### GET /api/docs/{doc_id}

Returns a full document payload:

- id
- title
- raw_markdown
- revision
- default_task_action
- default_task_instruction
- blocks
- updated_at

Each block contains:

- heading
- level
- position
- start_offset
- end_offset
- content

### PUT /api/docs/{doc_id}

Request:

```json
{
  "title": "Project Notes",
  "raw_markdown": "# Project Notes\n\nUpdated body\n",
  "expected_revision": 3,
  "actor": "browser",
  "note": "manual edit"
}
```

Behavior:

- expected_revision must match the current document revision
- if only the title changes, revision does not increase
- if title and body are unchanged, the request is a no-op
- if raw_markdown changes, revision increases and a new version snapshot is created

### DELETE /api/docs/{doc_id}

Deletes the document and cascades to its tasks and versions.

### POST /api/docs/{doc_id}/task-defaults

Request:

```json
{
  "actor": "browser",
  "default_task_action": "rewrite",
  "default_task_instruction": "Rewrite in a more formal tone"
}
```

Notes:

- this updates document metadata only
- it does not increase revision
- if action is null and instruction is present, the backend falls back to rewrite

### POST /api/docs/{doc_id}/tasks

Request:

```json
{
  "action": "rewrite",
  "instruction": "Keep it concise",
  "source_text": "Original text",
  "start_offset": 10,
  "end_offset": 23,
  "doc_revision": 3
}
```

Rules:

- doc_revision must match the current document revision
- source_text must match the current document slice exactly
- the range must stay within a single parsed block

### POST /api/docs/{doc_id}/tasks/cleanup-stale

Closes stale tasks for the current document.

- stale pending and processing tasks become cancelled
- stale done tasks become rejected

Response data contains:

- doc_id
- cancelled
- rejected
- unchanged

### POST /api/docs/{doc_id}/tasks/accept-ready

Apply one batch of safe done tasks for one document.

Use the companion preview endpoint first when the UI needs a reviewer-facing summary.

Batch-accepts safe done tasks for one document.

Request:

```json
{
  "actor": "browser",
  "note": "bulk accept from ui",
  "action": "rewrite",
  "start_offset": 0,
  "end_offset": 200,
  "limit": 20
}
```

Optional filters:

- action
- start_offset and end_offset together
- limit from 1 to 50

Response data contains:

- doc_id
- document_revision
- accepted
- skipped
- accepted_task_ids
- skipped_tasks
- rollback_version_id
- rollback_revision

### POST /api/docs/{doc_id}/tasks/accept-ready-preview

Preview the current batch-accept selection without changing document or task state.

Request body is the same as POST /api/docs/{doc_id}/tasks/accept-ready.

Response data contains:

- doc_id
- document_revision
- action
- start_offset
- end_offset
- limit
- matched
- will_accept
- will_skip
- accepted_task_ids
- accepted_tasks
- skipped_tasks

## Tasks

### GET /api/tasks

Optional query parameters:

- status
- doc_id

Returns task list items with stale metadata.

### GET /api/tasks/events

Returns a text/event-stream response for browser-side realtime sync.

Rules:

- requires the same Authorization: Bearer <API_KEY> header as other /api routes
- emits a ready event immediately after subscription
- emits task.changed, tasks.changed, and document.changed events after successful writes
- the browser workbench treats this stream as the primary sync path and falls back to polling if the stream disconnects

### GET /api/tasks/{task_id}

Returns the full task payload plus context.

Task fields include:

- id
- doc_id
- doc_revision
- start_offset
- end_offset
- source_text
- action
- instruction
- result
- status
- agent_name
- error_message
- is_stale
- stale_reason
- recommended_action
- context

context fields include:

- document_title
- document_revision
- current_selection_text
- block
- block_markdown
- heading_path
- document_outline
- context_before
- context_after

### GET /api/tasks/{task_id}/diff

Available only when the task already has a result.

Response data contains:

- task_id
- doc_id
- current_text
- source_text
- result_text
- can_accept
- conflict_reason
- recommended_action
- diff

### GET /api/tasks/{task_id}/recovery-preview

Returns a preview of stale-task recovery options.

Response data contains:

- task_id
- doc_id
- task_status
- is_stale
- stale_reason
- current_document_revision
- current_start_offset
- current_end_offset
- current_selection_text
- can_relocate
- relocation_strategy
- can_requeue_from_current
- requeue_reason
- recommended_mode
- context

### POST /api/tasks/next

Request:

```json
{
  "agent_name": "simulated-agent"
}
```

Behavior:

- picks the oldest pending task
- changes its status to processing
- stores agent_name and started_at
- returns null data when the queue is empty

### POST /api/tasks/{task_id}/complete

Request with success result:

```json
{
  "result": "Updated text",
  "error_message": null
}
```

Request with failure:

```json
{
  "result": null,
  "error_message": "model timeout"
}
```

Rules:

- the task must be processing
- exactly one of result or error_message must be provided
- result moves the task to done
- error_message moves the task to failed

### POST /api/tasks/{task_id}/accept

Request:

```json
{
  "expected_revision": 3,
  "actor": "browser",
  "note": "accept task result"
}
```

Rules:

- the task must be done and have a result
- expected_revision must match the current document revision
- the current document slice must still match source_text and source_hash
- if result equals source_text, the task becomes accepted without creating a new revision

### POST /api/tasks/{task_id}/reject

Rules:

- the task must be done
- the task becomes rejected
- the document is not modified

### POST /api/tasks/{task_id}/cancel

Rules:

- only pending and processing tasks can be cancelled
- the document is not modified

### POST /api/tasks/{task_id}/retry

Rules:

- only failed, cancelled, and rejected tasks can be retried
- the current document range must still match source_text
- the range must still stay within a single block
- the task returns to pending and clears previous execution fields

### POST /api/tasks/{task_id}/relocate

Rules:

- processing tasks cannot be relocated
- accepted tasks do not need relocation
- relocation may return one of these strategies:
  - current_selection_match
  - same_block_position_match
  - same_heading_unique_match
  - document_unique_match

### POST /api/tasks/{task_id}/recover

Supported modes:

- relocate
- requeue_from_current

Request:

```json
{
  "mode": "requeue_from_current",
  "actor": "browser"
}
```

Behavior:

- relocate delegates to the same relocation workflow and returns the source task plus strategy
- requeue_from_current closes the old task and creates a new pending task from the current document range

## Templates

### GET /api/task-templates

Returns all persisted server-side templates.

### POST /api/task-templates

```json
{
  "name": "Formal rewrite",
  "action": "rewrite",
  "instruction": "Use a formal and restrained tone"
}
```

### PUT /api/task-templates/{template_id}

Same request schema as create.

### DELETE /api/task-templates/{template_id}

Deletes one template.

## Versions

### GET /api/docs/{doc_id}/versions

Returns version list items:

- id
- revision
- actor
- note
- created_at

### POST /api/docs/{doc_id}/versions/{version_id}/rollback

Request:

```json
{
  "expected_revision": 5,
  "actor": "browser",
  "note": "rollback to version 2"
}
```

Rules:

- expected_revision must match the current document revision
- if the target snapshot already matches the current document body, rollback is a no-op
- otherwise the document body is restored, revision increases, and a new version snapshot is created
