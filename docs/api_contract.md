# API Contract

本文档定义第一版后端接口契约，目标是让后续代码生成直接按此约束实现。

## 1. 通用约定

Base URL:

- /api

认证：

- HTTP Header: Authorization: Bearer <api_key>

统一响应约定：

成功：

```json
{
  "ok": true,
  "data": {}
}
```

失败：

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

## 2. 文档接口

### GET /api/docs

说明：获取文档列表。

响应：

```json
{
  "ok": true,
  "data": [
    {
      "id": 1,
      "title": "研究笔记",
      "revision": 3,
      "updated_at": "2026-03-31T10:00:00Z"
    }
  ]
}
```

### POST /api/docs

约束：

- title 会先 trim，且不能为空字符串
- actor 会先 trim，且不能为空字符串

请求：

```json
{
  "title": "研究笔记",
  "raw_markdown": "# 研究笔记\n",
  "actor": "browser"
}
```

### GET /api/docs/{doc_id}

响应：

```json
{
  "ok": true,
  "data": {
    "id": 1,
    "title": "研究笔记",
    "raw_markdown": "# 研究笔记\n## 背景\n内容",
    "revision": 3,
    "blocks": [
      {
        "heading": "背景",
        "level": 2,
        "position": 0,
        "start_offset": 7,
        "end_offset": 15,
        "content": "内容"
      }
    ],
    "updated_at": "2026-03-31T10:00:00Z"
  }
}
```

### PUT /api/docs/{doc_id}

约束：

- title 会先 trim，且不能为空字符串
- actor 会先 trim，且不能为空字符串

请求：

```json
{
  "title": "研究笔记",
  "raw_markdown": "# 研究笔记\n## 背景\n更新后的内容",
  "expected_revision": 3,
  "actor": "browser",
  "note": "manual edit"
}
```

行为：

- 校验 expected_revision
- 只有 raw_markdown 变化时才更新正文、revision 加 1，并生成版本快照
- 如果只是 title 变化，只更新 title，不创建新版本
- 如果 title 和 raw_markdown 都没变化，返回当前文档，不创建新版本
- 读取时动态解析 blocks

### DELETE /api/docs/{doc_id}

说明：删除文档及其任务、版本。

### POST /api/docs/{doc_id}/tasks/cleanup-stale

说明：

- 按当前正文批量清理当前文档的失效任务
- stale 的 pending 或 processing 任务会被标记为 cancelled
- stale 的 done 任务会被标记为 rejected
- 该接口只做安全关闭，不会自动 accept 或自动重建任务

响应：

```json
{
  "ok": true,
  "data": {
    "doc_id": 1,
    "cancelled": 2,
    "rejected": 1,
    "unchanged": 3
  }
}
```

### POST /api/docs/{doc_id}/tasks/accept-ready

说明：

- 批量接受当前文档中所有状态为 done 且仍可安全合并的任务
- 服务端会按 start_offset 倒序处理，尽量避免前一个 accept 改写正文后破坏后一个任务的 offset
- 无法安全接受的任务不会报整批失败，而是留在 skipped_tasks 中返回原因

请求：

```json
{
  "actor": "browser",
  "note": "bulk accept from ui",
  "action": "rewrite",
  "start_offset": 7,
  "end_offset": 32,
  "limit": 20
}
```

可选筛选字段：

- action: 只接受指定 action 的 done 任务
- start_offset 与 end_offset: 只接受当前正文某个区间内的 done 任务，通常用于“当前 block”范围
- limit: 单次最多处理多少条，建议在低性能服务器上保守设置为 10 到 20

响应：

```json
{
  "ok": true,
  "data": {
    "doc_id": 1,
    "document_revision": 5,
    "accepted": 2,
    "skipped": 1,
    "accepted_task_ids": [12, 11],
    "skipped_tasks": [
      {
        "task_id": 10,
        "reason": "task_stale"
      }
    ]
  }
}
```

