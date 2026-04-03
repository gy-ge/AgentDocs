# AgentDocs 优化方案

> 基于对项目全部 API 端点（Documents/Tasks/Versions/Templates 共 25+ 个端点）、服务层（4 大 Service、60+ 函数）、UI（单体 HTML 2897 行 + CSS 1588 行、140+ JS 函数）的全面审查后编写。

---

## 第一部分：API 与 UI 配合现状诊断

### 1.1 架构总览

| 层次 | 技术 | 规模 |
|------|------|------|
| 后端 | FastAPI + SQLAlchemy + SQLite | 25+ REST 端点 |
| 前端 | 单体 Vanilla JS SPA | 2897 行 HTML（含 JS）+ 1588 行 CSS |
| 实时通信 | SSE (Server-Sent Events) + 轮询降级 | `/api/tasks/events` |
| 认证 | Bearer Token | localStorage 存储 |

### 1.2 当前 API-UI 匹配度分析

#### ✅ 匹配良好的部分

1. **乐观锁机制**：API 的 `expected_revision` + UI 的冲突检测 + "载入最新版本/保留本地草稿" 对话框，链路完整。
2. **SSE 实时同步**：后端 `/api/tasks/events` 推送 → 前端 `handleTaskEvent()` 消费 → 150ms 批量去抖，设计合理。
3. **任务状态机**：`pending → processing → done/failed → accepted/rejected/cancelled`，API 与 UI 的状态映射一致。
4. **国际化**：400+ 翻译键覆盖中英文，UI 无硬编码文案。
5. **版本回滚**：API 提供 `rollback` + UI 展示里程碑/常规快照分层，功能完整。

#### ⚠️ 存在不合理/可优化的部分

| 编号 | 问题 | 影响 | 涉及端 |
|------|------|------|--------|
| P1 | **布局：侧边栏承载过重** — 右侧同时放置了"审阅创建"(Review Composer)、"审阅批注"(Review Comments)、"版本历史"三个面板，信息密度过高，尤其移动端/窄屏下三面板堆叠成一长列 | UX 效率下降，用户需频繁滚动 | UI |
| P2 | **编辑/审阅模式切换断裂** — Review 模式是纯只读渲染面；Edit 模式是纯 textarea；两者完全互斥，用户在审阅中想微调文字必须切回 Edit 模式，上下文丢失 | 工作流中断，不符合 Word 的"边审阅边编辑"体验 | UI |
| P3 | **任务创建流程偏重** — 创建一个任务需要：①在 editor 选中文本 → ②到右侧 Composer 选 action → ③选 template → ④写 instruction → ⑤点 Create，步骤过多 | 创建效率低 | UI |
| P4 | **批注卡片信息冗余** — 每张 task-comment-card 同时显示 ID、action、block、offset、source、result、status、操作按钮，展开后内容过长 | 视觉噪音，关键信息被淹没 | UI |
| P5 | **Diff 展示分散** — 任务详情面板的 Diff 和审阅层的 inline mark 是两套独立渲染路径，用户需要在两处反复切换才能完整理解变更 | 认知负担 | UI + API(`/diff`) |
| P6 | **API 未提供批量 Diff** — 当多个 done 任务需要审阅时，只能逐个 `GET /api/tasks/{id}/diff`；`accept-ready-preview` 只返回分类列表不含 diff 内容 | 审阅效率低 | API |
| P7 | **任务列表排序不够灵活** — API `GET /api/tasks` 只按 `created_at ASC` 返回；UI 自行倒序显示；缺少按 offset 排序（即"文档中出现位置"排序），而这是批注模式最自然的排序 | 批注视觉关联弱 | API + UI |
| P8 | **Batch Accept 入口隐蔽** — `accept-ready` 批量接受功能在 UI 中只有一个 "Batch Accept Mergeable Results" 按钮文案，没有预览确认步骤 | 误操作风险 | UI |
| P9 | **单体 HTML 文件** — 2897 行含 JS/i18n/HTML 的单文件，所有 state 和函数挂在全局作用域，维护和扩展困难 | 技术债 | UI |
| P10 | **审阅层不支持 Markdown 渲染** — review-surface 用 `pre-wrap` 显示原始 markdown 文本+高亮 span，不渲染为富文本，阅读体验粗糙 | 与 Word 审阅体验差距大 | UI |
| P11 | **Task Defaults 设置入口缺失** — API 有 `POST /api/docs/{id}/task-defaults` 设置文档级默认 action/instruction，但 UI 中没有专门入口，仅在创建任务时隐式保存 | 功能可发现性差 | UI |
| P12 | **Recovery 流程过于技术化** — "relocate"/"requeue_from_current"/"recovery-preview" 等概念对普通用户不友好，UI 直接暴露了 API 的内部术语 | 理解门槛高 | UI |

