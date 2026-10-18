# T004：共用导航与首页壳（前端部分）

## 1. 任务信息

| 字段 | 内容 |
|---|---|
| 任务编号 | T004 |
| 类型 / 关联里程碑 | 开发任务 / M1（Task 08 前端子集） |
| 状态 | 已完成 |
| 创建日期 | 2026-10-18 |
| 开始日期 | 2026-10-18 |
| 最近更新 | 2026-10-18 |
| 完成日期 | 2026-10-18 |
| 最近回写 | 2026-10-18 |
| 总文档 | [master-plan.md](../master-plan.md) |
| 前置依赖 | T001 桌面脚手架；后端业务 RPC 未就绪（T002 只有 Task 01 脚手架） |
| 需求 / 设计 / 契约 | [M1 Task 08](../../superpowers/plans/2026-10-18-ai-workbench-m1-plan.md)、[UI 设计](../../product/2026-10-18-workbench-ui-design.md)、[PRD FR01/FR09](../../product/prd-ai-workbench-v1.md) |

编号说明：本任务最初误用 T003；同一时间后端工作流已建立 T003（SQLite/幂等写）。按 Skill 的“全局递增、不复用”规则，前端任务改号为 T004，后端 T003 文件未改动。

## 2. 目标与主线关系

补齐共用侧栏、页面路由、首页内容壳和统一空态/错误态，为 M1 Task 04～08 的业务页面提供稳定导航与布局基础。本任务只实现 Task 08 的导航/布局前端子集，不实现草稿 RPC 持久化，也不伪造资料、题库、面试或任务数据。

## 3. 范围与功能点

### 包含

