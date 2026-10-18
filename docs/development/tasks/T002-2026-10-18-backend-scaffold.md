# T002：后端脚手架

## 1. 任务信息

| 字段 | 内容 |
| --- | --- |
| 任务编号 | T002 |
| 类型 / 关联里程碑 | 开发任务 / M1 的基础设施部分，不计业务里程碑完成 |
| 状态 | 已完成 |
| 创建日期 | 2026-10-18（接续时补登记） |
| 开始日期 | 2026-10-18 |
| 最近更新 | 2026-10-18 |
| 完成日期 | 2026-10-18 |
| 最近回写 | 2026-10-18 |
| 总文档 | [master-plan.md](../master-plan.md) |
| 前置依赖 | CPython 3.14；已有后端执行计划与占位测试 |
| 需求 / 设计 / 契约 | [后端计划](../../superpowers/plans/2026-10-18-backend-scaffold-plan.md)、[技术方案](../../technical/technical-design-v1.md)、[运行说明](../../../services/workbench/README.md) |

## 2. 目标与主线关系

提供可安装、可启动、可测试的 Python stdio 本地服务，解除桌面开发态握手阻塞，为 M1 数据持久化提供稳定协议入口。用户要求完成后端脚手架；本任务不包含数据库、模型、语音、MCP 和发行包。

## 3. 范围与功能点

| 功能点 | 实际行为与验收条件 | 状态 |
| --- | --- | --- |
| F01 | src 包、项目 venv、带哈希依赖锁和可重装 bootstrap | 已完成 |
| F02 | JSON-RPC 分帧、严格校验、路由、系统方法、慢请求并发与退出 | 已完成 |
| F03 | 严格 DTO、JSON Schema 导出/漂移检测及复用 TS 生成器 | 已完成 |
| F04 | 后端脚本、真实 Windows 管道、独立审查与桌面集成验证 | 已完成 |

## 4. 实施步骤与验收

- [x] 检查已有设计、占位源文件、测试和前端契约。
- [x] 修复 pytest 保留参数造成的收集失败，再确认 26 个 RPC 行为测试 Red。
- [x] 补充严格 DTO 与进程边界测试，完成最小实现。
- [x] 完成真实安装、全量后端检查、schema 漂移及桌面握手。
- [x] 独立审查两项 P2 均补 Red→Green 回归后修复。
- [x] 回写实施记录、总览与运行说明。

## 5. 开发记录

### 2026-10-18 / F01～F03：接续占位实现

- **实际行为：**可通过项目 .venv 启动 workbench，initialize/ping/shutdown 真实可用；schema_version=0，不伪造数据库。
- **实现与决策：**有界帧与队列、单写者、同步守护线程，严格 Pydantic DTO；source 不从 params 提权；日志不记录请求和异常详情。
- **验证：**44 个 RPC/DTO 测试先失败再通过；导出 CLI 测试先失败再通过；完整初版 54 passed。
- **问题与处理：**测试 request 参数改名；慢请求计时移到握手之后；旧锁文件中无关 PyInstaller 及缺失的安装工具哈希已经清理补齐。

### 2026-10-18 / F04：独立审查与最终验证

- **实际行为：**保持 stdin 打开也能退出；错误帧后继续响应；同步与异步慢 handler 不阻塞系统心跳。
- **审查修复：**极限 ID 响应再次超限造成退出；输入积压时 reader 调度取消引起 stderr 异常。新增 3 项真实子进程测试，均看到 Red 后修复 Green。
- **验证：**verify-backend 57 passed，pip check、compileall、schema --check 全通过；Electron @shell|@unit 9 passed；桌面 typecheck 与 TS 契约漂移检查通过。
- **干净环境：**output/verification/backend space 中新建独立 venv，按 SHA256 锁文件安装成功；初版 54 passed，最终实现 57 passed，pip check/compileall/schema 均通过。输出目录受 Git 忽略。
- **取舍：**不提交或推送 Git；不改变数据库/发行包范围。完整证据及 Ruling 见 [backend-scaffold.md](../backend-scaffold.md)。

## 6. 实际文件改动

| 文件 | 类型 | 用途 |
| --- | --- | --- |
| services/workbench/src/workbench/{rpc,contracts,__main__}.py | 实现 / 新增 | 协议、严格 DTO、服务生命周期 |
| services/workbench/requirements.lock、README.md | 重生 / 新增 | 哈希依赖和运行说明 |
| services/workbench/tests/{test_rpc,test_service_process,test_contracts,test_contract_export}.py | 修改 / 新增 | 协议、进程和契约验证 |
| scripts/{bootstrap-backend,verify-backend}.ps1、export-contracts.py | 新增 | 安装、验收、导出 |
| contracts/{rpc.schema.json,generated.ts} | 生成 | Python/TS 契约 |
| docs/development/backend-scaffold.md、runtime-baseline.json、master-plan.md、README.md | 回写 | 实际状态与证据入口 |

包 pyproject.toml、__init__.py 和 process_helper.py 为已存在的未跟踪输入，本次保留。原型及前端源码未作本任务改写。

## 7. 验证结果

| 日期 | 命令 | 实际结果 | 范围与限制 |
| --- | --- | --- | --- |
| 2026-10-18 | powershell -NoProfile -ExecutionPolicy Bypass -File scripts/bootstrap-backend.ps1 | 退出 0 | 仅项目 .venv |
| 2026-10-18 | powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-backend.ps1 | 57 passed，依赖/编译/schema 全通过 | 完整后端 |
| 2026-10-18 | node apps/desktop/scripts/run-playwright.mjs --grep '@shell|@unit' | 9 passed | 本机真实 Electron + Python；非发行包服务 |
| 2026-10-18 | npm --prefix apps/desktop run typecheck / contracts:types:check | 退出 0 | 当前已安装桌面依赖 |

## 8. 遗留与接续

本任务范围内无已知待修复审查项；服务 onedir 打包、安装包握手、无 Python/Node 环境运行仍未完成，父 M1 Task 01 不能整体标为完成。下一任务先读总览 G01 与 M1 Task 01，然后完成服务捆绑与发行验收；之后实施 Task 02 SQLite 迁移与幂等写。

## 9. 回写总文档摘要

- **回写日期：**2026-10-18。
- **任务状态：**已完成。
- **完成的功能点：**F01～F04。
- **里程碑变化：**M1 保持进行中；后端基础设施完成，业务流未开始。
- **解除阻塞：**后端占位接口、严格 DTO、schema 缺失、桌面开发态握手。
- **下一步：**服务打包与安装验收；不把未提交代码记为未实现。
