# AgentDocs

AgentDocs 是一个面向单个作者与单个外部 Agent 工作流的极简 Markdown 协作服务。后端使用 FastAPI 和 SQLite，前端是单文件静态工作台；Markdown block 只在读取时解析，不会作为独立真源持久化。

[架构说明](docs/architecture_zh.md) | [API 契约](docs/api_contract_zh.md) | [English README](README.md)

## 当前范围

当前已经实现：

- 带 revision 乐观并发校验的文档 CRUD
- 基于 Markdown 选区的单 block 任务创建
- 通过 REST API 完成 Agent 领取与回写
- 人工 accept、reject、cancel、retry 与 rollback
- 任务 diff 预览、stale 检测、stale 清理、重定位与按当前正文重建
- 服务端持久化任务模板与文档级默认任务设置
- 最小浏览器工作台与本地模拟 Agent 脚本

当前明确不做：

- 内置 LLM 推理
- 多用户账户或复杂权限系统
- WebSocket 或 SSE 推送
- 无人工确认的自动应用结果
- 持久化 block 表
- lease、heartbeat、claim token 一类任务协议

## 环境要求

- Python 3.14+
- uv

## 安装

安装依赖：

```bash
uv sync
```

创建环境变量文件：

```bash
cp .env.example .env
```

.env.example 默认值：

- APP_NAME=AgentDocs
- APP_ENV=development
- API_KEY=change-me
- SQLITE_PATH=data/doc.db

## 运行

启动前先执行迁移：

```bash
uv run alembic upgrade head
```

启动后端：

```bash
uv run uvicorn app.main:app --reload
```

然后访问 http://127.0.0.1:8000。

## Docker 部署

先创建环境变量文件：

```bash
cp .env.example .env
```

构建并启动容器：

```bash
docker compose up --build -d
```

容器入口会在启动 Uvicorn 之前自动执行 `alembic upgrade head`。

第一次打开 http://127.0.0.1:8000 时，需要在浏览器弹出的连接设置里输入 `.env` 中的共享 API Key。按默认示例配置，这个值是 `change-me`。

常用命令：

```bash
docker compose logs -f
docker compose ps
docker compose down
```

SQLite 数据库会持久化在名为 `agentdocs-data` 的 Docker volume 中，并挂载到容器内的 `/app/data`。

如果代码或依赖有变化，需要重新构建：

```bash
docker compose up --build -d
```

## GitHub Container Registry 发布

仓库现在包含 [docker-publish.yml](.github/workflows/docker-publish.yml)，会把镜像发布到 GitHub Container Registry，而不是 Docker Hub。

推荐做法：

- 如果希望任何人都能直接 `docker pull`，请在 GitHub Packages 中把这个包设为 public。
- 用 `main` 分支持续发布滚动镜像，用 `v0.1.0` 这类 Git tag 发布不可变版本。
- 工作流直接使用内置 `GITHUB_TOKEN` 登录 GHCR，不需要额外配置镜像仓库密钥。

工作流行为：

- Pull Request 只做测试与镜像构建，不会推送镜像。
- 推送到 `main` 时会发布 `latest`、`main` 和 `sha-<commit>` 等滚动标签。
- 推送 `v0.1.0` 这类版本标签时会发布对应的 semver 标签。

首次发布成功后，镜像地址为：

```text
ghcr.io/<owner>/<repository>:latest
```

使用示例：

```bash
docker pull ghcr.io/<owner>/<repository>:latest
docker run --rm -p 8000:8000 --env-file .env ghcr.io/<owner>/<repository>:latest
```

如果包保持 private，使用者仍可先用带有 `read:packages` 权限的 GitHub Personal Access Token 登录后再拉取。

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

## 当前状态

目前实现包含：

- 文档列表、创建、更新、删除、版本历史与回滚
- 任务 create、next、complete、accept、reject、cancel、retry、diff、relocate、recovery preview 与 recover
- 批量 accept-ready 与文档级 stale cleanup
- 持久化任务模板与文档默认任务设置
- 覆盖 API 流程、迁移和模拟 Agent 的集成测试

## 建议后续顺序

1. 继续补 stale recovery 和批量接受边界场景的回归测试。
2. 继续压缩浏览器端高频任务审核路径。
3. 每次接口字段或任务状态变更后，同步更新 README 与 docs。