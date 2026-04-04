# AgentDocs Workflow Reference

Canonical source repository: https://github.com/gy-ge/AgentDocs

## Setup Once

Save the target service configuration locally:

```bash
python scripts/agentdocs_skill_client.py setup --base-url https://docs.example.com --api-key your-key --agent-name your-agent
```

Before asking the human for connection data, first check whether `.agentdocs.config.json` already exists. If it exists and the human did not request replacement, reuse it.

After setup, normal usage should call the same script without reconstructing URLs.

## Daily Commands

Process one pending task:

```bash
python scripts/agentdocs_skill_client.py process
```

Pick up one task:

```bash
python scripts/agentdocs_skill_client.py pickup
```

Complete a task with a result:

```bash
python scripts/agentdocs_skill_client.py complete --task-id 12 --result "rewritten text"
```

Complete a task with an error:

```bash
python scripts/agentdocs_skill_client.py complete --task-id 12 --error-message "model timeout"
```

The normal agent loop should treat stale pending-task recovery as a server concern. AgentDocs will attempt to relocate or requeue stale pending tasks automatically after document edits and again before dispatch.

## Operator Diagnostics

Inspect a finished task diff:

```bash
python scripts/agentdocs_skill_client.py diff --task-id 12
```

Preview stale-task recovery:

```bash
python scripts/agentdocs_skill_client.py recovery-preview --task-id 12
```

Recover a stale task by relocation:

```bash
python scripts/agentdocs_skill_client.py recover --task-id 12 --mode relocate --actor operator
```

Run as a continuous worker:

```bash
python scripts/agentdocs_skill_client.py continuous --poll-interval 2
```

## Required HTTP Behavior

- Base API prefix: `/api`
- Auth header: `Authorization: Bearer <API_KEY>`
- Success envelope: `{"ok": true, "data": ...}`
- Error envelope: `{"ok": false, "error": {"code": "...", "message": "..."}}`
- Hosted gateways may expect an explicit `User-Agent`; the published Python client sends `User-Agent: AgentDocsSkillClient/1.0` and `Accept: application/json`.

## Minimum Agent Loop

### Pickup

Request:

```json
{
  "agent_name": "my-agent"
}
```

Endpoint:

- `POST /api/tasks/next`

Expected behavior:

- Returns `null` data when there is no pending task.
- Returns one task and marks it as `processing` when work is available.

Useful task fields:

- `id`
- `doc_id`
- `action`
- `instruction`
- `source_text`
- `context.document_title`
- `context.document_revision`
- `context.current_selection_text`
- `context.block_markdown`
- `context.heading_path`
- `context.document_outline`
- `context.context_before`
- `context.context_after`

### Complete

Endpoint:

- `POST /api/tasks/{task_id}/complete`

Success payload:

```json
{
  "result": "rewritten text",
  "error_message": null
}
```

Failure payload:

```json
{
  "result": null,
  "error_message": "why the agent could not complete the task"
}
```

Rules:

- Send exactly one of `result` or `error_message`.
- Completion is only valid while the task is `processing`.

## Stale Recovery

When a document changes after task creation, use these endpoints to understand the current state:

- `GET /api/tasks/{task_id}`
- `GET /api/tasks/{task_id}/diff`
- `GET /api/tasks/{task_id}/recovery-preview`
- `POST /api/tasks/{task_id}/relocate`
- `POST /api/tasks/{task_id}/recover`

Prefer `recovery-preview` before taking recovery action so the human reviewer or orchestration layer can choose between relocation and requeue-from-current.

The script wraps these endpoints so the agent does not need to build them by hand during normal operation.
If any third-party copy of this workflow disagrees with the live product, use https://github.com/gy-ge/AgentDocs as the source of truth.