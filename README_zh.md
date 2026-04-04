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

你可以在仓库根目录运行，也可以只拿这一份 compose 文件到一个全新的空目录里运行；不要求先检出完整源码仓库。

### 最小独立部署步骤

macOS 或 Linux：

```bash
mkdir agentdocs
cd agentdocs
cp /path/to/docker-compose.yml .
docker compose up -d
```

Windows PowerShell：

```powershell
New-Item -ItemType Directory agentdocs | Out-Null
Set-Location agentdocs
Copy-Item C:/path/to/docker-compose.yml ./docker-compose.yml
docker compose up -d
```

第一次启动只需要这些步骤。默认情况下，Docker 会拉取镜像、按需在 `docker-compose.yml` 同级创建本地 `data` 目录，并把服务发布到 8000 端口。

把 [docker-compose.yml](docker-compose.yml) 放到目标目录后，执行：

```bash
docker compose up -d
```

这份 compose 文件默认拉取已经发布到 GHCR 的镜像。它不会把 `.env` 文件挂载进容器；真正的行为是：Docker Compose 会读取与 `docker-compose.yml` 同目录下可选的 `.env` 文件，用其中的值替换变量后，再把结果作为容器环境变量注入进去。

compose 还设置了 `pull_policy: always`，因此每次执行 `docker compose up -d` 时都会先检查对应标签是否有更新镜像。

如果你想覆盖默认值，可以在 `docker-compose.yml` 同目录创建一个 `.env`，内容示例：

```dotenv
IMAGE_TAG=latest
AGENTDOCS_PORT=8000
APP_NAME=AgentDocs
API_KEY=change-me
SQLITE_PATH=/app/data/doc.db
```

如果不创建 `.env`，compose 也可以直接用内置默认值启动。

首次部署时，最关键的默认值是：

- `AGENTDOCS_PORT=8000`
- `API_KEY=change-me`
- `SQLITE_PATH=/app/data/doc.db`

由于当前应用并不会使用 `APP_ENV` 切换运行行为，所以它已经从发布版 compose 路径中移除。如果你本地旧的 `.env` 里还保留了 `APP_ENV`，可以直接删掉。

容器入口会在启动 Uvicorn 之前自动执行 `alembic upgrade head`。

第一次打开 http://127.0.0.1:8000 时，需要在浏览器弹出的连接设置里输入 compose 环境里的共享 API Key。默认值是 `change-me`。

常用命令：

```bash
docker compose logs -f
docker compose ps
docker compose down
```

SQLite 数据库会持久化在 [docker-compose.yml](docker-compose.yml) 同级的 `data` 目录中。这个目录在容器内挂载为 `/app/data`。compose 默认把 `SQLITE_PATH` 设为 `/app/data/doc.db`，因此宿主机上的数据库文件就是 `./data/doc.db`。

如果你要自定义 `SQLITE_PATH`，除非你明确想脱离宿主机侧的 `data` 目录，否则应当继续放在 `/app/data` 下面。

这样备份也会简单很多：如果你想要安静备份，先停掉服务，然后直接复制本地 `data` 目录即可。

## 启动排查

- 如果 `uv sync` 提示当前 Python 版本不满足要求，先执行 `uv python install 3.10`，然后重新运行 `uv sync`。
- 如果你自定义了 `SQLITE_PATH`，请确保该路径的父目录可写；当前默认配置会自动创建缺失目录，但不会绕过权限问题。
- 如果 8000 端口已被占用，可以在 compose 侧 `.env` 中设置 `AGENTDOCS_PORT=8080` 一类的值，然后改用对应端口访问。
- 如果你的 Docker 环境没有自动创建可写的 `data` 目录，请先在 `docker-compose.yml` 同级手工创建该目录，再执行 `docker compose up -d`。
- 如果浏览器能打开页面但 API 请求返回 401，请在连接设置里填写 compose 侧 `.env` 或当前 shell 环境中设置的 `API_KEY`，默认值是 `change-me`。

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

如果你希望使用这套协议对应的已发布 AgentDocs 集成 skill 包，可查看 [skills/agentdocs-integration/SKILL.md](skills/agentdocs-integration/SKILL.md)。其中附带了可直接做 HTTP 联调的示例客户端：[skills/agentdocs-integration/scripts/agentdocs_skill_client.py](skills/agentdocs-integration/scripts/agentdocs_skill_client.py)。