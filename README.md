# AgentDocs

AgentDocs is a minimal Markdown collaboration service for a single human author and a single external agent workflow. The backend is FastAPI plus SQLite, the frontend is a single static HTML workbench, and Markdown blocks are parsed on read instead of being persisted as a separate source of truth.

[Architecture](docs/architecture.md) | [API Contract](docs/api_contract.md) | [中文说明](README_zh.md)

## Scope

Implemented now:

- Document CRUD with optimistic revision checks
- Block-scoped task creation from selected Markdown ranges
- Agent pickup and completion flows through the REST API
- Authenticated SSE task and document update stream for browser-side realtime sync
- Human accept, reject, cancel, retry, and rollback operations
- Task diff preview, batch-accept preview, stale detection, stale cleanup, relocation, and requeue-from-current recovery
- Server-persisted task templates and document-level default task settings
- Word-style browser workbench with inline review popover, selection toolbar, comment rail, bottom drawers, review badge, and keyboard shortcuts
- Simulated agent script for local testing

Explicitly out of scope for the current version:

- Built-in LLM execution
- Multi-user accounts or complex authorization
- WebSocket push updates
- Auto-apply of agent output without human review
- Persistent block tables
- Lease, heartbeat, or claim-token task protocols

## Requirements

- Python 3.10+
- uv

## Quick Start

If Python 3.10 is not installed yet, install and pin it first:

```bash
uv python install 3.10
uv python pin 3.10
```

Install dependencies:

```bash
uv sync
```

Create the environment file:

```bash
cp .env.example .env
```

On Windows PowerShell, use:

```powershell
Copy-Item .env.example .env
```

Default values from .env.example:

- APP_NAME=AgentDocs
- APP_ENV=development
- API_KEY=change-me
- SQLITE_PATH=data/doc.db

The default `SQLITE_PATH` is `data/doc.db`. The app now creates missing parent directories automatically on first migration or startup, so you do not need to create `data/` by hand.

Apply migrations before starting the app:

```bash
uv run alembic upgrade head
```

Start the backend:

```bash
uv run uvicorn app.main:app --reload
```

Then open http://127.0.0.1:8000 and enter the `API_KEY` from `.env` in the browser's Connection Settings dialog. With the default example config, that value is `change-me`.

Run the full test suite:

```bash
uv run pytest
```

If this is your first run with browser tests, install the Playwright Chromium runtime first:

```bash
uv run playwright install chromium
```

## Docker Deployment

From the repository root, run:

```bash
docker compose up --build -d
```

`docker-compose.yml` now builds from the local repository `Dockerfile` by default, instead of expecting a pre-published GHCR image.

The container entrypoint runs `alembic upgrade head` automatically before starting Uvicorn. You still need to create `.env` first, using the same steps from Quick Start.

After opening http://127.0.0.1:8000 for the first time, enter the shared API key from `.env` in the browser's Connection Settings dialog. With the default example config, that value is `change-me`.

Useful commands:

```bash
docker compose logs -f
docker compose ps
docker compose down
```

The SQLite database is persisted in the named Docker volume `agentdocs-data`, mounted at `/app/data` inside the container.

## Troubleshooting Startup

- If `uv sync` says your Python version does not satisfy the project requirement, run `uv python install 3.10` and then rerun `uv sync`.
- If you override `SQLITE_PATH`, make sure the parent directory is writable; the default local setup now creates missing directories automatically, but it cannot bypass filesystem permission errors.
- If the page loads but API requests return 401, enter the `API_KEY` from `.env` in the browser connection settings. The default example value is `change-me`.

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

## UI E2E Tests

Run the browser E2E suite directly with:

```bash
uv run pytest tests/test_ui_e2e.py
```

What the E2E suite covers now:

- document creation and autosave feedback
- editor-side task markers and task review linkage
- conflict recovery through Reload Latest after a server-side revision change
- narrow viewport marker usability

The test starts its own temporary database, Uvicorn process, and simulated agent worker, so it does not depend on the manually running app.

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