# Agent.md

## 1. 目标

实现一个部署在 VPS 上的极简 Markdown 协作服务，供单个用户和单个外部 Agent 协同工作。

系统职责：

- 提供 Markdown 文档编辑、任务创建、任务回写、人工 accept 或 reject、版本回滚。
- 不内置 LLM，不做多用户系统，不做复杂权限管理。
- 服务端只负责存储、状态流转和最基本的冲突校验。

## 2. 第一版范围

第一版只保留以下能力：

- 文档 CRUD
- 基于文本区间的任务创建
- 单 Agent 拉取待处理任务并回写结果
- 人工 accept 或 reject
- 文档版本快照与回滚
- 单共享 API Key

第一版明确不做：

- 持久化 blocks 表
- WebSocket 实时推送
- auto_apply
- claim_token、租约、heartbeat
- 多 Agent 并发竞争
- 跨 block 任务
- 自动重定位和复杂冲突恢复

## 3. 核心设计

### 3.1 文档真源

文档唯一真源是 documents.raw_markdown。

- blocks 只在读取文档时临时解析返回。
- 不把 blocks 持久化到数据库。
- 不允许前端用 blocks 覆盖正文。

### 3.2 任务定位

任务只保存最小锚点信息：

- doc_id
- doc_revision
- start_offset
- end_offset
- source_text
- source_hash
- action
- instruction

创建任务时必须校验：

- source_text 与当前 raw_markdown 对应区间一致
- 任务范围不跨 block

### 3.3 冲突控制

系统仍然有两个写入方：浏览器和 Agent。

- documents.revision 每次正文变化加 1
- 修改正文的接口必须带 expected_revision
- accept 前必须重新校验 source_hash
- 不匹配时返回 conflict，不静默覆盖

### 3.4 状态机保持最小

第一版只使用这些状态：

- pending
- processing
- done
- accepted
- rejected
- failed
- cancelled

不引入 claimed、claim_expired、heartbeat 之类状态和协议。

## 4. Agent 交互方式

Agent 使用最简单的串行协议：

- POST /api/tasks/next：领取一个 pending 任务并置为 processing
- POST /api/tasks/{id}/complete：写回 result 或 error

因为第一版只支持单 Agent 进程，所以不做租约和抢占控制。
如果 Agent 中途退出，人工可以把任务改回 pending 或直接 cancel。

## 5. 数据模型

只保留三张核心表。

### documents

- id
- title
- raw_markdown
- revision
- created_at
- updated_at

### tasks

- id
- doc_id
- doc_revision
- start_offset
- end_offset
- source_text
- source_hash
- action
- instruction
- result
- status
- agent_name
- error_message
- created_at
- started_at
- completed_at
- resolved_at

### doc_versions

- id
- doc_id
- revision
- snapshot
- actor
- note
- created_at

## 6. 实现优先级

按以下顺序实现：

1. 数据模型与初始化
2. 文档 CRUD 与 revision 控制
3. Markdown 解析与只读 blocks 视图
4. 任务创建与 next 或 complete
5. accept 或 reject 合并逻辑
6. 版本查询与 rollback
7. 最小前端
8. 自动化测试

## 7. 代码实现要求

- 先写 schema，再写 service，再接路由。
- 复杂逻辑只放在 service 层。
- 所有写操作记录 actor。
- accept 不通过时返回 conflict。
- reject 默认不改正文，只改任务状态。

## 8. 禁止事项

- 不要把 blocks 持久化成真源。
- 不要在第一版实现 WebSocket。
- 不要引入 claim_token、lease、heartbeat。
- 不要在 accept 或 reject 时整段覆盖正文。
- 不要在第一版支持跨 block 任务。