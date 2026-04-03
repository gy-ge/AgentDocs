# AgentDocs

AgentDocs 是一个面向单个作者与单个外部 Agent 工作流的极简 Markdown 协作服务。后端使用 FastAPI 和 SQLite，前端是单文件静态工作台；Markdown block 只在读取时解析，不会作为独立真源持久化。

[架构说明](docs/architecture_zh.md) | [API 契约](docs/api_contract_zh.md) | [English README](README.md)

## 当前范围

当前已经实现：

- 带 revision 乐观并发校验的文档 CRUD
- 基于 Markdown 选区的单 block 任务创建
- 通过 REST API 完成 Agent 领取与回写
- 基于认证 SSE 的任务与文档更新流，用于浏览器实时同步
- 人工 accept、reject、cancel、retry 与 rollback
- 任务 diff 预览、批量接受预览、stale 检测、stale 清理、重定位与按当前正文重建
- 服务端持久化任务模板与文档级默认任务设置
- Word 风格浏览器工作台：行内审阅浮窗、选区快捷工具栏、评论栏、底部折叠抽屉、审阅徽章与键盘快捷键
- 本地模拟 Agent 脚本

当前明确不做：

- 内置 LLM 推理
- 多用户账户或复杂权限系统
- WebSocket 推送
- 无人工确认的自动应用结果
- 持久化 block 表
- lease、heartbeat、claim token 一类任务协议

## 环境要求

- Python 3.10+
- uv

## 快速开始

如果本机还没有 Python 3.10，先安装并固定版本：

```bash
uv python install 3.10
uv python pin 3.10
```

安装依赖：

```bash
uv sync
```

创建环境变量文件：

```bash
cp .env.example .env
```

Windows PowerShell 可用：

```powershell
Copy-Item .env.example .env
```

.env.example 默认值：

- APP_NAME=AgentDocs
- APP_ENV=development
- API_KEY=change-me
- SQLITE_PATH=data/doc.db

默认 `SQLITE_PATH=data/doc.db`。现在项目会在首次迁移或启动时自动创建缺失的父目录，因此不需要手工新建 `data/`。

启动前先执行迁移：

```bash
uv run alembic upgrade head
```

启动后端：

```bash
uv run uvicorn app.main:app --reload
```

然后访问 http://127.0.0.1:8000，并在浏览器弹出的连接设置里填写 `.env` 中的 `API_KEY`。按默认示例配置，这个值是 `change-me`。

运行完整测试：

```bash
uv run pytest
```

如果是第一次跑包含浏览器用例的测试，先安装 Playwright Chromium：

```bash
uv run playwright install chromium
```

## Docker 部署

在仓库根目录执行：

```bash
docker compose up --build -d
```

`docker-compose.yml` 现在默认基于当前仓库里的 `Dockerfile` 本地构建镜像，不再依赖预先发布的 GHCR 镜像。

容器入口会在启动 Uvicorn 之前自动执行 `alembic upgrade head`。运行前仍需要先准备好 `.env` 文件，步骤与上面的快速开始一致。

第一次打开 http://127.0.0.1:8000 时，需要在浏览器弹出的连接设置里输入 `.env` 中的共享 API Key。按默认示例配置，这个值是 `change-me`。

常用命令：

```bash
docker compose logs -f
docker compose ps
docker compose down
```

SQLite 数据库会持久化在名为 `agentdocs-data` 的 Docker volume 中，并挂载到容器内的 `/app/data`。

## 启动排查

- 如果 `uv sync` 提示当前 Python 版本不满足要求，先执行 `uv python install 3.10`，然后重新运行 `uv sync`。
- 如果你自定义了 `SQLITE_PATH`，请确保该路径的父目录可写；当前默认配置会自动创建缺失目录，但不会绕过权限问题。
- 如果浏览器能打开页面但 API 请求返回 401，请在连接设置里填写 `.env` 中的 `API_KEY`，默认示例值是 `change-me`。

## 认证方式

所有 /api 路由都要求以下请求头：

```text
Authorization: Bearer <API_KEY>
```

当前实现不使用 X-API-KEY。

## 模拟 Agent

执行一次任务：

```bash
uv run python scripts/simulate_agent.py --api-key change-me
```

常用变体：

```bash
uv run python scripts/simulate_agent.py --api-key change-me --continuous
uv run python scripts/simulate_agent.py --api-key change-me --mode uppercase
uv run python scripts/simulate_agent.py --api-key change-me --mode fail
```

## UI 端到端测试

单独执行浏览器 E2E：

```bash
uv run pytest tests/test_ui_e2e.py
```

当前覆盖内容：

- 文档创建与自动保存反馈
- 编辑器侧任务标记与任务审阅联动
- 服务端 revision 变化后的 Reload Latest 冲突恢复
- 窄屏下任务标记区可用性

测试会自动启动临时数据库、Uvicorn 进程和模拟 Agent，因此不依赖你手工启动本地服务。

## Agent 接入

外部 Agent 协议保持很小。

1. 调用 POST /api/tasks/next，并传入 {"agent_name": "your-agent"}。服务端会返回一条 pending 任务，并将其改为 processing。
2. 使用任务顶层字段 source_text、action、instruction 生成提示词。
3. 使用 context 对象获取受控上下文。当前字段包括：
	- document_title
	- document_revision
	- current_selection_text
	- block
	- block_markdown
	- heading_path
	- document_outline
	- context_before
	- context_after
4. 调用 POST /api/tasks/{task_id}/complete 时，result 和 error_message 二选一。
5. 如果文档变化导致任务 stale，可结合 GET /api/tasks/{task_id}/diff、GET /api/tasks/{task_id}/recovery-preview、POST /api/tasks/{task_id}/relocate 和 POST /api/tasks/{task_id}/recover 处理。

action 和 instruction 都是自由文本。这个仓库里常见的 action 名称有 rewrite、translate、summarize、extract 和 fix。