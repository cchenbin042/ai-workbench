# 知序 · 个人 AI 工作台 开发任务总览

> 最近更新：2026-10-25
> 当前阶段：M1 桌面壳、本地协议、存储、后端任务机制与工作区/真实资料（Task 04）已完成；DeepSeek 接入与建题流程未完成
> 当前任务：T008 工作区、真实资料与来源快照已完成（后端 132/132、桌面 e2e 17/17）；业务阶段进入 M1 Task 05
> 下一步：M1 Task 05（DeepSeek 配置、系统密钥与文本请求）；前端草稿与任务页联调待接入；G01 服务打包独立保留

## 1. 主线目标与范围

交付 Windows 个人 AI 工作台 P0：选资料 → 生成候选题 → 检查入库 → 文字/语音面试 → 有依据的报告 → 手动复习 → 重开继续。首版聚焦面试准备；课程学习复盘属于 P1，不阻塞 P0。

当前框架与边界以以下文档为准：

- [项目接手指南](agent-onboarding.md)：智能体阅读入口与带日期的项目理解快照，不替代业务和工程基线。
- [联合 PRD 优化方案](../product/2026-10-19-prd-optimization-proposal.md)：两轮评审及建议，待用户采纳，未替换原 PRD/计划。
- [PRD v1.0](../product/prd-ai-workbench-v1.md)
- [技术方案 v1.0](../technical/technical-design-v1.md)
- [M1 实施计划](../superpowers/plans/2026-10-18-ai-workbench-m1-plan.md)
- [后端脚手架执行计划](../superpowers/plans/2026-10-18-backend-scaffold-plan.md)
- [UI 交互设计](../product/2026-10-18-workbench-ui-design.md)
- [设计覆盖与实现差距](../product/2026-10-18-design-coverage.md)

开发主线：设计基线（D0）→ 桌面/本地服务脚手架 → M1 真实建题 → M2 文字训练闭环 → M3 语音、MCP、发行 → M4 课程学习。

## 2. 里程碑

| 编号 | 里程碑 | 当前状态 | 完成条件 | 依赖 |
|---|---|---|---|---|
| D0 | 产品、技术、实施与 UI 设计 | 已完成 | 文档与交互原型一致，差距清单明确 | 无 |
| M1 | 第一条真实建题流程 | 进行中 | AC01～05、19、21、23 相关切片；真实资料 → DeepSeek 候选题 → 本地题库 | 桌面/本地服务脚手架已贯通；服务打包与业务流未完成 |
| M2 | 文字训练闭环 | 待开始 | AC06～08、11～16、20 | M1 验收通过 |
| M3 | 首版收口 | 待开始 | AC09～10、17～18、22、24 | M2 验收通过；真实 ASR/可信 MCP 服务可用 |
| M4 | 课程学习复盘 | 待开始 | 独立 P1 验收 | P1 输入可行性与方案确认 |

## 3. 已核验基线

- 设计交付：[设计覆盖与实现差距](../product/2026-10-18-design-coverage.md)记录原型四组检查 42 项通过；原型仍是演示，不替代正式验收。
- 桌面脚手架：提交 `0d77993`、`ede04f2`；`npm --prefix apps/desktop run typecheck` 通过；`npm --prefix apps/desktop run package` 通过；Playwright `@shell|@unit|@nav` 14/14 通过；T004 完成共用导航/首页壳；产物在 `apps/desktop/out/ZhixuWorkbench-win32-x64`。
- 本地服务：T002 完成 RPC/CLI/契约，历史基线 57 passed，已按要求推送；T003 新增 SQLite/草稿 RPC，最终 `scripts/verify-backend.ps1` 为 87 passed，pip check、compileall、schema/TypeScript 漂移和类型检查通过。wheel 在带空格临时目录独立安装后保存/EOF 提交/重开重放通过，迁移 SQL 为 LF。独立审查的行尾 P2 已修复并复审；T003/T004 已按用户要求提交 3f7e2bf 并推送 origin/codex/backend-storage。
- 任务协调器：T005单FIFO槽、run栅栏、同事务事件、显式恢复和RPC已实现；最终120 passed，31项任务/恢复用例。审查复现的锁恢复和取消启动窗口均Red→Green修复；桌面14/14、schema2握手和wheel独立安装恢复通过；前端@tasks和真实provider未接入。
- 前端实施记录：[frontend-scaffold.md](frontend-scaffold.md)。后端实施记录：[backend-scaffold.md](backend-scaffold.md)。
- 未核验：安装包内服务启动、无 Python/Node 环境运行、真实 DeepSeek/ASR、M1 业务流。

