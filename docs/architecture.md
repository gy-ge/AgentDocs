# AgentDocs Architecture

AgentDocs is a small asynchronous Markdown collaboration system built around one source document, one human reviewer, and one external agent workflow. The implementation favors explicit state transitions, revision checks, and recovery tooling over automation that writes directly into documents without review.

## System Boundaries

What the system does:

- Stores Markdown documents, task state, document versions, and task templates in SQLite
- Parses Markdown into runtime block views when documents are read
- Restricts task creation to a single block range inside the current document text
- Lets an external agent poll for work, submit a result, or report failure
- Requires a human-driven accept step before agent output changes the document
- Detects stale tasks and supports cleanup, relocation, preview, and requeue-from-current recovery

What the system does not do:

- It does not run an LLM internally
- It does not implement multi-user identity or role systems
- It does not keep a persistent blocks table
- It does not use WebSocket, SSE, auto-apply, lease, heartbeat, or claim-token flows

## Source of Truth

documents.raw_markdown is the only document source of truth.

- blocks are derived by parsing raw_markdown on demand
- the frontend never submits blocks back to the server
- accept only replaces the exact source range tracked by a task

## Data Model

The current schema contains four tables:

- documents: title, raw_markdown, revision, default task settings, timestamps
- tasks: source range, source text and hash, action, instruction, agent result, status, timestamps
- doc_versions: snapshots created on document creation, content edits, accept operations that change content, and rollback
- task_templates: reusable action and instruction presets stored on the server

## Task Lifecycle

The effective task statuses are:

- pending
- processing
- done
- accepted
- rejected
- failed
- cancelled

Main transitions:

- pending -> processing through POST /api/tasks/next
- processing -> done or failed through POST /api/tasks/{id}/complete
- done -> accepted through POST /api/tasks/{id}/accept
- done -> rejected through POST /api/tasks/{id}/reject
- pending or processing -> cancelled through POST /api/tasks/{id}/cancel
- failed, cancelled, or rejected -> pending through POST /api/tasks/{id}/retry

## Stale Detection and Recovery

Stale checks apply to pending, processing, and done tasks.

- If the current document slice still matches source_text and source_hash, the task is not stale.
- If it does not match, the backend reports one of selection_removed, selection_shifted, or source_changed.
- Relocation first tries the original block position, then a unique same-heading block, then a unique document-wide text match.
- If relocation is not enough, the recover endpoint can close the old task and create a new pending task from the current selection range.

## Main Components

- app/api: FastAPI routers, authentication dependency, and response serialization
- app/services/document_service.py: document CRUD, version creation, rollback, and default task settings
- app/services/task_service.py: task lifecycle, stale detection, diff generation, batch accept, cleanup, relocation, and recovery
- app/services/markdown.py: lightweight heading-based block parser
- app/static/index.html: minimal browser workbench
- scripts/simulate_agent.py: local worker for API integration testing