# AgentDocs

一个面向个人项目的极简 Markdown 协作服务，用于单个用户与单个外部 Agent 协同处理 Markdown 文档。

## 项目定位

- 单用户
- 单外部 Agent
- FastAPI + SQLite
- Markdown 文档编辑
- 局部任务创建、Agent 回写、人工 accept 或 reject
- 文档版本快照与回滚

明确不做：

- 多用户系统
- 复杂权限管理
- 内置 LLM
- 富文本 OT 或 CRDT
- WebSocket 首发
- 多 Agent 并发调度

## 依赖管理

本项目统一使用 uv 管理 Python 环境与依赖。

- 依赖声明：pyproject.toml
- 锁文件：uv.lock
- Python 版本：.python-version
- 本地虚拟环境：.venv

初始化和安装依赖：

```powershell
uv sync
```

如需增加依赖：

```powershell
uv add <package>
```

如需增加开发依赖：

```powershell
uv add --dev <package>
```

## 本地运行

先准备环境变量：

```powershell
Copy-Item .env.example .env
```

启动开发服务：

```powershell
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

生成新迁移：

```powershell
uv run alembic revision --autogenerate -m "your message"
```

运行一个本地模拟 Agent：

```powershell
uv run python scripts/simulate_agent.py --api-key change-me
```

常用调试方式：

```powershell
uv run python scripts/simulate_agent.py --api-key change-me --continuous
uv run python scripts/simulate_agent.py --api-key change-me --mode uppercase
uv run python scripts/simulate_agent.py --api-key change-me --mode fail
```

默认配置来自 .env.example：

- APP_NAME=AgentDocs
- APP_ENV=development
- API_KEY=change-me
- SQLITE_PATH=data/doc.db

## 目录说明

- app: FastAPI 应用代码
- app/api: 路由层
- app/schemas: Pydantic 请求响应模型
- app/services: 业务逻辑与 Markdown 处理
- app/static: 最小前端单页界面
- scripts/simulate_agent.py: 本地模拟 Agent 脚本
- docs/api_contract.md: 第一版接口契约
- docs/architecture.md: 第一版精简架构方案
- agent.md: 后续代码生成约束与实现顺序
- data: SQLite 数据目录

## 当前进度

当前第一批后端业务代码已经落地，并已通过 50 项 pytest 集成测试：

- 文档 CRUD 已实现
- 文档 revision 校验已实现
- blocks 只读解析视图已实现
- 任务创建、next、complete、accept、reject、cancel 已实现
- 任务 retry 与 diff 预览已实现
- 文档版本列表与 rollback 已实现
- 文档删除已实现，并会级联删除对应任务与版本
- Alembic 初始迁移已实现
- 统一错误响应与单 API Key 认证已实现
- 任务失效检测与一键清理已实现，可自动关闭过期 pending 或 processing 任务、关闭失效 done 任务
- 后端已补充基础输入约束，空标题和空 agent_name 会直接返回 validation_error，避免写入脏数据
- 任务详情与领取接口已扩展 richer context，除文档标题、当前 revision、所在 block 与前后文窗口外，还会返回当前选区文本、标题链路与文档大纲，便于 Agent 在不加载整篇正文的前提下获得更稳的任务上下文
- 当前文档已支持一键批量接受所有可安全合并的 done 任务，减少逐条 accept 的重复操作
- 旧任务已支持轻量重定位，可优先按原 block 或全文唯一命中尝试恢复，再决定 accept、retry 或关闭
- 前端任务区已按状态分组展示，并支持按动作或当前 block 做更细的批量接受筛选
- 前端已补可见页短轮询刷新任务状态，页面隐藏时自动暂停，适合低性能服务器部署
- 任务创建区已支持最近说明复用和轻量快捷模板，进一步压缩高频创建路径
- 自定义模板已升级为服务端持久化存储，支持跨设备复用，并兼容从旧版浏览器 localStorage 做一次性迁移
- 文档已支持保存默认任务动作与默认说明，适合个人长期使用时固化常用提示词
- 任务 diff 已升级为原始文本、当前文本、任务结果三栏对照，并把任务按钮收紧为更少、更直接的主次操作
- stale 任务已补恢复预览与“按当前正文重建”工作流，不再只有清理或手工重建两种选择
- 文档工作台顶部已支持直接导出 Markdown 文件，文件名会自动带上标题、revision 与日期，便于本地留档和交付
- 前端已进一步收敛为“文档编辑 + 任务处理”双主区，版本历史折叠显示，常用动作集中在编辑区顶部
- 无变化保存、无变化 accept、无变化 rollback 都已收紧为 no-op，不再制造多余 revision
- pytest 集成测试已建立并覆盖核心流程
- 本地模拟 Agent 脚本已提供，可在没有真实 Agent 时联调任务流程

当前还没有完成的部分包括：

- 前端页面已可用于闭环操作，但仍有进一步打磨空间
- 更细的自动策略和更强的任务审核辅助仍可继续增强
- WebSocket 仍未实现，当前实时感依赖低频短轮询

当前已经明确简化为：

- blocks 只在读取时解析，不持久化
- 任务不使用 claim_token、lease、heartbeat
- 第一版不做 auto_apply
- 第一版不做 WebSocket

## 建议开发顺序

1. 继续补更多异常路径和回归测试
2. 继续压缩前端任务工作台的高频操作路径
3. 继续增强 stale 恢复与任务审核辅助
4. 最后才考虑是否需要 WebSocket

## 文档分工

- README.md 只负责说明项目用途、运行方式、当前状态和开发顺序
- docs/architecture.md 负责保存当前采用的精简设计方案
- docs/api_contract.md 负责保存接口契约
- agent.md 负责约束后续代码生成的实现边界

如果后续设计发生变化，应优先更新 docs/architecture.md 和 docs/api_contract.md，再同步调整 README 的当前状态描述。