| 功能点 | 计划行为与验收条件 | 状态 | 实际记录 |
|---|---|---|---|
| F01 共用侧栏与导航模型 | 新建任务、助理、专家 · 技能 · 连接器、定时任务、资料库、更多；任务/空间空态；设置入口；当前页 `aria-current` | 已完成 | [2026-10-18 F01](#2026-10-18-f01共用侧栏与导航模型) |
| F02 页面路由与统一空态 | 首页与占位页切换；更多/助理 hub；设置未配置状态；占位页明确里程碑，不展示伪造业务数据 | 已完成 | [2026-10-18 F02](#2026-10-18-f02页面路由占位页与空态) |
| F03 首页状态保持 | 切换页面/模块后保留未提交文字与办公/开发/设计选择；导航后焦点到页面标题 | 已完成 | [2026-10-18 F03](#2026-10-18-f03首页状态保持与焦点) |
| F04 键盘、响应式与测试 | 键盘可操作；1024 宽度无破坏性溢出；Playwright `@nav` 覆盖 | 已完成 | [2026-10-18 F04](#2026-10-18-f04测试响应式与回归) |

### 不包含

- `drafts.get/save`、800ms ACK、跨重启草稿恢复（Task 02/08 后端）。
- 真实工作区/资料读取、DeepSeek、题库、面试、报告、复习业务页面。
- 安装包、PyInstaller 服务包与真实云服务验证。

## 4. 实施步骤与验收

- [x] 确认 T001 基线与当前服务状态：后端 Task 01 已通过 57 项测试，业务 RPC 尚未实现。
- [x] 先写 `@nav` 失败测试并确认 Red：3 failed / 2 passed。
- [x] 实现导航模型、侧栏、页面路由、首页状态保持与占位页。
- [x] 执行 typecheck、构建、Playwright 与可访问性检查。
- [x] 回写本任务与总文档。

## 5. 开发记录

### 2026-10-18 F01：共用侧栏与导航模型

- **当次状态：**已完成。
- **实际行为：**侧栏提供新建任务、助理、专家 · 技能 · 连接器、定时任务、资料库、更多与设置入口；任务/空间显示真实的零条空态；当前页有 `aria-current="page"`。
- **实现与决策：**新增 `navigation.ts` 集中维护页面元数据；侧栏按钮由数据驱动；助理的 BETA 文字不参与可访问名称，使用 `aria-label` 保持名称稳定；没有把示例空间写进正式侧栏。
- **修改文件：**`apps/desktop/src/renderer/navigation.ts`、`components/Sidebar.tsx`、`components/Icon.tsx`。
- **验证：**`@nav exposes the shared sidebar...` 通过；`aria-current`、导航项可见性、资料库切换均被断言。
- **问题与处理：**BETA 徽标导致“助理”按钮的可访问名称不精确；通过 `aria-label` 修正。
- **下一步：**接入页面内容与占位页。

### 2026-10-18 F02：页面路由、占位页与空态

- **当次状态：**已完成。
- **实际行为：**首页与占位页可切换；更多页提供面试题库、AI 面试官、面试记录、复习清单、Agent 入口；助理页提供两个内置 Agent 入口；设置页显示模型/语音/MCP 的“未配置/未连接”状态；未接入页面明确写出所属里程碑。
- **实现与决策：**新增 `PlaceholderPage.tsx`，按 `PageId` 渲染统一空态；`MilestoneCard` 只写里程碑与说明，不展示伪造题目或统计；工作区页明确“尚未连接工作区”；更多页的 hub 按钮使用稳定 `aria-label`。
- **修改文件：**`apps/desktop/src/renderer/components/PlaceholderPage.tsx`、`App.tsx`、`styles.css`。
- **验证：**`@nav hubs and placeholders declare milestones without fake business data` 通过；断言资料库/题库占位页、里程碑文本与无示例题。
- **问题与处理：**`getByText('尚未连接工作区')` 同时匹配侧栏与主内容；测试改为限定 `main`，避免严格模式歧义。
- **下一步：**保证首页草稿与场景在路由切换后保留。

### 2026-10-18 F03：首页状态保持与焦点

- **当次状态：**已完成。
- **实际行为：**在首页输入文字、选择开发模块后切到资料库再返回，文字和模块选择仍在；页面切换后焦点落到一级标题；顶栏面包屑可返回首页。
- **实现与决策：**`page`、`scene`、`draft` 状态提升到 `App`，首页组件改为受控；`useEffect` 在页面变化后聚焦 `page-title`；`main` 提供跳过导航目标；页面标题使用 `tabIndex={-1}`。
- **修改文件：**`apps/desktop/src/renderer/App.tsx`、`components/Launcher.tsx`、`styles.css`。
- **验证：**`@nav preserves the draft and scene...` 与 `@nav moves focus...` 通过；键盘 Enter 激活“查看全部任务”后任务记录标题获得焦点。
- **问题与处理：**无。
- **下一步：**补响应式与回归覆盖。

### 2026-10-18 F04：测试、响应式与回归

- **当次状态：**已完成。
- **实际行为：**`@nav` 覆盖导航、空态、状态保持、焦点、键盘和 1024px 宽度；完整前端回归 14/14 通过。
- **实现与决策：**新增共享 Electron 启动 helper `tests/e2e/support/workbench-app.ts`；`shell.spec.ts` 改为复用 helper，删除重复启动代码；`verify.ps1` 纳入 `@nav`。
- **修改文件：**`tests/e2e/navigation.spec.ts`、`tests/e2e/support/workbench-app.ts`、`tests/e2e/shell.spec.ts`、`scripts/verify.ps1`。
- **验证：**`@nav` 5/5；`@shell|@unit|@nav` 14/14；typecheck 通过；`npm run package` 通过。
- **问题与处理：**无。
- **下一步：**草稿 RPC 持久化与业务页面等待后端。

## 6. 实际文件改动

| 文件 | 新增 / 修改 / 删除 | 实际用途 |
|---|---|---|
| `apps/desktop/src/renderer/navigation.ts` | 新增 | 页面元数据、主导航/更多页清单 |
| `apps/desktop/src/renderer/App.tsx` | 修改 | 页面/模块/草稿状态、面包屑、焦点管理 |
| `apps/desktop/src/renderer/components/Sidebar.tsx` | 修改 | 完整共用侧栏、空态、`aria-current` |
| `apps/desktop/src/renderer/components/Launcher.tsx` | 修改 | 受控草稿、模块切换、建议跳转、未配置状态 |
| `apps/desktop/src/renderer/components/PlaceholderPage.tsx` | 新增 | 统一占位页、更多/助理 hub、设置概览 |
| `apps/desktop/src/renderer/components/Icon.tsx` | 修改 | 新增 history/shield/arrow 图标 |
| `apps/desktop/src/renderer/styles.css` | 修改 | 侧栏、面包屑、跳转链接、占位页、hub、设置与响应式样式 |
| `tests/e2e/navigation.spec.ts` | 新增 | 5 项 `@nav` 测试 |
| `tests/e2e/support/workbench-app.ts` | 新增 | 共享 Electron 启动与清理 helper |
| `tests/e2e/shell.spec.ts` | 修改 | 复用启动 helper，保持原有断言 |
| `scripts/verify.ps1` | 修改 | 累计验证加入 `@nav` |
| `docs/development/master-plan.md`、`docs/development/tasks/T004-...md` | 修改/新增 | 台账回写 |

## 7. 验证结果

| 日期 | 执行目录 / 命令或检查 | 实际结果 | 范围与限制 |
|---|---|---|---|
| 2026-10-18 | 仓库根 / `npm --prefix apps/desktop run typecheck` | 通过 | 静态类型检查 |
| 2026-10-18 | `apps/desktop` / `npm run package` | 通过 | shell-only；服务包仍缺失 |
| 2026-10-18 | `apps/desktop` / `node scripts/run-playwright.mjs --grep '@nav'` | 5/5 通过 | 导航、空态、状态保持、焦点、1024px |
| 2026-10-18 | `apps/desktop` / `node scripts/run-playwright.mjs --grep '@shell\|@unit\|@nav'` | 14/14 通过 | 含真实本地服务握手；不含真实 DeepSeek/ASR |
| 2026-10-18 | 仓库根 / `.venv/Scripts/python.exe -m pytest services/workbench/tests -q` | 57 passed（既有证据） | 后端脚手架基线，非本任务改动 |

## 8. 遗留问题与接续步骤

| 问题 / 未完成项 | 影响与恢复条件 | 后续任务或步骤 |
|---|---|---|
| 草稿只保留在会话内 | 关闭应用后未提交文字丢失 | Task 02/08 的 `drafts.get/save` 与 ACK 实现后接入 |
| 业务页面全部为占位 | 资料、题库、面试、报告、复习不可用 | 等待 M1 Task 02～04 的 RPC 与数据契约 |
| 安装包缺本地服务 | 严格构建失败 | G01：PyInstaller 服务包与打包后握手 |
| 编号冲突 | 前后端同日各建 T003 | 前端已改号 T004；后端 T003 保留 |

接续入口：下一次先读 [master-plan.md](../master-plan.md) 的任务索引与缺口，再读本文件第 8 节；若后端 Task 02～04 已提供 RPC，则新建 T005 实现资料库页面，否则继续等待或先做服务打包验收。

## 9. 回写总文档摘要

- **回写日期：**2026-10-18。
- **任务状态：**已完成（共用导航/首页壳前端子集）。
- **完成的功能点：**F01 共用侧栏与导航模型；F02 页面路由、占位页与空态；F03 首页状态保持与焦点；F04 测试、响应式与回归。
- **里程碑变化：**M1 的共用导航/页面壳就绪；M1 业务里程碑未推进。
- **新增 / 解除的阻塞与范围变化：**新增“草稿 RPC 未接入”的已知限制；编号冲突已通过改号 T004 解决。
- **下一步：**等待后端 Task 02～04 的 RPC；可先完成 G01 服务打包与安装验收。
