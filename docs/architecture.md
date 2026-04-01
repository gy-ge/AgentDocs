# AI 标注式 Markdown 协作方案 v2

> 日期：2026-03-31
> 状态：第一版按最小可行实现收敛

## 一、目标

这是一个部署在 VPS 上的单用户 Markdown 协作服务，用于你和一个外部 Agent 协同处理文档中的局部修改任务。

系统职责：

- 提供 Markdown 文档编辑、任务创建、结果回写、人工确认、版本回滚。
- 只负责存储、状态流转和最基本的冲突校验。
- 不内置 LLM，不承担模型推理。

项目前提：

- 单用户
- 单浏览器会话
- 单个外部 Agent 进程
- 不引入复杂权限管理

## 二、第一版收敛结论

为了尽快进入编码，第一版只保留真正必要的能力。

保留：

- 完整 Markdown 文档保存
- 文本区间任务
- 单 Agent 顺序处理
- 人工 accept 或 reject
- 版本快照与回滚
- 单共享 API Key

去掉：

- blocks 持久化
- WebSocket
- auto_apply
- claim_token、lease、heartbeat
- 多 Agent 并发处理
- 跨 block 任务
- 自动重定位

## 三、系统边界

浏览器负责：

- 编辑 Markdown
- 创建任务
- 查看任务结果
- accept 或 reject
- 查看版本和回滚

服务端负责：

- 保存 documents、tasks、doc_versions
- 在读取文档时解析 blocks 视图
- 校验 revision 和 source_hash
- 维护任务状态

外部 Agent 负责：

- 拉取一个待处理任务
- 调用自己的 LLM
- 写回 result 或 error

## 四、核心设计

### 1. 文档真源

documents.raw_markdown 是唯一真源。

- blocks 只在读取文档时动态解析。
- 数据库不保存 blocks 表。
- 前端不能提交 blocks 反写正文。

### 2. 任务锚点

任务只保存最小锚点信息：

- doc_id
- doc_revision
- start_offset
- end_offset
- source_text
- source_hash
- action
- instruction

创建任务时只需要保证两件事：

- source_text 与当前区间一致
- 该区间不跨 block

### 3. 任务状态机

第一版任务状态只有：

- pending
- processing
- done
- accepted
- rejected
- failed
- cancelled

状态转移保持线性：

- pending -> processing 或 cancelled
- processing -> done 或 failed
- done -> accepted 或 rejected

### 4. 冲突控制

虽然是个人项目，但浏览器和 Agent 都会改同一份文档，所以仍需基本 revision 控制。

规则：

1. documents.revision 只在正文变化时加 1
2. PUT 文档和 accept 都必须提交 expected_revision
3. accept 前重新校验 source_hash
4. 校验失败直接返回 conflict，不自动修复

补充：

- 只有标题变化时，不创建新版本
- 标题和正文都没变化时，更新请求直接视为 no-op
- 如果正文后续删掉或改写了任务目标文本，旧任务不自动改写正文，只会在 accept 或 retry 时被拦住

### 5. Agent 协议

第一版不做复杂 claim 协议，只保留最简单串行处理：

1. Agent 调用 POST /api/tasks/next
2. 服务端取一个 pending 任务并置为 processing
3. Agent 完成后调用 POST /api/tasks/{id}/complete

如果 Agent 异常退出，人工后续可 cancel 或 retry。

当前实现中已经补充 diff 预览与 stale cleanup，作为人工处理旧任务的最小辅助工具。

## 五、数据模型

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

## 六、认证方案

认证保持最简：

- 一个共享 API Key
- 所有 HTTP 请求走 Authorization Header
- 不做用户系统、角色系统、JWT、OAuth

## 七、API 轮廓

文档：

- GET /api/docs
- POST /api/docs
- GET /api/docs/{doc_id}
- PUT /api/docs/{doc_id}
- DELETE /api/docs/{doc_id}
- GET /api/docs/{doc_id}/versions
- POST /api/docs/{doc_id}/versions/{version_id}/rollback

任务：

- POST /api/docs/{doc_id}/tasks
- POST /api/docs/{doc_id}/tasks/cleanup-stale
- GET /api/tasks
- GET /api/tasks/{task_id}
- GET /api/tasks/{task_id}/diff
- POST /api/tasks/next
- POST /api/tasks/{task_id}/complete
- POST /api/tasks/{task_id}/accept
- POST /api/tasks/{task_id}/reject
- POST /api/tasks/{task_id}/cancel
- POST /api/tasks/{task_id}/retry

## 八、实现顺序

1. 建好三张表和基础 schema
2. 完成 documents service
3. 完成任务创建与 next 或 complete
4. 完成 accept 或 reject
5. 完成版本查询和 rollback
6. 再考虑前端细节和实时体验