### 1.3 优化方向汇总

| 优化方向 | 关键目标 | 是否需要改 API |
|----------|----------|----------------|
| A. **布局重组** | 精简侧边栏，让核心区域更聚焦 | ❌ |
| B. **统一审阅体验** | 向 Word 批注/审阅模式靠拢 | ❌ |
| C. **简化任务创建** | 减少步骤，支持右键/浮动菜单 | ❌ |
| D. **优化批注卡片** | 信息分层，降低视觉噪音 | ❌ |
| E. **增强 Diff 展示** | 统一 inline + sidebar Diff 展示 | 可选 |
| F. **代码拆分** | 单体 HTML 拆分为模块化结构 | ❌ |

---

## 第二部分：UI 向 Word 批注/审阅模式靠拢的具体方案

### 2.1 设计目标

参照 Microsoft Word 的 **Track Changes + Comments** 模式：

1. **正文为主**：文档内容始终占据最大面积，批注/修订不喧宾夺主
2. **inline 修订标记**：删除线(红色) + 插入(绿色/下划线) 直接嵌在正文流中
3. **右侧批注轨(Comment Rail)**：窄栏，只显示与正文行对齐的批注气泡
4. **操作就近(Accept/Reject)**：在 inline 标记上悬停/点击即可接受/拒绝，不需要跳到别处
5. **编辑与审阅共存**：审阅模式下仍可编辑未标记的文本区域

### 2.2 方案总览（不改 API）

```
┌──────────────────────────────────────────────────────────────────────┐
│  ┌─ 顶部工具栏 ──────────────────────────────────────────────────┐  │
│  │ [文档选择 ▼] [Title Input] [Save] [Export] [Edit|审阅] [⚙]   │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ┌─── 正文区(占 70%-75%) ────────┐  ┌── 批注轨(占 25%-30%) ──┐  │
│  │                                │  │                          │  │
│  │  # Heading 1                  │  │  ┌──────────────────┐    │  │
│  │                                │  │  │ #12 rewrite      │    │  │
│  │  这段话需要~~被改写的原文~~    │──│──│ "建议文案..."     │    │  │
│  │  [插入的新文案]                │  │  │ [✓接受] [✗拒绝]  │    │  │
│  │                                │  │  └──────────────────┘    │  │
│  │  正常文本继续...              │  │                          │  │
│  │                                │  │  ┌──────────────────┐    │  │
│  │  另一段~~原文~~[建议]         │──│──│ #15 translate     │    │  │
│  │                                │  │  │ [✓] [✗] [↻重试]  │    │  │
│  │                                │  │  └──────────────────┘    │  │
│  │                                │  │                          │  │
│  │                                │  │  ┌──────────────────┐    │  │
│  │  [待处理的选区]               │──│──│ #18 expand ⏳     │    │  │
│  │                                │  │  │ 处理中...         │    │  │
│  │                                │  │  └──────────────────┘    │  │
│  │                                │  │                          │  │
│  └────────────────────────────────┘  └──────────────────────────┘  │
│                                                                      │
│  ┌─ 底部折叠区 ─────────────────────────────────────────────────┐  │
│  │ [创建任务面板(折叠)] [版本历史(折叠)] [连接/同步状态]          │  │
│  └───────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
```

### 2.3 具体执行方案

---

#### 方案 A：布局重组 — 将"审阅创建"从侧边栏提取为浮动面板

**现状**：右侧 sidebar 包含三个面板(Review Composer / Review Comments / Version History)，上下堆叠

