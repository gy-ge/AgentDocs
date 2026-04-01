# AgentDocs 架构说明

AgentDocs 是一个围绕单份 Markdown 文档、单个人工审核者和单个外部 Agent 工作流构建的小型异步协作系统。当前实现优先保证显式状态流转、revision 校验和恢复工具，而不是让 Agent 在无审核的情况下直接改写正文。

## 系统边界

系统会做的事情：

- 使用 SQLite 存储 Markdown 文档、任务状态、文档版本和任务模板
- 在读取文档时把 Markdown 解析成运行时 block 视图
- 只允许在当前文档里创建单个 block 范围内的任务
- 允许外部 Agent 轮询领取任务、回写结果或上报失败
- 在 Agent 结果真正改写文档前，要求人工显式 accept
- 检测 stale 任务，并提供清理、重定位、预览和按当前正文重建能力

系统不会做的事情：

- 不内置 LLM 推理
- 不实现多用户身份和角色体系
- 不持久化 blocks 表
- 不使用 WebSocket、SSE、auto-apply、lease、heartbeat 或 claim-token 协议

## 真源

documents.raw_markdown 是唯一的文档真源。

- blocks 通过解析 raw_markdown 按需生成
- 前端不会把 blocks 反向提交给服务端
- accept 只会替换任务记录的精确 source 区间

## 数据模型

当前 schema 一共有四张表：

- documents：标题、正文、revision、默认任务设置、时间戳
- tasks：source 区间、source_text 与 source_hash、action、instruction、结果、状态、时间戳
- doc_versions：文档创建、正文修改、会改变正文的 accept，以及 rollback 产生的快照
- task_templates：保存在服务端的可复用 action 与 instruction 模板

## 任务生命周期

当前实际状态有：

- pending
- processing
- done
- accepted
- rejected
- failed
- cancelled

主要状态流转：

- pending -> processing：通过 POST /api/tasks/next
- processing -> done 或 failed：通过 POST /api/tasks/{id}/complete
- done -> accepted：通过 POST /api/tasks/{id}/accept
- done -> rejected：通过 POST /api/tasks/{id}/reject
- pending 或 processing -> cancelled：通过 POST /api/tasks/{id}/cancel
- failed、cancelled 或 rejected -> pending：通过 POST /api/tasks/{id}/retry

## Stale 检测与恢复

stale 检测只对 pending、processing 和 done 任务生效。

- 如果当前文档切片仍然匹配 source_text 和 source_hash，则任务不是 stale。
- 如果不匹配，后端会返回 selection_removed、selection_shifted 或 source_changed。
- 重定位会依次尝试原 block 位置、唯一同标题 block，以及全文唯一文本命中。
- 如果仅重定位还不够，recover 接口可以先关闭旧任务，再按当前选区重建一条新的 pending 任务。

## 主要组件

- app/api：FastAPI 路由、认证依赖和响应序列化
- app/services/document_service.py：文档 CRUD、版本快照、rollback 和默认任务设置
- app/services/task_service.py：任务状态机、stale 检测、diff、批量 accept、清理、重定位和恢复
- app/services/markdown.py：轻量级标题分块解析器
- app/static/index.html：最小浏览器工作台
- scripts/simulate_agent.py：本地 API 联调用模拟 worker

