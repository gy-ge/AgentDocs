---
name: agentdocs-integration
description: 'Integrate a production agent with AgentDocs. Use when the human provides an AgentDocs URL and API key, the agent should save that setup once, then use the bundled script for pickup, completion, and recovery instead of hand-building API URLs.'
argument-hint: 'Check for saved config first. If missing, ask the human for URL, API key, and agent name, then save setup and use the bundled script.'
user-invocable: true
---

# AgentDocs Integration

## Purpose

- Connect a production agent to an AgentDocs service.
- Save the target URL, API key, and agent name once.
- Reuse the bundled script for daily pickup and completion.
- Avoid reconstructing raw API URLs in normal usage.

## Operating Rule

Check whether `.agentdocs.config.json` already exists for this skill.

- If config exists and the human did not ask to replace it, reuse it.
- If config is missing, ask the human for the AgentDocs URL, API key, and agent name.
- If config exists but the human wants a different environment, run setup again and overwrite it.

If the human only gives a URL, stop there and ask for the API key and agent name before continuing.

## First-Time Setup

Run the bundled script [scripts/agentdocs_skill_client.py](./scripts/agentdocs_skill_client.py) with:

```bash
python ./scripts/agentdocs_skill_client.py setup --base-url https://docs.example.com --api-key your-key --agent-name your-agent
```

The script stores configuration in `.agentdocs.config.json` next to the skill files.

## Daily Use

After setup, prefer the script entrypoints instead of hand-building requests.

Process one task end to end:

```bash
python ./scripts/agentdocs_skill_client.py process
```

Pick up one task only:

```bash
python ./scripts/agentdocs_skill_client.py pickup
```

Complete an already picked task:

```bash
python ./scripts/agentdocs_skill_client.py complete --task-id 12 --result "rewritten text"
```

Report a task failure:

```bash
python ./scripts/agentdocs_skill_client.py complete --task-id 12 --error-message "upstream model timed out"
```

Run continuously:

```bash
python ./scripts/agentdocs_skill_client.py continuous --poll-interval 2
```

## Agent Procedure

1. Check for saved config first.
2. If config is missing, ask the human for URL, API key, and agent name.
3. Run `setup` once.
4. Use `process` for one-shot handling or `continuous` for a worker loop.
5. Build prompts from `source_text`, `action`, `instruction`, and `context`.
6. Submit exactly one of `result` or `error_message`.
7. Do not auto-accept results into the document.
8. If the task is stale, inspect the recovery endpoints before retrying.

## Notes

- AgentDocs authentication is always `Authorization: Bearer <API_KEY>`.
- `POST /api/tasks/next` moves a task from `pending` to `processing`.
- `POST /api/tasks/{task_id}/complete` is valid only while the task is `processing`.
- The bundled script already knows the API paths. Reuse it.
- For protocol details, see [references/workflow.md](./references/workflow.md).