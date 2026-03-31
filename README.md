# AgentDocs

一个面向个人项目的极简 Markdown 协作服务。

当前仓库包含三类内容：

- 方案文档
- API 契约
- 最小 FastAPI 项目骨架

## 目标范围

- 单用户
- 单外部 Agent
- SQLite 持久化
- Markdown 文档编辑
- 局部 AI 任务创建与回写
- 人工 accept 或 reject
- 文档版本回滚

## 目录

- app: 后端代码骨架
- docs: 设计文档和 API 契约
- data: SQLite 数据目录

## 启动方式

```powershell
uv sync
uv run uvicorn app.main:app --reload
```

如果需要继续兼容传统安装方式，也可以保留并使用 requirements.txt，但后续以 pyproject.toml 和 uv.lock 为准。

## 当前状态

当前骨架只提供：

- 应用入口
- 配置加载
- 数据模型草图
- 路由占位
- 服务层占位

后续建议先实现 documents 与 tasks 的 service 层，再补数据库迁移和测试。