**改造**：

1. **Review Composer → 底部折叠抽屉(Drawer) 或浮动面板(Floating Panel)**
   - 默认收起，只显示一个"+ 新建任务"按钮
   - 点击/选中文本后自动展开创建面板
   - 放在正文区底部或作为 overlay，不占侧边栏空间

2. **Version History → 底部折叠区或独立弹窗**
   - 版本历史使用频率低，不应常驻侧边栏
   - 改为底部工具栏的一个折叠 `<details>` 或点击弹出 Modal

3. **侧边栏只保留批注轨(Comment Rail)**
   - sidebar 宽度从 380px 缩减到 280-300px
   - 只放置与正文对齐的批注气泡卡片

**CSS 改动要点**：
```
.workspace → grid-template-columns: 1fr 280px (原 380px)
新增 .task-drawer (底部抽屉组件)
.version-panel → 移出 sidebar，放入底部折叠区或 modal
```

**不需要改 API**：仅重新组织 HTML 结构和 CSS 布局。

---

#### 方案 B：统一审阅体验 — 正文 Inline 修订标记 + 就近操作

**现状**：
- Review 模式下，`buildReviewMarkup()` 已在正文中渲染 `<span class="review-mark--delete">` 和 `review-mark--insert`
- 但点击标记只能触发 `selectTask()`，必须到右侧面板才能 Accept/Reject
- 编辑和审阅互斥

**改造**：

1. **Inline 操作浮层(Inline Action Popover)**
   - 在审阅层中，点击一个已完成(done)的修订标记时，在标记正上方弹出微型操作浮层：
     ```
     ┌──────────────────────┐
     │ [✓ 接受] [✗ 拒绝]   │
     │ [↻ 重试] [查看详情]  │
     └──────────────────────┘
     ```
   - 使用 `position: absolute` 相对于被点击的 `<span>` 定位
   - 点击浮层外部或按 Esc 关闭
   - 操作后自动关闭浮层并刷新视图

2. **增强 Inline 修订标记的视觉效果**
   - `done` 状态且 `result ≠ source` 时，显示红色删除线原文 + 绿色插入文本（保持现有逻辑）
   - 增加悬停效果：鼠标移入时高亮背景 + 显示工具提示（tooltip）显示 action 类型
   - `pending/processing` 状态：蓝色/橙色波浪下划线 + 旋转图标
   - `accepted` 状态：绿色背景渐隐（表示已合并）

3. **批注轨与正文联动**
   - 右侧批注气泡根据对应文本在正文中的位置动态调整 `top` 值
   - 使用 `document.querySelector('[data-review-task-id="N"]')` 获取正文中标记位置
   - 批注气泡与标记之间绘制连接线（可选，用 CSS `::before` 伪元素或 SVG）

**实现方式**：
- 修改 `buildReviewMarkup()` 函数，为 done 状态任务的标记增加 `data-can-accept="true"` 属性
- 新增 `showInlinePopover(taskId, anchorElement)` 函数
- 在 `renderEditorTaskMarkers()` 的事件绑定中，增加浮层弹出逻辑
- 新增 CSS 组件：`.inline-popover`

**不需要改 API**：所有操作（accept/reject/retry）仍调用现有端点。

---

#### 方案 C：简化任务创建 — 选中文本后右键/浮动菜单一键创建

**现状**：选中文本 → 查看右侧 Composer → 选 action → 选 template → 写 instruction → 点 Create（5步）

**改造**：

1. **选中文本后自动弹出快捷菜单**
   - 在 `doc-body` textarea 的 `mouseup` 事件中检测是否有选区
   - 如果有选区，在选区附近弹出一个浮动工具栏：
     ```
     ┌──────────────────────────────────────┐
     │ [✏ 改写] [📝 摘要] [📖 展开] [🌐 翻译] │
     └──────────────────────────────────────┘
     ```
   - 点击即用文档默认 instruction 创建任务（一步完成）
   - 长按或右键可展开完整创建面板（高级模式）

