# AI 标注式 Markdown 协作方案 v2

> 日期：2026-03-31
> 状态：可直接进入编码准备

---

## 一、目标

这是一个部署在 VPS 上的单用户 Markdown 协作服务，用于你和一个外部 Agent 协同处理文档中的局部改写任务。

系统职责：

- 提供 Markdown 文档编辑、任务创建、任务回写、人工确认、版本回滚
- 只负责存储、状态流转、冲突检测和实时通知
- 不内置 LLM，不承担模型推理

明确前提：

- 个人项目
- 单个浏览器使用者
- 单个外部 Agent 进程
- 不引入复杂权限管理、用户系统、角色系统

---

## 二、设计结论

为了让后续代码生成稳定，这一版有四个关键收敛：

1. 文档唯一真源是完整 Markdown，不是 blocks
2. 第一版任务只允许落在单个 block 内，不支持跨标题任务
3. 浏览器编辑和 Agent 回写都必须走 revision 冲突控制
4. 任务采用 claim 协议，避免重复处理和脏写

---

## 三、系统边界

### 浏览器负责

- 编辑 Markdown
- 插入 AI 标记
- 创建任务
- 查看任务结果
- accept 或 reject
- 查看版本与回滚

### VPS 服务负责

- 存储文档与任务
- 解析 Markdown 生成 blocks 视图
- 保存版本快照
- 维护任务状态机
- 校验 revision 和文本锚点
- 推送事件给前端

### 外部 Agent 负责

- 轮询或 claim 待处理任务
- 调用自己的 LLM
- 写回 result 或 error

---

## 四、架构

```text
浏览器 SPA
  <-> FastAPI REST
  <-> FastAPI WebSocket
  <-> SQLite (WAL)

外部 Agent
  <-> FastAPI REST
```

约束说明：

- WebSocket 只做通知，不承载核心写操作
- SQLite 足够覆盖当前单用户场景
- 不引入消息队列、后台 worker、缓存层

---

## 五、核心模型

### 1. Document

文档真源保存为完整 Markdown。

核心字段：

- id
- title
- raw_markdown
- revision
- created_at
- updated_at

### 2. Block

block 是从 raw_markdown 派生出来的结构化视图，不是持久化真源。

核心字段：

- id
- doc_id
- heading
- level
- position
- start_offset
- end_offset
- content

### 3. Task

任务必须绑定文本锚点，不能只绑定 block_id。

核心字段：

- id
- doc_id
- block_id
- doc_revision
- start_offset
- end_offset
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

### 4. Version

每次文档正文变化都生成快照，支持回滚。

核心字段：

- id
- doc_id
- revision
- snapshot
- actor
- note
- created_at

---

## 六、Markdown 标记规则

保留包裹式标记语法：

```markdown
<!-- @ai:rewrite 用学术中文重写 -->
待处理内容
<!-- /ai -->
```

action 支持：

- summarize
- rewrite
- expand
- translate
- custom

规则：

1. 不允许嵌套
2. 第一版不允许跨 block
3. custom 必须带 instruction
4. auto_apply 只建议用于 summarize、translate 这类低风险任务
5. 前端创建任务后，应把标记从正文中移除，只保留纯 Markdown 与任务记录

原因：

- 避免标记长期污染正文
- 避免 accept 或 reject 时二次解析标记导致错位

---

## 七、任务状态机

第一版采用以下状态：

- pending: 已创建，待 Agent 领取
- claimed: Agent 已领取
- processing: Agent 处理中
- done: 已写回结果，待人工确认或自动合并
- accepted: 结果已合并入正文
- rejected: 结果被人工拒绝
- failed: Agent 处理失败
- conflict: 结果已产出，但无法安全合并
- cancelled: 任务被取消

状态约束：

- pending 只能进入 claimed 或 cancelled
- claimed 只能进入 processing、pending 或 cancelled
- processing 只能进入 done 或 failed
- done 只能进入 accepted、rejected 或 conflict
- accepted、rejected、cancelled 为终态

---

## 八、revision 与冲突控制

虽然是个人项目，但仍然有两个写入方：

- 浏览器编辑正文
- Agent 回写任务结果

因此必须有最基本的并发保护。

规则：

1. documents.revision 每次正文变化加 1
2. 所有修改文档正文的接口都必须提交 expected_revision
3. accept 或 auto_apply 前必须重新校验任务锚点
4. 锚点不匹配时，任务进入 conflict，不做静默覆盖

accept 合并条件：

- 当前 revision 与任务创建时可对齐，或仍能精确定位 source_text
- 当前目标区间的 hash 与 source_hash 一致

reject 规则：

- 默认只更新任务状态为 rejected
- 只有能确认当前正文正是该任务的合并结果时，才执行反向替换

---

## 九、Agent 协议

不要让 Agent 直接扫描全部 pending 任务然后抢写。

