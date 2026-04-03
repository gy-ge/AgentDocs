# API 契约

本文档描述当前 FastAPI 应用实际实现出来的接口形状。

## 通用约定

Base URL：

- /api

认证：

- 所有 /api 路由都要求 Authorization: Bearer <API_KEY>

成功响应包装：

```json
{
  "ok": true,
  "data": {}
}
```

失败响应包装：

```json
{
  "ok": false,
  "error": {
    "code": "conflict",
    "message": "document revision mismatch"
  }
}
```

常见错误码：

- unauthorized
- not_found
- validation_error
- conflict
- invalid_state

## 文档接口

### GET /api/docs

返回文档列表项：

- id
- title
- revision
- updated_at

### POST /api/docs

请求：

```json
{
  "title": "Project Notes",
  "raw_markdown": "# Project Notes\n",
  "actor": "browser"
}
```

响应 data 包含：

- id
- title
- revision

说明：

- title 会先 trim，不能为空
- 文档创建时会立即生成一条版本快照

### GET /api/docs/{doc_id}

返回完整文档：

- id
- title
- raw_markdown
- revision
- default_task_action
- default_task_instruction
- blocks
- updated_at

每个 block 包含：

- heading
- level
- position
- start_offset
- end_offset
- content

### PUT /api/docs/{doc_id}

请求：

```json
{
  "title": "Project Notes",
  "raw_markdown": "# Project Notes\n\nUpdated body\n",
  "expected_revision": 3,
  "actor": "browser",
  "note": "manual edit"
}
```

行为：

- expected_revision 必须匹配当前文档 revision
- 如果只改标题，不增加 revision
- 如果标题和正文都没变，视为 no-op
- 如果 raw_markdown 变化，会增加 revision 并创建新版本快照

### DELETE /api/docs/{doc_id}

删除文档，并级联删除相关任务和版本。

### POST /api/docs/{doc_id}/task-defaults

请求：

```json
{
  "actor": "browser",
  "default_task_action": "rewrite",
  "default_task_instruction": "Rewrite in a more formal tone"
}
```

说明：

- 只更新文档元信息
- 不增加 revision
- 如果 action 为空但 instruction 不为空，后端会回退为 rewrite

### POST /api/docs/{doc_id}/tasks

请求：

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

规则：

- doc_revision 必须匹配当前文档 revision
- source_text 必须与当前文档切片完全一致
- 任务区间必须落在同一个解析后的 block 内

### POST /api/docs/{doc_id}/tasks/cleanup-stale

清理当前文档的 stale 任务。

- stale 的 pending 和 processing 任务会变成 cancelled
- stale 的 done 任务会变成 rejected

响应 data 包含：

- doc_id
- cancelled
- rejected
- unchanged

### POST /api/docs/{doc_id}/tasks/accept-ready

对当前文档执行一次批量接受。

当 UI 需要先展示人工审阅摘要时，应先调用对应的 preview 接口。

批量接受当前文档里可以安全合并的 done 任务。

请求：

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

可选筛选：

- action
- start_offset 和 end_offset 一起提供
- limit，范围 1 到 50

响应 data 包含：

- doc_id
- document_revision
- accepted
- skipped
- accepted_task_ids
- skipped_tasks
- rollback_version_id
- rollback_revision

### POST /api/docs/{doc_id}/tasks/accept-ready-preview

预览当前批量接受筛选条件下的结果，不会修改文档或任务状态。

请求体与 POST /api/docs/{doc_id}/tasks/accept-ready 相同。

响应 data 包含：

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

## 任务接口

### GET /api/tasks

可选查询参数：

- status
- doc_id

返回带 stale 元数据的任务列表。

### GET /api/tasks/events

返回 text/event-stream 响应，用于浏览器侧实时同步。

规则：

- 与其他 /api 路由一样，需要 Authorization: Bearer <API_KEY>
- 建立订阅后会立即发送 ready 事件
- 成功写操作后会发送 task.changed、tasks.changed 和 document.changed 事件
- 浏览器工作台优先使用该事件流，同步失败时再退回轮询

### GET /api/tasks/{task_id}

返回完整任务以及 context。

任务字段包括：

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
- created_at
- started_at
- completed_at
- resolved_at

context 字段包括：

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

只有任务已经有 result 时才能调用。

响应 data 包含：

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

返回 stale 任务的恢复预览。

响应 data 包含：

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

请求：

```json
{
  "agent_name": "simulated-agent"
}
```

行为：

- 领取最早的一条 pending 任务
- 把状态改成 processing
- 记录 agent_name 和 started_at
- 如果队列为空，返回 data: null

### POST /api/tasks/{task_id}/complete

成功回写：

```json
{
  "result": "Updated text",
  "error_message": null
}
```

失败回写：

```json
{
  "result": null,
  "error_message": "model timeout"
}
```

规则：

- 任务必须处于 processing
- result 和 error_message 必须二选一
- result 会把任务改成 done
- error_message 会把任务改成 failed

### POST /api/tasks/{task_id}/accept

请求：

```json
{
  "expected_revision": 3,
  "actor": "browser",
  "note": "accept task result"
}
```

规则：

- 任务必须是 done 且有 result
- expected_revision 必须匹配当前文档 revision
- 当前文档切片必须仍然匹配 source_text 和 source_hash
- 如果 result 与 source_text 完全相同，任务会变成 accepted，但不会创建新 revision

### POST /api/tasks/{task_id}/reject

规则：

- 任务必须是 done
- 任务会变成 rejected
- 不会改动文档正文

### POST /api/tasks/{task_id}/cancel

规则：

- 只有 pending 和 processing 任务可以取消
- 不会改动文档正文

### POST /api/tasks/{task_id}/retry

规则：

- 只有 failed、cancelled 和 rejected 任务可以重试
- 当前文档区间必须仍然匹配 source_text
- 区间仍必须位于单个 block 内
- 任务会回到 pending，并清空上一次执行信息

### POST /api/tasks/{task_id}/relocate

规则：

- processing 任务不能重定位
- accepted 任务不需要重定位
- 可能返回以下策略之一：
  - current_selection_match
  - same_block_position_match
  - same_heading_unique_match
  - document_unique_match

### POST /api/tasks/{task_id}/recover

支持的 mode：

- relocate
- requeue_from_current

请求：

```json
{
  "mode": "requeue_from_current",
  "actor": "browser"
}
```

行为：

- relocate 会走同一套重定位流程，并返回 source task 和策略
- requeue_from_current 会先关闭旧任务，再按当前文档区间创建一条新的 pending 任务

## 模板接口

### GET /api/task-templates

返回所有服务端持久化模板。

### POST /api/task-templates

```json
{
  "name": "Formal rewrite",
  "action": "rewrite",
  "instruction": "Use a formal and restrained tone"
}
```

### PUT /api/task-templates/{template_id}

请求结构与创建一致。

### DELETE /api/task-templates/{template_id}

删除一条模板。

## 版本接口

### GET /api/docs/{doc_id}/versions

返回版本列表项：

- id
- revision
- actor
- note
- created_at

### POST /api/docs/{doc_id}/versions/{version_id}/rollback

请求：

```json
{
  "expected_revision": 5,
  "actor": "browser",
  "note": "rollback to version 2"
}
```

规则：

- expected_revision 必须匹配当前文档 revision
- 如果目标快照和当前正文完全一致，rollback 是 no-op
- 否则会恢复正文、增加 revision，并生成新的版本快照