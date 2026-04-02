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
- Minimal browser UI and a simulated agent script for local testing

Explicitly out of scope for the current version:

- Built-in LLM execution
- Multi-user accounts or complex authorization
- WebSocket push updates
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

## Docker Deployment

Create the environment file first:

```bash
cp .env.example .env
```

Build and start the container:

```bash
docker compose up --build -d
```

The container entrypoint runs `alembic upgrade head` automatically before starting Uvicorn.

After opening http://127.0.0.1:8000 for the first time, enter the shared API key from `.env` in the browser's Connection Settings dialog. With the default example config, that value is `change-me`.

Useful commands:

```bash
docker compose logs -f
docker compose ps
docker compose down
```

The SQLite database is persisted in the named Docker volume `agentdocs-data`, mounted at `/app/data` inside the container.

If you want to rebuild after dependency or code changes:

```bash
docker compose up --build -d
```

## GitHub Container Registry

The repository now includes [docker-publish.yml](.github/workflows/docker-publish.yml), which publishes images to GitHub Container Registry instead of Docker Hub.

Recommended setup:

- Keep the package public in GitHub Packages if you want anonymous `docker pull` access.
- Use pushes to `main` only for validation, and Git tags like `v0.1.0` for actual image releases.
- Rely on the built-in `GITHUB_TOKEN`; no extra registry secret is required for the workflow.

Workflow behavior:

- Pull requests run tests and a Docker build validation, but do not publish images.
- Pushes to `main` run tests and a Docker build validation, but do not publish images.
- Version tags like `v0.1.0` publish semver tags to GHCR.
- Manual runs can publish a custom tag and optionally refresh `latest`.
- After each actual publish, the workflow pulls the published digest and starts the container once as a smoke test.

After the first successful publish, the image will be available under:

```text
ghcr.io/<owner>/<repository>:latest
```

Example usage:

```bash
docker pull ghcr.io/<owner>/<repository>:latest
docker run --rm -p 8000:8000 --env-file .env ghcr.io/<owner>/<repository>:latest
```

Recommended release flow:

```bash
git tag v0.1.0
git push origin v0.1.0
```

How `latest` is updated:

- Pushing a normal version tag such as `v0.1.0` updates the semver tags and `latest` together.
- Manual publishing does not update `latest` unless you explicitly set `publish_latest=true` in the workflow input.
- If you want to move `latest` to an already-tested build without changing the semver tags, run the workflow manually with a maintenance tag and enable `publish_latest`.

Manual publishing is best reserved for exceptional cases such as republishing the same code with an explicit maintenance tag.

If the package stays private, users can still pull it after logging in with a GitHub personal access token that has `read:packages`.

Run the published image locally

You can override the image tag with the `IMAGE_TAG` environment variable (or set it in `.env`). Example commands:

```bash
# pull specific published tag (default: latest)
IMAGE_TAG=v0.1.0 docker compose pull

# start the service with the pulled image
IMAGE_TAG=v0.1.0 docker compose up -d

# follow logs
docker compose logs -f

# stop and remove
docker compose down
```

Notes:

- If the repository package is private, `docker compose pull` will prompt for credentials; authenticate with `docker login ghcr.io` using a Personal Access Token that has `read:packages`.
- By default the compose file uses `ghcr.io/gy-ge/agentdocs:${IMAGE_TAG:-latest}` so you can omit `IMAGE_TAG` to run `latest`.

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

The repository now includes Playwright-based browser E2E coverage for the static workbench.

Install the Chromium runtime once:

```bash
uv run python -m playwright install chromium
```

Run the browser E2E suite:

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