## 4. 任务索引与当前焦点

| 编号 | 任务 | 类型 / 里程碑 | 状态 | 最近更新 | 明细 |
|---|---|---|---|---|---|
| T001 | 桌面脚手架（前端部分） | 开发任务 / M1 | 已完成 | 2026-10-18 | [T001-2026-10-18-desktop-scaffold.md](tasks/T001-2026-10-18-desktop-scaffold.md) |
| T002 | 后端脚手架 | 开发任务 / M1 | 已完成 | 2026-10-18 | [T002-2026-10-18-backend-scaffold.md](tasks/T002-2026-10-18-backend-scaffold.md) |
| T003 | SQLite、幂等写与迁移备份 | 后端开发 / M1 Task 02 | 已完成 | 2026-10-18 | [T003-2026-10-18-backend-storage.md](tasks/T003-2026-10-18-backend-storage.md) |
| T004 | 共用导航与首页壳（前端部分） | 开发任务 / M1 | 已完成 | 2026-10-18 | [T004-2026-10-18-shared-navigation-shell.md](tasks/T004-2026-10-18-shared-navigation-shell.md) |
| T005 | 后端队列、事件、取消与恢复 | 后端开发 / M1 Task 03 | 已完成 | 2026-10-18 | [T005-2026-10-18-backend-tasks.md](tasks/T005-2026-10-18-backend-tasks.md) |
| T006 | 项目理解与智能体接手文档 | 文档支撑 / 不推进业务里程碑 | 已完成 | 2026-10-19 | [T006-2026-10-19-agent-onboarding.md](tasks/T006-2026-10-19-agent-onboarding.md) |
| T007 | Claude Code / OpenCode 联合 PRD 评审 | 产品评审支撑 / 不直接改变业务范围 | 已完成 | 2026-10-19 | [T007-2026-10-19-prd-joint-review.md](tasks/T007-2026-10-19-prd-joint-review.md) |
| T008 | 工作区、真实资料与来源快照 | 后端 + 桌面开发 / M1 Task 04 | 已完成 | 2026-10-25 | [T008-2026-10-25-workspaces-materials.md](tasks/T008-2026-10-25-workspaces-materials.md) |

当前焦点：T008 完成 M1 Task 04 后端与桌面接线：schema=3（workspaces/directory_links/materials/material_versions），路径安全受控读取、grant 目录授权、不可变来源快照与新鲜度检查；公开 RPC 新增 workspaces.*（create/list/listLinks/linkDirectory/unlinkDirectory）与 materials.*（listDirectory/importFiles/importText/list/get/checkFreshness/previewFile），`internal.registerGrant` 仅 main 可调；资料库页（WorkspacePage）接入真实数据并新增 @materials e2e。后端 132/132、桌面 17/17、typecheck 与契约检查通过。T006/T007 文档与本任务代码均未提交，待用户授权。

## 5. 缺口、依赖与范围变化

