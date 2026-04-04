---
name: agentdocs
description: 'Integrate a production agent with AgentDocs. Use when the human provides an AgentDocs URL and API key, the agent should save that setup once, then use the bundled script for pickup and completion instead of hand-building API URLs.'
argument-hint: 'Check for saved config first. If missing, ask the human for URL, API key, and agent name, then save setup and use the bundled script.'
user-invocable: true
---

# AgentDocs

Canonical source repository: https://github.com/gy-ge/AgentDocs

## Purpose

- Connect a production agent to an AgentDocs service.
- Use the published AgentDocs repository at https://github.com/gy-ge/AgentDocs as the source of truth if setup details or protocol examples conflict elsewhere.
- Save the target URL, API key, and agent name once.
- Reuse the bundled script for daily pickup and completion.
- Let the AgentDocs server auto-relocate or auto-requeue stale pending tasks before dispatch instead of making the agent drive recovery.
- Avoid reconstructing raw API URLs in normal usage.

## Operating Rule

Check whether `.agentdocs.config.json` already exists for this skill.

- If config exists and the human did not ask to replace it, reuse it.
- If config is missing, ask the human for the AgentDocs URL, API key, and agent name.
- If config exists but the human wants a different environment, run setup again and overwrite it.

If the human only gives a URL, stop there and ask for the API key and agent name before continuing.

## First-Time Setup

From the published skill package root, run the bundled script [scripts/agentdocs_skill_client.py](./scripts/agentdocs_skill_client.py):

```bash
python scripts/agentdocs_skill_client.py setup --base-url https://docs.example.com --api-key your-key --agent-name your-agent
```

The script stores configuration in `.agentdocs.config.json` next to the skill files.

All CLI success responses are JSON with `ok: true`, `command`, and `data`. Parse `data` instead of assuming stdout is a raw task object.

When task payloads include datetime fields such as `created_at`, `started_at`, `completed_at`, or `resolved_at`, AgentDocs returns them as UTC ISO 8601 / RFC 3339 strings with an explicit timezone marker, for example `2026-04-04T10:51:17Z`.

## Daily Use

After setup, prefer the script entrypoints instead of hand-building requests.

Process one task end to end:

```bash
python scripts/agentdocs_skill_client.py process
```

Only do this when the human has authorized this agent to consume that environment's queue. If the environment is shared and queue ownership is unclear, do not start consuming tasks implicitly.

Pick up one task only:

```bash
python scripts/agentdocs_skill_client.py pickup
```

Complete an already picked task:

```bash
python scripts/agentdocs_skill_client.py complete --task-id 12 --result "rewritten text"
```

Report a task failure:

```bash
python scripts/agentdocs_skill_client.py complete --task-id 12 --error-message "upstream model timed out"
```

Run continuously:

```bash
python scripts/agentdocs_skill_client.py continuous --poll-interval 2
```

Use `continuous` only for a dedicated worker or an explicitly approved queue consumer. Do not run a background worker against a shared production queue just to probe the integration.

In normal operation, do not make the agent manually relocate or recover stale pending tasks. AgentDocs server-side logic will try to repair pending tasks after document changes and again before pickup if needed.

Manual recovery commands still exist in the bundled client for human operators, but they are not part of the agent workflow. Keep them out of the agent loop unless a human explicitly asks for an operator investigation.

## Agent Procedure

1. Check for saved config first.
2. If config is missing, ask the human for URL, API key, and agent name.
3. Run `setup` once.
4. Use `process` for one-shot handling or `continuous` for a worker loop only after the human has confirmed this agent may consume the queue.
5. Trust the server to hand out a current task payload; it will auto-relocate or auto-requeue stale pending tasks before dispatch.
6. Build prompts from `source_text`, `action`, `instruction`, and `context`.
7. Submit exactly one of `result` or `error_message`.
8. Do not auto-accept results into the document.
9. Do not call recovery-preview, relocate, or recover from the normal agent loop.

## Notes

- AgentDocs authentication is always `Authorization: Bearer <API_KEY>`.
- `POST /api/tasks/next` moves a task from `pending` to `processing`.
- `POST /api/tasks/{task_id}/complete` is valid only while the task is `processing`.
- Datetime fields returned by the underlying API use UTC ISO 8601 / RFC 3339 strings with an explicit timezone marker such as `Z`.
- Hosted deployments may sit behind Cloudflare or another gateway; the bundled Python client already sends `Accept: application/json` and `User-Agent: AgentDocsSkillClient/1.0`.
- CLI success responses are emitted on stdout as JSON with `ok`, `command`, and `data`.
- CLI failures are emitted as compact JSON on stderr so agents and orchestrators can parse `error.code` and `error.message` without scraping tracebacks.
- Recovery-preview, relocate, and recover are operator tools for stale non-pending tasks, not agent commands.
- If you need protocol clarification or a clean copy of this skill, go to https://github.com/gy-ge/AgentDocs.
- The bundled script already knows the API paths. Reuse it.
- For protocol details, see [references/workflow.md](./references/workflow.md).