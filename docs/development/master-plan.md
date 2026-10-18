# 知序 · 个人 AI 工作台 开发任务总览

> 最近更新：2026-10-18
> 当前阶段：M1 桌面、存储及后端任务协调器已贯通；真实建题业务流尚未开始
> 当前任务：T005 后端任务队列、事件、取消与恢复已完成；T003/T004 已提交推送
> 下一步：后端 M1 Task 04（工作区、真实资料与来源快照）；前端草稿、任务页和真实 RPC 联调待接入；G01 服务打包独立保留

## 1. 主线目标与范围

交付 Windows 个人 AI 工作台 P0：选资料 → 生成候选题 → 检查入库 → 文字/语音面试 → 有依据的报告 → 手动复习 → 重开继续。首版聚焦面试准备；课程学习复盘属于 P1，不阻塞 P0。

当前框架与边界以以下文档为准：

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

当前焦点：T003 后端存储已完成，后端 87/87；T004 共用导航/首页壳已完成，全量前端 14/14，schema=1 握手通过。T005 已完成 M1 Task 03 后端，120/120全量、31项任务/恢复回归，下一后端Task04；草稿目前仅开放 local 后端入口，前端持久化尚未接入，业务 owner 需在实体实现后校验归属。服务打包仍是 M1 门禁缺口。

## 5. 缺口、依赖与范围变化

| 编号 | 事项与影响 | 关联任务 / 阶段 | 当前处理与恢复条件 |
|---|---|---|---|
| G01 | 安装包缺少本地服务：未安装 PyInstaller，`services/workbench/dist/workbench-service` 不存在；`build.ps1 -Stage M1` 会按设计失败 | M1 / 下一打包任务 | 在 `.venv` 安装 PyInstaller，生成 onedir 服务包，再执行严格构建与打包后握手 |
| G02 | 后端脚手架与契约已提交推送，原提交缺口已解除 | T002 | 2026-10-18 按用户要求推送 main，远程提交 8ee582a；不表示后续开发自动推送 |
| G03 | M1 业务流未开始：Task 02存储及Task 03后端队列已完成；资料版本、DeepSeek配置、候选校验、题库事务与导出仍属Task 04～09；T004 导航壳已完成，前端持久化与业务接口待接入 | M1 | 按 M1 Task 04～09 顺序实施；前端接续真实 RPC，不提前伪造业务数据 |
| G04 | Windows Job Object 子进程树管理未实现；当前使用 `taskkill /T` 并等待退出 | M1 / 打包阶段 | 在发行包任务中补齐并做异常退出验证 |
| G05 | 真实 DeepSeek/ASR 未配置、未验证；当前只有替身与本地协议证据 | M1/M3 | 配置用户自己的服务后执行真实样本；缺账号时保留受阻状态 |

## 6. 状态与完成口径

任务采用：待开始、进行中、待验证、受阻、已完成、已取消；重开任务保留原完成记录并注明原因与日期。任务完成以范围内功能点、验收条件、必要验证和回写为依据；环境受阻或验证未执行时保留“受阻/待验证”。支撑任务完成不自动推进业务里程碑。业务规则以 PRD、技术方案和接口契约为准，台账不保存凭据或敏感原文。

## 7. 每日汇总

| 日期 | 当日涉及任务 | 产出与主线结论 | 遗留与下一步 |
|---|---|---|---|
| 2026-10-18 | [T001](tasks/T001-2026-10-18-desktop-scaffold.md)、[T002](tasks/T002-2026-10-18-backend-scaffold.md)、[T003](tasks/T003-2026-10-18-backend-storage.md)、[T004](tasks/T004-2026-10-18-shared-navigation-shell.md)、[T005](tasks/T005-2026-10-18-backend-tasks.md) | 桌面脚手架完成：TypeScript 检查通过、Windows 桌面包构建通过、全量前端 Playwright 14/14；后端脚手架完成：57/57 pytest、哈希安装与含空格干净环境验证通过，两项审查问题已修复，契约类型检查通过；T003 后端存储完成：87/87 全量后端、schema=1 握手、独立 wheel 安装/重开通过，审查 P2 已修复；T004 共用导航与首页壳完成：侧栏、路由、空态、草稿/模块保持与焦点管理，新增 `@nav` 5/5；M1 业务流未开始 | T005后端完成：120/120、14/14兼容、wheel恢复验证及审查修复；下一后端Task04；G01服务打包、前端任务页/草稿联调保留 |
