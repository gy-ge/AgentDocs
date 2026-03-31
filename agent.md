# Agent.md

## 1. 目标

实现一个部署在 VPS 上的极简 Markdown 协作服务，供单个用户和单个外部 Agent 协同工作。

系统职责：

- 提供 Markdown 文档编辑、任务创建、任务回写、人工确认、版本回滚。
- 不内置 LLM，不做多用户系统，不做复杂权限管理。
- 服务端只负责存储、任务编排、状态流转、冲突校验和实时推送。

## 2. 非目标

- 不做团队协作。
- 不做富文本 OT/CRDT。
- 不做复杂工作流编排。
- 不把 Agent 逻辑部署到本服务内。

## 3. 架构约束

- 后端使用 FastAPI。
- 数据库使用 SQLite，并开启 WAL。
- 前端先做单页应用，优先保证可用性，不追求复杂 UI。
- 外部 Agent 通过 HTTP API 轮询待处理任务并写回结果。
- 实时通知通过 WebSocket 推送，但 WebSocket 只负责通知，不承载核心业务写入。

## 4. 核心设计原则

### 4.1 文档真源

文档的唯一真源是 raw_markdown，而不是 blocks。

- documents 表必须保存完整 Markdown 文本。
- blocks 是派生视图，用于前端渲染、局部定位和列表展示。
- 每次保存文档时，先更新 raw_markdown，再重新解析生成 blocks。
- 不允许前端直接把 blocks 当作真源覆盖文档，避免标题拆分和任务标记失真。

### 4.2 任务定位必须可重放

任务不能只绑定 block_id，必须同时保存创建时的文本锚点信息。

每个任务至少保存：

- doc_id
- doc_revision
- start_block_id
- start_offset
- end_offset
- source_text
- source_hash
- action
- instruction
- auto_apply

如果任务跨多个 block，也必须能根据 offset 和 hash 找回原始范围。

### 4.3 人和 Agent 依然是双写方

即使是单人系统，也存在浏览器编辑和 Agent 回写两个写入者，所以必须做冲突控制。

- documents 表增加 revision 整数版本号。
- 所有修改文档内容的接口都必须带 expected_revision。
- revision 不一致时返回冲突，不静默覆盖。
- accept、reject、auto apply 前必须再次校验任务锚点是否仍然匹配当前文档。

### 4.4 任务结果不能直接盲替换

只有当以下条件同时满足时，任务结果才能合并到文档：

- 任务状态允许合并。
- 当前文档 revision 与任务可接受范围一致，或者锚点重定位成功。
- source_hash 仍与当前目标文本一致。

若不满足，则任务进入 conflict 状态，等待人工处理。

## 5. Markdown 标记规则

保留包裹式标记语法：

<!-- @ai:rewrite 用学术中文重写 -->
待处理内容
<!-- /ai -->

约束如下：

- 不允许嵌套。
- 一个任务的起止标记必须在同一份文档内闭合。
- 第一版禁止跨标题创建任务，任务范围必须限制在单个 block 内。
- auto_apply 只允许用于低风险操作，例如 summarize 和格式整理；rewrite 和 custom 默认需要人工确认。
- 前端解析出任务后，应移除标记再保存文档，避免标记长期污染正文。

## 6. 推荐任务状态机

不要只用 pending -> done -> accepted/rejected。

使用以下状态：

- pending: 已创建，待领取
- claimed: 某个 Agent 已领取，带租约
- processing: Agent 正在处理
- done: 已产出结果，待合并或待人工确认
- accepted: 结果已合并入文档
- rejected: 人工拒绝
- failed: 处理失败
- conflict: 结果可用，但因 revision 或锚点漂移无法自动合并
- cancelled: 任务在处理前被撤销

额外字段：

- claimed_by
- claim_token
- claim_expires_at
- attempt_count
- error_message

## 7. Agent 领取协议

不要让多个 Agent 通过简单轮询同一批 pending 任务后重复处理。

至少提供以下接口：

- POST /api/tasks/claim
  - 输入: agent_name, limit
  - 行为: 原子地领取若干 pending 任务并写入 claim_token 和 claim_expires_at
- POST /api/tasks/{id}/heartbeat
  - 延长租约
- POST /api/tasks/{id}/complete
  - 写回 result 或 error

如果 claim_expires_at 超时未续租，任务可重新回到 pending。

## 8. 接口约束

### 8.1 文档接口

- GET /api/docs
- POST /api/docs
- GET /api/docs/{id}
- PUT /api/docs/{id}
- DELETE /api/docs/{id}
- GET /api/docs/{id}/versions
- POST /api/docs/{id}/versions/{version_id}/rollback

