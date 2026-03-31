# API Contract

本文档定义第一版后端接口契约，目标是让后续代码生成直接按此约束实现。

## 1. 通用约定

Base URL:

- /api

认证：

- HTTP Header: Authorization: Bearer <api_key>
- WebSocket 连接成功后，客户端先发送一条 auth 消息

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
- claim_expired

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
        "id": 10,
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
- 更新 raw_markdown
- revision 加 1
- 生成版本快照
- 重建 blocks

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
  "block_id": 10,
  "action": "rewrite",
  "instruction": "改成简历语气，控制在 180 字内",
  "source_text": "原文内容",
  "start_offset": 20,
  "end_offset": 40,
  "doc_revision": 3,
  "auto_apply": false,
  "actor": "browser"
}
```

校验：

- 任务范围必须在同一个 block 内
- source_text 必须与当前 raw_markdown 对应区间一致

### GET /api/tasks

查询参数：

- status 可选
- doc_id 可选

### GET /api/tasks/{task_id}

返回任务详情和当前状态。

### POST /api/tasks/claim

请求：

```json
{
  "agent_name": "picoclaw",
  "limit": 1,
  "lease_seconds": 300
}
```

响应：

```json
{
  "ok": true,
  "data": [
    {
      "id": 9,
      "doc_id": 1,
      "action": "rewrite",
      "instruction": "改成简历语气，控制在 180 字内",
      "source_text": "原文内容",
      "claim_token": "task-9-token",
      "status": "claimed"
    }
  ]
}
```

### POST /api/tasks/{task_id}/heartbeat

请求：

```json
{
  "claim_token": "task-9-token",
  "lease_seconds": 300
}
```

### POST /api/tasks/{task_id}/complete

成功写回：

```json
{
  "claim_token": "task-9-token",
  "result": "改写后的内容",
  "error_message": null
}
```

失败写回：

```json
{
  "claim_token": "task-9-token",
  "result": null,
  "error_message": "model timeout"
}
```

行为：

- 有 result 时转为 done
- 有 error_message 时转为 failed
- 若 auto_apply 且锚点校验成功，则自动 accepted
- 校验失败则转为 conflict

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

## 4. WebSocket 协议

连接：

- GET /ws

客户端首条消息：

```json
{
  "type": "auth",
  "api_key": "your-api-key"
}
```

服务端成功响应：

```json
{
  "type": "auth.ok"
}
```

服务端推送事件：

```json
{
  "type": "task.created",
  "task_id": 9,
  "doc_id": 1
}
```

```json
{
  "type": "task.completed",
  "task_id": 9,
  "doc_id": 1,
  "status": "done"
}
```

```json
{
  "type": "doc.updated",
  "doc_id": 1,
  "revision": 4
}
```

## 5. 关键实现备注

- 所有正文写操作都必须经过 revision 校验
- blocks 始终由 raw_markdown 派生，不接受独立更新
- complete 接口必须校验 claim_token
- accept 时只对 source_text 对应区间执行替换