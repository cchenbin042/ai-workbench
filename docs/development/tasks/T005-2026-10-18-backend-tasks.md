# T005：后端任务队列、事件、取消与恢复

## 1. 任务信息

| 字段 | 内容 |
| --- | --- |
| 任务编号 | T005 |
| 类型 / 关联里程碑 | 后端开发 / M1 Task 03 后端部分 |
| 状态 | 已完成 |
| 创建日期 | 2026-10-18 |
| 开始日期 | 2026-10-18 |
| 最近更新 | 2026-10-18 |
| 完成日期 | 2026-10-18 |
| 最近回写 | 2026-10-18 |
| 总文档 | [master-plan.md](../master-plan.md) |
| 前置依赖 | T003；提交 3f7e2bf 已推送 origin/codex/backend-storage |
| 需求 / 设计 | [M1 Task 03](../../superpowers/plans/2026-10-18-ai-workbench-m1-plan.md)、[技术方案 §3/5](../../technical/technical-design-v1.md) |

## 2. 目标和范围

单 AI 执行槽 FIFO、waiting_user 释放槽、run 提交栅栏、同事务事件和快照水位、显式恢复、启动不重发旧 queued。沿用既有计划，在 codex/backend-tasks 内联开发，使用 dev-task-tracker / ponytail / TDD / executing-plans / verification-before-completion。

用户授权先提交当前代码再继续后端：3f7e2bf 已推送且远程 hash 相同；本任务不改 main。

## 3. 功能点

| 编号 | 行为与验收 | 状态 |
| --- | --- | --- |
| F01 | tasks/task_runs/task_events 迁移、严格 DTO 和查询 | 已完成 |
| F02 | FIFO 单槽、状态迁移与 waiting_user 释放 | 已完成 |
| F03 | run 栅栏、取消与原子事件提交 | 已完成 |
| F04 | 启动恢复、真实进程重开、契约与回归 | 已完成 |

## 4. 实施与验收

- [x] 建立行为测试并确认 Red。
- [x] 实现后端功能和服务生命周期。
- [x] 全量后端、桌面兼容、迁移安装资源验证。
- [x] 独立审查、修复和回写。

## 5. 开发记录与决策

### 2026-10-18 / 开始

- Ruling: 本次仅后端 Task 03，不修改 TaskPage/useTask 或 preload；用户明确继续后端，前端 @tasks 验收另行接续，不能将其记为通过。
- Ruling: 此阶段仅内部受控流程可创建任务；workspace/agent 为 null，material_version_ids 为空。查询、取消和恢复可通过 stdio 调用；不向用户开放占位 Agent。实体落地后再验证真实 owner 与不可变版本快照。
- Ruling: 复用 src/workbench/migrations 的 package data 和 LF 约定，不新增调度框架或依赖。
- 预检共享接口：Task 02 提供 Storage.transaction/write_once/read，Task 03 事务回调同步；Task 04/05 未来添加真实引用校验，当前拒绝伪造引用。

## 6. 实际文件改动

- tasks.py：持久化 FIFO 单执行槽、状态/run 校验、取消、显式恢复、事件发布、查询分页和关闭。
- migrations/0002_tasks.sql：tasks/task_runs/task_events、FK、状态约束与单槽唯一索引。
- contracts.py、__main__.py：严格 DTO 和任务 RPC、启动恢复及关闭，schema=2。
- tests/test_tasks.py、test_recovery.py、test_service_process.py：真实 SQLite、屏障和子进程重开/kill。
- test_storage.py：初始 schema=2，升级失败/备份测试改为从真实 schema2 升级测试schema3，保留原断言。
- contracts/rpc.schema.json / generated.ts、tests/e2e/shell.spec.ts：导出契约与 schema=2 握手。

## 7. 验证

基线在提交前重新验证：87/87 后端、14/14 桌面、契约与类型检查通过；不是 Task 03 完成证据。

## 8. 遗留与接续

后端 F01～F04 已完成。下一后端任务为 M1 Task 04：工作区、真实资料与来源快照；扩展任务引用时验证真实实体归属。前端 TaskPage/useTask/preload 与 @tasks 验收另行接入；真实模型/材料和服务发行包尚未完成。

## 9. 回写摘要

2026-10-18：T005 后端部分已完成，最终120/120后端、14/14桌面兼容、独立wheel验证通过，审查问题已修复，M1仍进行中。下一后端Task04，前端@tasks尚未实现。

### 2026-10-18 / F01～F04 实施

- 初始19项任务/恢复测试均因NotImplemented失败，实施后19/19；新增边界后完整后端114通过。
- 当前28项任务/恢复通过；真实子进程测试先准备持久任务，启动服务后queued/running转interrupted、waiting_user检查点保留；kill后重启不增加历史事件、不重跑。
- 发现并修复旧取消operation在恢复后重放误取消新run，单测先Red再Green；副作用只附着本次实际提交的取消事件。
- 任务输入及scope快照不随continue修改；continue仅接受当前waiting_reason动作，后续输入保存在检查点。
- 事件推送是尽力交付，outgoing满或回调失败不回滚已提交业务，events.list按序补偿。没有前端@tasks测试，不据此声明UI已接入。
- 独立审查review_backend_tasks完成，2项实质问题均已修复；复核31/31任务与恢复通过，无新增实质缺陷。

### 2026-10-18 / 审查修复

- 独立审查复现：短暂数据库锁会令唯一worker退出；补外部BEGIN IMMEDIATE真实Red→Green，现只重试本地原子槽获取，禁止重发provider调用。
- 独立审查复现：run事务提交后、协程注册前取消可能仍启动handler；补提交后barrier真实Red→Green，用同一asyncio锁协调注册与取消。
- 同根因扩展验证：flow失败时数据库被锁会丢失收尾，补Red→Green；现保留槽并退避重试本地失败/取消收尾，不重跑flow。
- 当前31项任务/恢复通过；此前完整117/117、桌面14/14、wheel独立安装/事件恢复均通过，最终全量待复跑。


### 2026-10-18 / 最终验收

| 命令 / 检查 | 结果 | 限制 |
| --- | --- | --- |
| scripts/verify-backend.ps1 | 120 passed / 22.28s；pip check、compileall、schema一致 | 真实SQLite及进程，非真实云服务 |
| pytest test_tasks.py test_recovery.py | 31 passed | FIFO/barrier/取消/锁恢复/重启 |
| npm desktop typecheck、contracts:types:check | 退出0 | 契约已导出，无漂移 |
| npm desktop test:e2e -- --grep `@shell&#124;@unit&#124;@nav` | 14 passed；构建成功、schema2握手 | 开发Python服务，未声称@tasks UI可用 |
| 独立wheel安装与-I进程 | 通过：任务SQL为LF、queued启动恢复、事件重放、EOF | 非PyInstaller发行验收 |
| 独立review_backend_tasks | 31 passed；2项问题修复后无新增实质缺陷 | 只读审查 |

最终代码在codex/backend-tasks，基线3f7e2bf；按既有实施计划单独提交本任务文件。上一快照已推送，不合并main。开发台账及运行说明同步更新。