采用简单 claim 机制：

1. Agent 调用 claim 接口原子领取任务
2. 服务端为任务写入 claim_token 和过期时间
3. Agent 处理期间可 heartbeat 续租
4. Agent complete 时必须提交 claim_token
5. claim 超时后任务可回到 pending

这个机制已经足够覆盖单 Agent 场景，也能防止脚本异常退出后任务永久挂死。

---

## 十、认证方案

这是个人项目，所以认证只保留最低复杂度：

- 一个共享 API Key
- 所有 HTTP 请求走 Authorization Header
- WebSocket 在连接后发送第一条 auth 消息完成校验

明确不做：

- 多用户
- RBAC
- JWT
- OAuth
- 细粒度权限控制

说明：

- 单 key 对个人项目足够
- 不要把 key 放在 URL 查询串里
- 前端可以暂存到本地，但只在 HTTPS 场景下使用

---

## 十一、API 轮廓

### 文档

- GET /api/docs
- POST /api/docs
- GET /api/docs/{doc_id}
- PUT /api/docs/{doc_id}
- DELETE /api/docs/{doc_id}
- GET /api/docs/{doc_id}/versions
- POST /api/docs/{doc_id}/versions/{version_id}/rollback

### 任务

- POST /api/docs/{doc_id}/tasks
- GET /api/tasks
- GET /api/tasks/{task_id}
- POST /api/tasks/claim
- POST /api/tasks/{task_id}/heartbeat
- POST /api/tasks/{task_id}/complete
- POST /api/tasks/{task_id}/accept
- POST /api/tasks/{task_id}/reject
- POST /api/tasks/{task_id}/cancel

### WebSocket

- GET /ws

推送事件类型：

- doc.updated
- task.created
- task.claimed
- task.completed
- task.accepted
- task.rejected
- task.conflict

---

## 十二、数据表建议

```sql
PRAGMA journal_mode = WAL;

CREATE TABLE documents (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        title        TEXT NOT NULL,
        raw_markdown TEXT NOT NULL DEFAULT '',
        revision     INTEGER NOT NULL DEFAULT 1,
        created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE blocks (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        doc_id       INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
        heading      TEXT NOT NULL DEFAULT '',
        level        INTEGER NOT NULL DEFAULT 0,
        position     INTEGER NOT NULL,
        start_offset INTEGER NOT NULL,
        end_offset   INTEGER NOT NULL,
        content      TEXT NOT NULL DEFAULT '',
        updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX idx_block_position ON blocks(doc_id, position);

CREATE TABLE tasks (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        doc_id           INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
        block_id         INTEGER NOT NULL REFERENCES blocks(id),
        doc_revision     INTEGER NOT NULL,
        start_offset     INTEGER NOT NULL,
        end_offset       INTEGER NOT NULL,
        source_text      TEXT NOT NULL,
        source_hash      TEXT NOT NULL,
        action           TEXT NOT NULL,
        instruction      TEXT,
        result           TEXT,
        result_hash      TEXT,
        status           TEXT NOT NULL DEFAULT 'pending',
        auto_apply       INTEGER NOT NULL DEFAULT 0,
        claimed_by       TEXT,
        claim_token      TEXT,
        claim_expires_at TIMESTAMP,
        attempt_count    INTEGER NOT NULL DEFAULT 0,
        error_message    TEXT,
        created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        done_at          TIMESTAMP,
        resolved_at      TIMESTAMP
);

CREATE TABLE doc_versions (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        doc_id      INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
        revision    INTEGER NOT NULL,
        snapshot    TEXT NOT NULL,
        actor       TEXT NOT NULL,
        note        TEXT,
        created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 十三、最小工作流

```text
1. 浏览器保存文档
2. 浏览器在 block 内创建任务
3. 服务端记录任务锚点并推送 task.created
4. Agent claim 任务
5. Agent 处理并 complete
6. 若 auto_apply 且校验通过，则自动合并并 accepted
7. 否则等待浏览器 accept 或 reject
8. 每次正文变化均生成版本快照
```

---

## 十四、第一版范围

必须做：

- 文档 CRUD
- Markdown 解析为 block 视图
- 任务创建
- task claim 与 complete
- accept 与 reject
- revision 冲突检测
- 版本快照与回滚
- WebSocket 通知

明确不做：

- 跨 block 任务
- 嵌套任务
- 多 Agent 竞争
- 自动重定位
- 复杂权限管理
- 内置模型调用

---

## 十五、实现顺序

推荐按以下顺序编码：

1. 配置与应用入口
2. SQLite 连接和模型
3. 文档 CRUD 与 revision
4. Markdown block 解析
5. 任务创建与 claim 协议
6. complete 和 accept 合并逻辑
7. 版本回滚
8. WebSocket 事件
9. 最小前端