PUT /api/docs/{id} 请求体建议为：

- title
- raw_markdown
- expected_revision
- actor
- note 可选

响应中返回：

- doc_id
- revision
- parsed_blocks
- updated_at

### 8.2 任务接口

- POST /api/docs/{id}/tasks
- GET /api/tasks?status=pending|claimed|processing|done|conflict
- GET /api/tasks/{id}
- POST /api/tasks/claim
- POST /api/tasks/{id}/heartbeat
- POST /api/tasks/{id}/complete
- POST /api/tasks/{id}/accept
- POST /api/tasks/{id}/reject
- POST /api/tasks/{id}/cancel

创建任务时必须保存：

- target_text
- target_range
- doc_revision
- source_hash

### 8.3 WebSocket

只推送事件，不传递认证信息到 URL 查询串。

事件类型建议：

- doc.updated
- task.created
- task.claimed
- task.completed
- task.accepted
- task.rejected
- task.conflict

## 9. 认证要求

这是个人项目，认证保持最简。

- 第一版只使用一个共享 API Key
- HTTP 请求通过 Authorization Header 传递
- WebSocket 连接建立后发送第一条 auth 消息完成校验

要求只有三条：

- 通过 HTTPS 使用
- 不把 key 放进 URL 查询串
- 不引入用户、角色、权限矩阵

如果后续要拆分浏览器和 Agent 的 key，再作为第二步增强，而不是第一版前置条件。

## 10. 数据模型建议

建议最少包含以下表：

### documents

- id
- title
- raw_markdown
- revision
- created_at
- updated_at

### blocks

- id
- doc_id
- heading
- level
- position
- start_offset
- end_offset
- content
- updated_at

### tasks

- id
- doc_id
- start_block_id
- start_offset
- end_offset
- doc_revision
- source_text
- source_hash
- action
- instruction
- result
- result_hash
- status
- auto_apply
- claimed_by
- claim_token
- claim_expires_at
- attempt_count
- error_message
- created_at
- done_at
- resolved_at

### doc_versions

- id
- doc_id
- revision
- snapshot
- actor
- note
- created_at

## 11. 合并规则

accept 或 auto apply 的流程必须是：

1. 读取当前 documents.raw_markdown 和 revision。
2. 根据任务记录的 offset 和 source_hash 校验目标文本。
3. 校验通过则替换目标范围，写入新 revision。
4. 保存版本快照。
5. 重建 blocks。
6. 更新任务状态并推送事件。

reject 的流程必须是：

1. 如果正文尚未被该任务结果改写，只更新任务状态为 rejected。
2. 不要盲目用 original 覆盖当前 block。

说明：reject 不是回滚整段正文，除非能证明当前正文正是该任务自动合并后的结果。

## 12. 代码生成优先级

按以下顺序实现：

1. 数据模型与迁移
2. 文档 CRUD 与 revision 控制
3. Markdown 解析和 block 派生
4. 任务创建与锚点保存
5. 任务 claim/complete 协议
6. accept/reject/conflict 合并逻辑
7. WebSocket 事件推送
8. 最小可用前端
9. 版本回滚

## 13. 代码实现要求

- 先写清楚 Pydantic schema，再写路由，再写 service 层。
- 路由层不直接写复杂业务逻辑。
- 文本替换、revision 校验、任务状态流转应集中在 service 层。
- 所有状态转移必须显式校验，不允许任意跨状态更新。
- 所有写操作都要记录 actor。
- 为核心流程补测试：任务创建、claim、complete、accept、reject、conflict、rollback。

## 14. 禁止事项

- 不要把 blocks 当作持久化真源。
- 不要只靠 block_id 合并结果。
- 不要在 accept 或 reject 时整块覆盖正文。
- 不要让 WebSocket URL 携带明文 key。
- 不要把 pending 任务直接暴露给多个 Agent 自由竞争而没有 claim 机制。
- 不要在第一版支持跨 block 任务。

## 15. 第一版范围结论

为了尽快得到稳定可生成代码的版本，第一版建议缩到以下范围：

- 单文档 Markdown 编辑
- 基于单个 block 的任务创建
- 外部 Agent 领取和回写
- 人工 accept/reject
- revision 冲突检测
- 版本快照和回滚
- WebSocket 通知
- 单共享 API Key 认证

明确不做：

- 跨 block 任务
- 嵌套任务
- 多 Agent 并发竞争
- 自动无冲突重定位
- 复杂权限管理

如果后续要扩展，再在第二版加入跨 block 锚点、重定位和更复杂的富文本体验。