说明：

- 当前前端任务工作台不额外增加新的分组接口，而是基于 GET /api/tasks 的结果在浏览器本地分组，避免服务器端额外计算与更多请求
- 当前默认实时策略为“前台页面短轮询”，不会在页面隐藏时持续刷新，也没有引入 WebSocket 长连接

### GET /api/docs/{doc_id}/versions

响应：

```json
{
  "ok": true,
  "data": [
    {
      "id": 5,
      "revision": 4,
      "actor": "browser",
      "note": "manual edit",
      "created_at": "2026-03-31T10:00:00Z"
    }
  ]
}
```

### POST /api/docs/{doc_id}/versions/{version_id}/rollback

约束：

- actor 会先 trim，且不能为空字符串

请求：

```json
{
  "expected_revision": 4,
  "actor": "browser",
  "note": "rollback to version 5"
}
```

## 3. 任务接口

### POST /api/docs/{doc_id}/tasks

约束：

- action 会先 trim，且不能为空字符串

请求：

```json
{
  "action": "rewrite",
  "instruction": "改成简历语气，控制在 180 字内",
  "source_text": "原文内容",
  "start_offset": 20,
  "end_offset": 40,
  "doc_revision": 3
}
```

校验：

- 任务范围必须在同一个 block 内
- source_text 必须与当前 raw_markdown 对应区间一致
- 第一版不支持多段落或跨 block 选区

### GET /api/tasks

查询参数：

- status 可选
- doc_id 可选

### GET /api/tasks/{task_id}

返回任务详情和当前状态。

补充字段：

- is_stale: 当前正文是否已与任务源文本失配
- stale_reason: 失配原因，可能是 selection_removed、selection_shifted、source_changed
- recommended_action: 针对 stale 任务的建议动作，第一版可能为 reject 或 cancel
- context: 当前文档上下文快照，便于前端或外部 Agent 判断任务环境

context 字段结构：

- document_title: 当前文档标题
- document_revision: 当前文档 revision，区别于任务自己的 doc_revision
- block: 当前选区所在 block 的标题和范围；如果当前正文已无法定位 block，则为 null
- block_markdown: 当前 block 的完整 Markdown 文本；如果当前正文已无法定位 block，则为 null
- context_before: 当前正文里选区前最多 200 个字符
- context_after: 当前正文里选区后最多 200 个字符

### GET /api/tasks/{task_id}/diff

说明：

- 返回 source_text、result_text、current_text 和 unified diff
- 当 can_accept 为 false 时，额外返回 conflict_reason，便于前端或外部 Agent 判断是文本变更、结构位移还是选区已失效
- 当 can_accept 为 false 时，也会返回 recommended_action，便于前端直接提示“关闭旧任务”而不是只提示冲突
- 当任务已有 result 时可用于前端预览 accept 前后的差异

响应：

```json
{
  "ok": true,
  "data": {
    "task_id": 9,
    "doc_id": 1,
    "current_text": "原文内容",
    "source_text": "原文内容",
    "result_text": "改写后的内容",
    "can_accept": true,
    "conflict_reason": null,
    "recommended_action": null,
    "diff": "--- source\n+++ result\n@@ -1 +1 @@\n-原文内容\n+改写后的内容"
  }
}
```

### POST /api/tasks/next

说明：

- 领取一个 pending 任务并置为 processing
- 响应体会直接返回任务当前的 stale 描述与 context 快照，便于 Agent 在处理前拿到周边上下文

响应 data 示例：

