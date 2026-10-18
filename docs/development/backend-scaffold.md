# 后端脚手架实施记录

日期：2026-10-18（Asia/Shanghai）。状态：后端脚手架已完成并验证，57 项后端测试与 9 项桌面集成测试通过；完整 M1 尚未完成。

范围依据：[后端执行计划](../superpowers/plans/2026-10-18-backend-scaffold-plan.md)、[M1 Task 01](../superpowers/plans/2026-10-18-ai-workbench-m1-plan.md)、[技术方案](../technical/technical-design-v1.md)。本文件保留前期实施范围；本次接续请求为“完成后端脚手架”，未要求推进全部 P0。

## 交付范围

- Python 3.14 src 布局、项目私有 `.venv`、依赖锁文件。
- stdio JSON-RPC 分帧、路由、输入校验及 system.initialize/ping/shutdown。
- 基础 Pydantic DTO 和 JSON Schema 导出/漂移检查。
- 后端初始化与检查脚本、真实 Windows 子进程测试和运行说明。

后端范围不包含 SQLite、模型/语音/MCP 或桌面安装包；本次复用已有桌面生成器生成 TypeScript 契约并验证开发态握手。父计划 Task 01 的服务捆绑和安装包验收仍未完成。

## 基线与实施方式

- 工作区：`D:\llm\agent\ai-workbench`。
- 本轮开始时无 Git 仓库和正式产品代码；初始化本地 `feat/backend-scaffold` 分支，基线提交 `ff45f9070e31a50f77bb9b6fb6d54c13f27e258e`。没有远程推送或发布。
- 可用运行时：CPython 3.14.2 x64；全局默认 python 为 Conda，因此不用于本轮安装。
- 实施代理：backend_scaffold_implementer；后续由独立代理检查规格与代码，再做最终复核。

## 范围与流程取舍

| 决定 | 原因 | 若后续需要扩展 |
| --- | --- | --- |
| 只执行 Task 01 的后端部分 | 对齐本轮用户明确范围 | 桌面和整体 M1 另行继续，不提前标完成 |
| 在现有目录建立本地 feature 分支 | 原来没有仓库或需保护的主分支 | 如以后有并行分支需要隔离，再建立 worktree |
| 首批行为测试建立后端基线 | 原来没有正式后端测试 | 既有原型验证证据仍单独保留 |
| 先导出 JSON Schema，延后 TS 生成和全阶段检查脚本 | 当前没有正式前端 | 接入桌面时增加 TS 生成和累计验收，不伪称 M1 可用 |

## 验证与审查

下方接续与最终验证记录为本次实际执行结果；前期基线与实施方式保留为历史记录。


## 2026-10-18 接续记录

- 当前用户请求完成既有后端脚手架，按已存在的技术方案及后端实施计划接续，不重建设计和台账。
- 基线：pytest 因参数名 request 被保留而无法收集；改为 payload 后，RPC 的 26 项测试均因 NotImplementedError 失败。新增 DTO/RPC 边界测试后，44 项行为测试失败，再实施协议和契约。
- Ruling: 沿用当前 .venv 和未提交后端文件；保留原型及前端改动，不自动提交 Git。当前请求授权实现，旧计划中的代理/提交安排不作为新增授权。
- Ruling: 慢请求进程测试先完成 initialize，再开始 0.5 秒心跳计时；避免把 Python/Pydantic 冷启动混入请求并发断言。
- 依照 test-driven-development / verification-before-completion 执行边界测试和最终检查；按现有实施记录回写。


## 最终实现与验证（2026-10-18）

- 主代理接续现有占位实现，完成 strict DTO、协议校验、8 MiB 分帧、路由、守护线程同步 handler、单 writer、有界读写队列、系统方法和正常退出；数据目录仅日志，5 MiB × 5 备份轮转。
- requirements.lock 按实际 pyproject 重生，去掉旧锁残留的 PyInstaller，补齐 pip/setuptools 的精确版本和哈希；bootstrap 不修改全局环境。
- 增加独立后端 bootstrap/verify、schema 导出及漂移检测；复用前端生成器产生 contracts/generated.ts。
- 独立审查 backend_review 发现两个 P2：极长 ID 的错误响应二次超限、shutdown 输入积压时读线程取消竞态。均以真实子进程测试确认 Red，再修复；新增 3 项测试 Green，未留待修复审查项。

| 命令 / 检查 | 实际结果 | 范围 |
| --- | --- | --- |
| powershell -NoProfile -ExecutionPolicy Bypass -File scripts/bootstrap-backend.ps1 | 退出 0，锁文件安装、editable、pip check 和 schema 导出通过 | 项目 .venv |
| powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-backend.ps1 | 退出 0；57 passed；pip check、compileall、schema --check 通过 | 后端全量 |
| 含空格临时目录全新 venv 的 bootstrap/verify | 全新 venv 安装通过；最终代码 57 passed、依赖/compileall/schema 均通过 | 无全局包安装 |
| npm --prefix apps/desktop run contracts:types:check / typecheck | 均退出 0 | schema 与桌面 TS |
| node apps/desktop/scripts/run-playwright.mjs --grep '@shell|@unit' | 9 passed，0 跳过 | 真实 Electron 开发态、本地 Python、IPC/CSP/握手/契约漂移 |
| schema --output 临时文件后修改内容 --check | 非零且不覆盖临时文件 | 已纳入 pytest |

- Ruling: 极限 ID 无法放入有界错误帧时返回 id:null；代价是调用方需按未知请求错误处理，不能用超限 ID 使本地服务退出。
- Ruling: 在后端闭环时同步现有前端契约生成器产物，原因是前端已经存在并需要解除联调阻塞；没有修改前端行为。
- 未执行 Git commit/push。现有未跟踪后端与原型文件均保留，代码已在工作区可审阅。
- 后续：服务发行包与安装验收、SQLite 迁移和幂等写；不把本任务完成等同于完整 M1 或真实 DeepSeek/ASR 已验证。

- 最终补验：verify.ps1 -Stage M2 返回 1，未实现阶段不会空成功；schema 和 TS 类型 --check 最终通过。临时验证副本已删除，只保留忽略目录中的验证日志。
