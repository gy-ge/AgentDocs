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

请求：

```json
{
  "action": "rewrite",
  "instruction": "改成简历语气，控制在 180 字内",
  "source_text": "原文内容",
  "start_offset": 20,
  "end_offset": 40,
  "doc_revision": 3,
  "actor": "browser"
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

### GET /api/tasks/{task_id}/diff

说明：

- 返回 source_text、result_text、current_text 和 unified diff
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
    "diff": "--- source\n+++ result\n@@ -1 +1 @@\n-原文内容\n+改写后的内容"
  }
}
```

### POST /api/tasks/next

请求：

```json
{
  "agent_name": "picoclaw"
}
```

响应：

```json
{
  "ok": true,
  "data": {
    "id": 9,
    "doc_id": 1,
    "action": "rewrite",
    "instruction": "改成简历语气，控制在 180 字内",
    "source_text": "原文内容",
    "status": "processing"
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

请求：

```json
{
  "expected_revision": 3,
  "actor": "browser",
  "note": "accept ai result"
}
```

### POST /api/tasks/{task_id}/reject

请求：

```json
{
  "actor": "browser",
  "note": "reject ai result"
}
```

说明：

- reject 默认不改正文，只改状态

### POST /api/tasks/{task_id}/cancel

请求：

```json
{
  "actor": "browser",
  "note": "cancel before processing"
}
```

### POST /api/tasks/{task_id}/retry

说明：

- 允许 failed、cancelled、rejected 三种状态重新进入 pending
- retry 前重新校验当前文档区间是否仍与 source_text 一致
- retry 成功后会清空 agent_name、result、error_message 和时间戳
- 如果正文已删除或改写掉原始目标文本，旧任务仍会保留，但 accept 会返回 conflict，retry 会返回 validation_error

## 4. 第一版范围说明

第一版不实现 WebSocket。

浏览器端通过主动刷新或重新请求列表获知最新状态。

## 5. 关键实现备注

- 所有正文写操作都必须经过 revision 校验
- blocks 始终由 raw_markdown 派生，不接受独立更新
- 任务状态流转为 pending -> processing -> done 或 failed -> accepted 或 rejected
- cancel 当前允许 pending 和 processing 两种状态
- retry 当前允许 failed、cancelled、rejected 三种状态
- accept 时只对 source_text 对应区间执行替换