2. **Review 模式下也支持选中创建**
   - 审阅层中未标记的文本区域允许选中
   - 选中后同样弹出快捷菜单
   - 实现：在 `review-surface-content` 上监听 `mouseup`，用 `window.getSelection()` 获取选区范围，通过 `Range.startOffset` 计算对应的 markdown offset

3. **保留高级创建面板**
   - 底部 Drawer 或折叠面板中保留完整的 action/template/instruction 输入
   - 用于需要自定义 instruction 的场景

**不需要改 API**：创建任务仍调用 `POST /api/docs/{id}/tasks`。

---

#### 方案 D：优化批注卡片 — 三级信息折叠

**现状**：每张卡片一次性展示所有信息（ID、action、block、offset、source、result、status、按钮），展开后很长

**改造**：参照 Word 的 Comment Bubble 设计

1. **Level 0 — 折叠态（默认）**
   ```
   ┌─────────────────────────┐
   │ ✏ 改写 · §Introduction │
   │ "建议文案前50字..."     │
   └─────────────────────────┘
   ```
   - 只显示：action 图标 + action 名 + 所在 heading + 结果摘要（50字）
   - 左侧色条表示状态（绿=done、蓝=pending、红=failed）
   - 高度约 48-56px

2. **Level 1 — 半展开态（单击）**
   ```
   ┌─────────────────────────┐
   │ ✏ 改写 · §Introduction │ ← 标题行
   │ ─────────────────────── │
   │ 原文: "这段话..."       │ ← 原文摘要
   │ 建议: "修改后的..."     │ ← 结果摘要
   │ [✓ 接受] [✗ 拒绝]      │ ← 主要操作
   └─────────────────────────┘
   ```
   - 显示原文/结果摘要（100字截断）+ 主要操作按钮
   - 不显示 offset/revision/metadata 等技术细节

3. **Level 2 — 完全展开态（点击"详情"）**
   - 显示完整 diff、元数据、recovery 选项
   - 技术用户的高级面板

**不需要改 API**：纯 UI 渲染逻辑调整。

---

#### 方案 E：增强 Diff 展示 — 在批注气泡中内联 Diff

**现状**：diff 内容只在底部 `task-detail-panel` 中显示，需要选中任务才能查看

**改造**：

1. **在批注卡片的 Level 1 中直接嵌入 mini-diff**
   - 用两行对比显示（红色删除 + 绿色插入），类似 Word 的 Track Changes 气泡
   - 不显示 unified diff 格式，使用更直观的富文本对比

2. **保留底部 Diff Detail 面板**
   - 作为 Level 2 的详细视图
   - 需要逐字对比时使用

3. **（可选 API 优化）批量 Diff 端点**
   - 新增 `GET /api/docs/{doc_id}/tasks/diffs?status=done` 一次性返回所有 done 任务的 diff
   - 减少 UI 逐个请求的开销
   - **注意**：此项是唯一可能需要新增 API 的点，但也可以通过前端在加载任务列表后批量请求现有 diff 端点来替代

**不需要改 API**（前端可并行请求多个 `/tasks/{id}/diff`）。

---

#### 方案 F：代码重构 — 从单体 HTML 拆分为模块结构

**现状**：index.html 是 2897 行的单体文件，包含 HTML + JS + i18n

**改造**（可渐进式执行）：

1. **Phase 1：提取 JS**
   - `app/static/js/i18n.js` — 翻译数据和 `t()` 函数
   - `app/static/js/state.js` — 全局状态对象
   - `app/static/js/api.js` — 所有 API 调用函数
   - `app/static/js/app.js` — 主逻辑（事件绑定、渲染）
   - 使用 ES Module (`<script type="module">`) 导入

2. **Phase 2：提取 HTML 片段**
   - 利用 `<template>` 标签将卡片/弹窗等复用组件模板化
   - 减少 `innerHTML` 拼接的硬编码 HTML 字符串

3. **Phase 3：引入轻量框架（可选）**
   - 如 Alpine.js 或 Preact，降低手动 DOM 操作的复杂度
   - 但考虑到项目"无依赖"的特点，此步为可选

**不需要改 API**。

---

### 2.4 其余 UI 微调清单