| 编号 | 事项与影响 | 关联任务 / 阶段 | 当前处理与恢复条件 |
|---|---|---|---|
| G01 | 安装包缺少本地服务：未安装 PyInstaller，`services/workbench/dist/workbench-service` 不存在；`build.ps1 -Stage M1` 会按设计失败 | M1 / 下一打包任务 | 在 `.venv` 安装 PyInstaller，生成 onedir 服务包，再执行严格构建与打包后握手 |
| G02 | 后端脚手架与契约已提交推送，原提交缺口已解除 | T002 | 2026-10-18 按用户要求推送 main，远程提交 8ee582a；不表示后续开发自动推送 |
| G03 | M1 业务流进行中：Task 02/03/04 已完成（存储、任务队列、工作区与资料快照）；DeepSeek 配置、候选校验、题库事务与导出属 Task 05～09；前端草稿持久化与任务页联调待接入 | M1 | 按 M1 Task 05～09 顺序实施；前端接续真实 RPC，不提前伪造业务数据 |
| G04 | Windows Job Object 子进程树管理未实现；当前使用 `taskkill /T` 并等待退出 | M1 / 打包阶段 | 在发行包任务中补齐并做异常退出验证 |
| G05 | 真实 DeepSeek/ASR 未配置、未验证；当前只有替身与本地协议证据 | M1/M3 | 配置用户自己的服务后执行真实样本；缺账号时保留受阻状态 |

## 6. 状态与完成口径

任务采用：待开始、进行中、待验证、受阻、已完成、已取消；重开任务保留原完成记录并注明原因与日期。任务完成以范围内功能点、验收条件、必要验证和回写为依据；环境受阻或验证未执行时保留“受阻/待验证”。支撑任务完成不自动推进业务里程碑。业务规则以 PRD、技术方案和接口契约为准，台账不保存凭据或敏感原文。

## 7. 每日汇总

| 日期 | 当日涉及任务 | 产出与主线结论 | 遗留与下一步 |
|---|---|---|---|
| 2026-10-25 | [T008](tasks/T008-2026-10-25-workspaces-materials.md) | M1 Task 04 完成：迁移 0003（schema=3）、paths/workspaces/materials 三模块、13 个公开 RPC 与内部 grant 登记、桌面 dialogs/白名单/资料库页、@materials e2e 3 项。先 Red（12 项）后 Green；最终后端 132/132、桌面 17/17、typecheck 与契约检查通过。forge.config.ts 钉住 electron zip sha256 修复离线打包 | 未提交待授权；下一任务 M1 Task 05（DeepSeek/密钥）；G01 打包、前端草稿与任务页联调、真实 provider 缺口不变 |
| 2026-10-19 | [T006](tasks/T006-2026-10-19-agent-onboarding.md)、[T007](tasks/T007-2026-10-19-prd-joint-review.md) | T006 完成接手指南与入口，85 个链接及读者检查通过；同会话先前后端 120 项、类型/契约通过。T007 协调真实 Claude Code/OpenCode 完成独立审查和交叉讨论，四项 dispatch succeeded，保存双方报告与综合建议；原 PRD/代码/计划未改 | M1 仍进行中，下一业务 Task 04；优化建议待采纳，正式门禁未变。T006 校验时 Python 基础解释器不可用待核实（T008 会话未复现）；发行、前端联调和真实 provider 缺口不变 |
| 2026-10-18 | [T001](tasks/T001-2026-10-18-desktop-scaffold.md)、[T002](tasks/T002-2026-10-18-backend-scaffold.md)、[T003](tasks/T003-2026-10-18-backend-storage.md)、[T004](tasks/T004-2026-10-18-shared-navigation-shell.md)、[T005](tasks/T005-2026-10-18-backend-tasks.md) | 桌面脚手架完成：TypeScript 检查通过、Windows 桌面包构建通过、全量前端 Playwright 14/14；后端脚手架完成：57/57 pytest、哈希安装与含空格干净环境验证通过，两项审查问题已修复，契约类型检查通过；T003 后端存储完成：87/87 全量后端、schema=1 握手、独立 wheel 安装/重开通过，审查 P2 已修复；T004 共用导航与首页壳完成：侧栏、路由、空态、草稿/模块保持与焦点管理，新增 `@nav` 5/5；M1 业务流未开始 | T005后端完成：120/120、14/14兼容、wheel恢复验证及审查修复；下一后端Task04；G01服务打包、前端任务页/草稿联调保留 |
