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
- `main` 分支只做校验，用 `v0.1.0` 这类 Git tag 发布正式镜像。
- 工作流直接使用内置 `GITHUB_TOKEN` 登录 GHCR，不需要额外配置镜像仓库密钥。

工作流行为：

- Pull Request 只做测试与 Docker 构建校验，不会推送镜像。
- 推送到 `main` 时只做测试与 Docker 构建校验，不会推送镜像。
- 推送 `v0.1.0` 这类版本标签时会向 GHCR 发布对应的 semver 标签。
- 手动触发时可以发布自定义标签，并可选择是否同时刷新 `latest`。
- 每次真正发布后，工作流都会按 digest 拉取已发布镜像，并实际启动一次容器做 smoke test。

首次发布成功后，镜像地址为：

```text
ghcr.io/<owner>/<repository>:latest
```

使用示例：

```bash
docker pull ghcr.io/<owner>/<repository>:latest
docker run --rm -p 8000:8000 --env-file .env ghcr.io/<owner>/<repository>:latest
```

推荐发布流程：

```bash
git tag v0.1.0
git push origin v0.1.0
```

`latest` 标签如何同步：

- 推送 `v0.1.0` 这类正式版本标签时，会同时更新 semver 标签和 `latest`。
- 手动触发发布时，默认不会更新 `latest`；只有显式把 `publish_latest` 设为 `true` 才会同步。
- 如果你想在不改 semver 版本标签的前提下，把 `latest` 指向一份已经验证过的构建，可以手动触发工作流，填写一个维护用标签，并勾选 `publish_latest`。

手动发布更适合少数例外场景，例如对同一份代码补发一个明确的维护标签。

如果包保持 private，使用者仍可先用带有 `read:packages` 权限的 GitHub Personal Access Token 登录后再拉取。

本地运行已发布镜像

可以用环境变量 `IMAGE_TAG` 覆盖默认镜像标签（或在 `.env` 中设置）。示例：

```bash
# 拉取指定标签（默认 latest）
IMAGE_TAG=v0.1.0 docker compose pull

# 启动服务
IMAGE_TAG=v0.1.0 docker compose up -d

# 查看日志
docker compose logs -f

# 停止并移除
docker compose down
```

注意：

- 如果仓库包是私有的，`docker compose pull` 需要验证，先用带有 `read:packages` 权限的 Personal Access Token 登录 `ghcr.io`。
- 默认 `docker-compose.yml` 使用 `ghcr.io/gy-ge/agentdocs:${IMAGE_TAG:-latest}`，不设置 `IMAGE_TAG` 将拉取 `latest`。

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

仓库现在包含基于 Playwright 的浏览器端到端测试，用于覆盖静态工作台的关键交互。

首次运行前先安装 Chromium 运行时：

```bash
uv run python -m playwright install chromium
```

执行浏览器 E2E：

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

## 当前状态

目前实现包含：

- 文档列表、创建、更新、删除、版本历史与回滚
- 任务 create、next、complete、accept、reject、cancel、retry、diff、relocate、recovery preview 与 recover
- 批量 accept-ready 与文档级 stale cleanup
- 持久化任务模板与文档默认任务设置
- Word 风格浏览器工作台：行内审阅浮窗、选区快捷工具栏、评论栏、底部折叠抽屉、审阅徽章与键盘快捷键
- 覆盖 API 流程、迁移和模拟 Agent 的集成测试

## 建议后续顺序

1. 继续补 stale recovery 和批量接受边界场景的回归测试。
2. 继续压缩浏览器端高频任务审核路径。
3. 每次接口字段或任务状态变更后，同步更新 README 与 docs。