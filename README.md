# AgentDocs

AgentDocs is a minimal Markdown collaboration service for a single human author and a single external agent workflow. The backend is FastAPI plus SQLite, the frontend is a single static HTML workbench, and Markdown blocks are parsed on read instead of being persisted as a separate source of truth. In normal production use, agents are expected to integrate through the published AgentDocs skill, while the REST protocol remains the underlying transport.

[Architecture](docs/architecture.md) | [API Contract](docs/api_contract.md) | [中文说明](README_zh.md)

## Scope

Implemented now:

- Document CRUD with optimistic revision checks
- Block-scoped task creation from selected Markdown ranges
- Agent collaboration through the published AgentDocs skill, backed by REST pickup and completion APIs
- Authenticated SSE task and document update stream for browser-side realtime sync
- Human accept, reject, cancel, retry, and rollback operations
- Task diff preview, batch-accept preview, stale detection, stale cleanup, relocation, and requeue-from-current recovery
- Server-persisted task templates and document-level default task settings
- Word-style browser workbench with inline review popover, selection toolbar, comment rail, bottom drawers, review badge, and keyboard shortcuts
- Simulated agent script for local testing and protocol verification

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

This repository's automated CI test entry currently runs this local suite. For manual live-environment verification after deployment, use the Online Smoke Test section below instead of adding the target environment to always-on CI.

If this is your first run with browser tests, install the Playwright Chromium runtime first:

```bash
uv run playwright install chromium
```

## Docker Deployment

You can run the published image from the repository root or from a brand-new empty folder. A source checkout is not required as long as you have this compose file.

### Minimal Standalone Steps

On macOS or Linux:

```bash
mkdir agentdocs
cd agentdocs
cp /path/to/docker-compose.yml .
docker compose up -d
```

On Windows PowerShell:

```powershell
New-Item -ItemType Directory agentdocs | Out-Null
Set-Location agentdocs
Copy-Item C:/path/to/docker-compose.yml ./docker-compose.yml
docker compose up -d
```

That is enough for a first boot. If you do nothing else, Docker will pull the image, create a local `data` folder next to `docker-compose.yml` if needed, and publish the app on port 8000.

Save [docker-compose.yml](docker-compose.yml) into the target folder, then run:

```bash
docker compose up -d
```

The compose file pulls the published GHCR image by default. It does not mount a `.env` file into the container. Instead, Docker Compose reads variables from an optional `.env` file in the same folder as `docker-compose.yml` and injects them as container environment variables.

The compose file also sets `pull_policy: always`, so `docker compose up -d` will check for a newer image tag before starting the container.

If you want to override the defaults, create a `.env` file next to `docker-compose.yml` with content like:

```dotenv
IMAGE_TAG=latest
AGENTDOCS_PORT=8000
APP_NAME=AgentDocs
API_KEY=change-me
SQLITE_PATH=/app/data/doc.db
```

If you do not create `.env`, the compose file still works with the same defaults.

For a safe first-time deployment, the important defaults are:

- `AGENTDOCS_PORT=8000`
- `API_KEY=change-me`
- `SQLITE_PATH=/app/data/doc.db`

`APP_ENV` has been removed from the published compose path because the current application does not use it. If you still have `APP_ENV` in an older local `.env`, it is safe to delete.

The container entrypoint runs `alembic upgrade head` automatically before starting Uvicorn.

After opening http://127.0.0.1:8000 for the first time, enter the shared API key from your compose environment in the browser's Connection Settings dialog. With the default config, that value is `change-me`.

Useful commands:

```bash
docker compose logs -f
docker compose ps
docker compose down
```

The SQLite database is persisted in the `data` folder next to [docker-compose.yml](docker-compose.yml). Inside the container, that folder is mounted at `/app/data`. The compose default sets `SQLITE_PATH=/app/data/doc.db`, so the database file ends up as `./data/doc.db` on the host.

If you override `SQLITE_PATH`, keep it under `/app/data` unless you intentionally want the database to stop using the host-side `data` folder.

This also makes backup simple: stop the stack if you want a quiet backup, then copy the local `data` folder.

## Troubleshooting Startup