```json
{
  "id": 9,
  "doc_id": 1,
  "doc_revision": 3,
  "start_offset": 20,
  "end_offset": 40,
  "source_text": "原文内容",
  "action": "rewrite",
  "instruction": "改成简历语气，控制在 180 字内",
  "status": "processing",
  "agent_name": "agent-one",
  "is_stale": false,
  "stale_reason": null,
  "recommended_action": null,
  "context": {
    "document_title": "研究笔记",
    "document_revision": 3,
    "block": {
      "heading": "背景",
      "level": 2,
      "position": 1,
      "start_offset": 7,
      "end_offset": 32
    },
    "block_markdown": "## 背景\n原文内容\n",
    "context_before": "# 研究笔记\n## 背景\n",
    "context_after": "\n## 结论\n待补充"
  }
}
```

约束：

- agent_name 会先 trim，且不能为空字符串

请求：

```json
{
  "agent_name": "picoclaw"
}
```

### POST /api/tasks/{task_id}/relocate

说明：

- 尝试把旧任务重新对齐到当前正文
- processing 任务和 accepted 任务不允许重定位
- 重定位会优先尝试原 block 位置精确命中，再尝试同标题 block 唯一命中，最后尝试全文唯一命中
- 重定位成功后会更新 task 的 start_offset、end_offset 和 doc_revision，但不会改正文，也不会改变任务状态

响应：

```json
{
  "ok": true,
  "data": {
    "task": {
      "id": 9,
      "doc_id": 1,
      "doc_revision": 4,
      "start_offset": 26,
      "end_offset": 30,
      "source_text": "原文",
      "action": "rewrite",
      "status": "done",
      "is_stale": false,
      "stale_reason": null,
      "recommended_action": null,
      "context": {
        "document_title": "研究笔记",
        "document_revision": 4,
        "block": {
          "heading": "背景",
          "level": 2,
          "position": 1,
          "start_offset": 7,
          "end_offset": 32
        },
        "block_markdown": "## 背景\n新的原文\n",
        "context_before": "# 研究笔记\n## 背景\n新的",
        "context_after": "\n## 结论\n待补充"
      }
    },
    "relocation_strategy": "same_block_position_match"
  }
}
```

### POST /api/tasks/{task_id}/complete

成功写回：

```json
{
  "result": "改写后的内容",
  "error_message": null
}
```

失败写回：

```json
{
  "result": null,
  "error_message": "model timeout"
}
```

行为：

- 有 result 时转为 done
- 有 error_message 时转为 failed
- 必须且只能提供 result 或 error_message 其中一个
- 不自动改正文

### POST /api/tasks/{task_id}/accept

约束：

- actor 会先 trim，且不能为空字符串

请求：

```json
{
  "expected_revision": 3,
  "actor": "browser",
  "note": "accept ai result"
}
```

### POST /api/tasks/{task_id}/reject

说明：

- reject 默认不改正文，只改状态

### POST /api/tasks/{task_id}/cancel

### POST /api/tasks/{task_id}/retry

说明：

- 允许 failed、cancelled、rejected 三种状态重新进入 pending
- retry 前重新校验当前文档区间是否仍与 source_text 一致
- retry 成功后会清空 agent_name、result、error_message 和时间戳
- 如果正文已删除或改写掉原始目标文本，旧任务仍会保留，但 accept 会返回 conflict，retry 会返回 validation_error
- 如果任务 result 与 source_text 完全相同，accept 只会把任务标记为 accepted，不会产生新的 revision 或版本快照

## 4. 第一版范围说明

第一版不实现 WebSocket。

浏览器端通过主动刷新或重新请求列表获知最新状态。

## 5. 关键实现备注

- 所有正文写操作都必须经过 revision 校验
- blocks 始终由 raw_markdown 派生，不接受独立更新
- 任务状态流转为 pending -> processing -> done 或 failed -> accepted 或 rejected
- stale 检查只针对 pending、processing、done 三种仍受正文当前位置约束的任务；accepted、rejected、cancelled 只保留结果记录
- cancel 当前允许 pending 和 processing 两种状态
- retry 当前允许 failed、cancelled、rejected 三种状态
- accept 时只对 source_text 对应区间执行替换
- rollback 到当前快照时视为 no-op，不创建新 revision