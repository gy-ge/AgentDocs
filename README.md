# AgentDocs

AgentDocs is a minimal Markdown collaboration service for a single human author and a single external agent workflow. The backend is FastAPI plus SQLite, the frontend is a single static HTML workbench, and Markdown blocks are parsed on read instead of being persisted as a separate source of truth.

[Architecture](docs/architecture.md) | [API Contract](docs/api_contract.md) | [中文说明](README_zh.md)

## Scope

Implemented now:

- Document CRUD with optimistic revision checks
- Block-scoped task creation from selected Markdown ranges
- Agent pickup and completion flows through the REST API
- Human accept, reject, cancel, retry, and rollback operations
- Task diff preview, stale detection, stale cleanup, relocation, and requeue-from-current recovery
- Server-persisted task templates and document-level default task settings
- Minimal browser UI and a simulated agent script for local testing

Explicitly out of scope for the current version:

- Built-in LLM execution
- Multi-user accounts or complex authorization
- WebSocket or SSE push updates
- Auto-apply of agent output without human review
- Persistent block tables
- Lease, heartbeat, or claim-token task protocols

## Requirements

- Python 3.14+
- uv

## Setup

Install dependencies:

```bash
uv sync
```

Create the environment file:

```bash
cp .env.example .env
```

Default values from .env.example:

- APP_NAME=AgentDocs
- APP_ENV=development
- API_KEY=change-me
- SQLITE_PATH=data/doc.db

## Run

Apply migrations before starting the app:

```bash
uv run alembic upgrade head
```

Start the backend:

```bash
uv run uvicorn app.main:app --reload
```

Then open http://127.0.0.1:8000.

## Authentication

All API routes under /api require this header:

```text
Authorization: Bearer <API_KEY>
```

The API does not use X-API-KEY.

## Simulated Agent

Run one task once:

```bash
uv run python scripts/simulate_agent.py --api-key change-me
```

Useful variants:

```bash
uv run python scripts/simulate_agent.py --api-key change-me --continuous
uv run python scripts/simulate_agent.py --api-key change-me --mode uppercase
uv run python scripts/simulate_agent.py --api-key change-me --mode fail
```

## Agent Integration

The external agent protocol is intentionally small.

1. Call POST /api/tasks/next with {"agent_name": "your-agent"}. The server returns one pending task and moves it to processing.
2. Use the top-level task fields source_text, action, and instruction to build your prompt.
3. Use the context object for bounded document awareness. Current fields are:
	- document_title
	- document_revision
	- current_selection_text
	- block
	- block_markdown
	- heading_path
	- document_outline
	- context_before
	- context_after
4. Submit exactly one of result or error_message to POST /api/tasks/{task_id}/complete.
5. If the task becomes stale because the document changed, the browser or operator can inspect GET /api/tasks/{task_id}/diff, GET /api/tasks/{task_id}/recovery-preview, POST /api/tasks/{task_id}/relocate, or POST /api/tasks/{task_id}/recover.

Action and instruction are free-form strings. Typical action names in this repository are rewrite, translate, summarize, extract, and fix.

## Current Status

Current implementation includes:

- Document list, create, update, delete, version history, and rollback
- Task create, next, complete, accept, reject, cancel, retry, diff, relocate, recovery preview, and recover
- Batch accept-ready and document-wide stale cleanup
- Persistent task templates and per-document default task settings
- Integration tests for API flows, migrations, and simulated agent behavior

## Development Order

Recommended next priorities:

1. Add more regression tests around stale recovery and batch acceptance edge cases.
2. Continue simplifying the high-frequency task review flow in the browser UI.
3. Keep README and docs in sync whenever API fields or task states change.