- If `uv sync` says your Python version does not satisfy the project requirement, run `uv python install 3.10` and then rerun `uv sync`.
- If you override `SQLITE_PATH`, make sure the parent directory is writable; the default local setup now creates missing directories automatically, but it cannot bypass filesystem permission errors.
- If port 8000 is already in use, set `AGENTDOCS_PORT` in the compose-side `.env`, for example `AGENTDOCS_PORT=8080`, then open that port in the browser.
- If Docker does not auto-create a writable `data` directory on your platform, create it yourself next to `docker-compose.yml` before running `docker compose up -d`.
- If the page loads but API requests return 401, enter the `API_KEY` from the compose-side `.env` or your shell environment in the browser connection settings. The default value is `change-me`.

## Authentication

All API routes under /api require this header:

```text
Authorization: Bearer <API_KEY>
```

The API does not use X-API-KEY.

## Recommended Agent Workflow

For real agent collaboration, prefer the published AgentDocs skill instead of hand-building API calls.

Recommended flow:

1. Open [skills/agentdocs/SKILL.md](skills/agentdocs/SKILL.md) or install the published skill package that contains it.
2. Run the bundled setup once so the agent saves the AgentDocs base URL, API key, and agent name.
3. Use the bundled commands such as `process`, `pickup`, `complete`, or `continuous` from [skills/agentdocs/scripts/agentdocs_skill_client.py](skills/agentdocs/scripts/agentdocs_skill_client.py) instead of reconstructing raw HTTP requests.
4. Keep accept, reject, rollback, and stale-task investigation as human or operator actions outside the normal agent loop.

The skill is the recommended collaboration surface because it preserves a stable operator workflow, reuses saved configuration, sends gateway-safe headers, and keeps agents from reimplementing stale-task recovery logic that already exists server-side.

## Simulated Agent

This script is for local testing and smoke verification. It is not the recommended production integration path.

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

## Online Smoke Test

This smoke script is for manual post-deploy verification when you want to inspect a specific live environment. It is not intended to run in GitHub Actions or as a mandatory CI/CD step.

For manual production-like checks, use the dedicated smoke script instead of editing URLs into source files.

Add the target environment to a local env file such as `.env.live`:

```dotenv
AGENTDOCS_SMOKE_BASE_URL=https://example.com
AGENTDOCS_SMOKE_API_KEY=change-me
```

Then run:

```bash
uv run python scripts/live_smoke_test.py --env-file .env.live
```

For a more readable operator summary:

```bash
uv run python scripts/live_smoke_test.py --env-file .env.live --output human
```

To run only part of the smoke test:

```bash
uv run python scripts/live_smoke_test.py --env-file .env.live --checks basic
uv run python scripts/live_smoke_test.py --env-file .env.live --checks tasks
uv run python scripts/live_smoke_test.py --env-file .env.live --checks rollback
```

The stages work like this:

- `basic`: auth, document list, create, fetch, and cleanup
- `tasks`: includes `basic`, then verifies manual pickup, complete, accept, reject, cancel, task list, and version list
- `rollback`: includes `tasks`, then verifies rollback and final content restoration

What the smoke script verifies:

- bearer authentication
- document create, fetch, list, and delete
- manual agent pickup and completion through the task APIs
- accept, reject, and cancel flows
- version listing and rollback
- UTC timestamp serialization on API fields

The script creates temporary documents and deletes them before exiting.

Recommended usage:

- keep one or more local env files such as `.env.live` or `.env.staging`
- run the script only when you explicitly want to verify that target environment
- do not wire this script into always-on CI unless you intentionally want external-environment checks
- keep `.env.example` as the shared template, and put real live targets only in local files such as `.env.live`

## UI E2E Tests

Run the browser E2E suite directly with:

```bash
uv run pytest tests/test_ui_e2e.py
```

This UI suite is part of the local automated test path. If you want to verify a deployed environment instead, use the Online Smoke Test section rather than pointing pytest at a live service.

What the E2E suite covers now:

- document creation and autosave feedback
- editor-side task markers and task review linkage
- conflict recovery through Reload Latest after a server-side revision change
- narrow viewport marker usability

The test starts its own temporary database, Uvicorn process, and simulated agent worker, so it does not depend on the manually running app.

## Agent Integration

The external agent protocol is intentionally small. The published AgentDocs skill is the preferred way to consume it; the details below describe the underlying transport for custom integrations, debugging, and tests.

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

If you want the published AgentDocs skill package for this protocol, see [skills/agentdocs/SKILL.md](skills/agentdocs/SKILL.md). The canonical source is https://github.com/gy-ge/AgentDocs, and it includes a runnable skill client at [skills/agentdocs/scripts/agentdocs_skill_client.py](skills/agentdocs/scripts/agentdocs_skill_client.py). In day-to-day use, prefer that client over hand-crafted API calls.