| 编号 | 优化项 | 具体做法 | 优先级 |
|------|--------|----------|--------|
| U1 | **状态色条** | 在每张批注卡片左侧加 3px 色条（绿/蓝/橙/红）代替文字状态标签 | 高 |
| U2 | **Tooltip** | 审阅层标记悬停时显示 action + status 的简洁 tooltip | 高 |
| U3 | **Recovery 术语友好化** | "relocate"→"同步定位"、"requeue_from_current"→"基于当前重建"（已有中文翻译，但 UI 按钮仍显示英文术语） | 中 |
| U4 | **键盘快捷键** | `Ctrl+Shift+A` 接受当前任务、`Ctrl+Shift+R` 拒绝、`Tab` 在批注间导航 | 中 |
| U5 | **批注数量徽章** | 在 Review 按钮旁显示待审阅数量（done 状态任务数） | 高 |
| U6 | **正文 Markdown 预览** | 审阅层支持基础 Markdown 渲染（标题/粗体/斜体/列表），而非纯 pre-wrap | 低 |
| U7 | **Document Defaults 入口** | 在文档设置区域添加"默认 Action/Instruction"设置入口 | 中 |
| U8 | **响应式批注轨** | 窄屏下批注轨变为底部抽屉而非堆叠在正文下方 | 中 |

---

### 2.5 实施优先级与路线图

```
Phase 1（高优先级 / 立即可做 / 不改 API）
├── A. 布局重组（sidebar 瘦身 + composer 移至底部）
├── B. Inline Action Popover（点击标记弹出接受/拒绝）
├── D. 批注卡片三级折叠
└── U1/U2/U5 微调

Phase 2（中优先级 / 需要较多 JS 改动 / 不改 API）
├── C. 选中文本快捷菜单
├── E. 批注卡片内联 mini-diff
├── U3/U4/U7/U8 微调
└── Version History 移至 Modal

Phase 3（低优先级 / 可选 / 渐进式）
├── F. 代码拆分 JS 模块化
├── U6. Markdown 渲染（考虑引入 marked.js 等轻量库）
└── （可选）批量 Diff API 端点
```

---

### 2.6 改动影响评估

| 改动项 | 影响的文件 | 是否破坏现有 API | 是否影响现有测试 |
|--------|-----------|----------------|----------------|
| 布局重组 | index.html, index.css | ❌ | ❌ |
| Inline Popover | index.html (JS部分), index.css | ❌ | ❌ |
| 批注卡片优化 | index.html (JS部分), index.css | ❌ | ❌ |
| 选中快捷菜单 | index.html (JS部分), index.css | ❌ | ❌ |
| 内联 Diff | index.html (JS部分), index.css | ❌ | ❌ |
| 代码拆分 | 新建多个 JS 文件, 修改 index.html | ❌ | ❌ |
| 批量 Diff API | 新增 API 端点（可选） | 新增，不破坏现有 | 需新增测试 |

**总结**：所有 Phase 1 和 Phase 2 的改动都不需要修改后端 API，只涉及前端 HTML/CSS/JS 的调整。现有的 25+ 个 API 端点已足够支撑更优的 UI 体验。

---

## 第三部分：针对发现的 API 不合理之处的建议（仅建议，非必需）

以下是审查 API 时发现的可选优化点，均为**不影响前端核心改造**的增量改进：

| 编号 | 建议 | 说明 |
|------|------|------|
| API-1 | `GET /api/tasks` 增加 `sort` 参数 | 支持 `sort=offset` 按文档位置排序，方便批注轨按位置对齐 |
| API-2 | `accept-ready-preview` 返回 diff 摘要 | 在预览结果中包含每个任务的 source/result 摘要，减少 UI 额外请求 |
| API-3 | 新增 `GET /api/docs/{id}/tasks/diffs` | 批量返回指定文档所有 done 任务的 diff，减少网络请求 |
| API-4 | SSE 事件携带更多 payload | 如 `task.changed` 事件直接携带 task 对象摘要，减少 UI 回查 |
| API-5 | `POST /api/docs/{id}/tasks` 支持批量创建 | 一次选区可同时对多个 action（如改写+翻译）创建任务 |

> 以上 API 建议均为可选增量，不阻塞 UI 优化的执行。
