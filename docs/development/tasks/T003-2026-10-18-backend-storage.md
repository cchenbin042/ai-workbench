# T003：SQLite 持久化、幂等写和迁移备份

## 1. 任务信息

| 字段 | 内容 |
| --- | --- |
| 任务编号 | T003 |
| 类型 / 关联里程碑 | 后端开发 / M1 Task 02 |
| 状态 | 已完成 |
| 创建日期 | 2026-10-18 |
| 开始日期 | 2026-10-18 |
| 最近更新 | 2026-10-18 |
| 完成日期 | 2026-10-18 |
| 最近回写 | 2026-10-18 |
| 总文档 | [master-plan.md](../master-plan.md) |
| 前置依赖 | T002；CPython 3.14 / sqlite3 |
| 需求 / 设计 / 契约 | [M1 Task 02](../../superpowers/plans/2026-10-18-ai-workbench-m1-plan.md)、[技术方案 §4](../../technical/technical-design-v1.md) |

## 2. 目标与范围

按用户“继续后端任务”接续既有 M1 后端计划。实现 Storage.read/transaction/write_once、首个 SQL 迁移、迁移备份、草稿保存和读取 RPC。SQLite 单写线程、WAL/FULL/FK/5000 ms；成功提交后才 ACK；重放先于新请求 revision 校验。服务发行包继续作为独立缺口。

## 3. 功能点

| 功能点 | 验收 | 状态 |
| --- | --- | --- |
| F01 | 真实 SQLite 事务、只读查询与安全关闭 | 已完成 |
| F02 | operation 重放、冲突与原子回滚 | 已完成 |
| F03 | 顺序迁移、checksum、backup/integrity 与保留策略 | 已完成 |
| F04 | 本地草稿保存/读取、严格 DTO、schema_version=1、进程重开 | 已完成 |

## 4. 实施与验收

- [x] 测试先行并确认真实 Red。
- [x] 实现 Storage 与初始表。
- [x] 接入 RPC、契约导出与生命周期。
- [x] 后端全量、桌面兼容、安装资源检查。
- [x] 审阅、回写与接续说明。

## 5. 开发记录

### 2026-10-18 / 开始

- 主代理沿用已有设计与 Task 02，执行方式为当前会话内联；使用 ponytail 控制范围、TDD 和 verification-before-completion 验证结果。
- 分支 codex/backend-storage，基线 8ee582a；在当前干净工作区切分支，避免额外 worktree/重复安装；不改 main、不推送。
- Ruling: 后端开发先做 Task 02，服务发行打包保留 G01，不让桌面发行验证阻塞独立的数据底座；代价是本轮不能宣称完整 M1 Task 01 验收。
- Ruling: 工作区/任务归属实体尚未实现，草稿入口仅开放 local 本地编辑器，业务 owner 类型暂不接受；后续接入真实 owner 时必须增加归属校验，不能信任请求中的 scope。
- Ruling: SQL 放入 src/workbench/migrations 并作为 package data 安装，保证 wheel 和后续 PyInstaller 不依赖源码目录；与原计划根 migrations 路径不同，接口不变。

## 6. 实际文件改动

- services/workbench/src/workbench/storage.py：单写线程、只读 reader、事务与幂等命令、迁移备份、草稿保存/读取。
- services/workbench/src/workbench/migrations/0001_core.sql：4 张初始 STRICT 表；.gitattributes 固定迁移行尾。
- contracts.py / __main__.py：草稿 DTO、方法注册、实际数据库版本和有序关闭。
- services/workbench/tests/test_storage.py / test_service_process.py：真实 SQLite 与管道进程回归。
- pyproject.toml / scripts/build.ps1：wheel SQL package data、PyInstaller SQL 与包元数据资源声明。
- contracts/rpc.schema.json / generated.ts：同步契约；tests/e2e/shell.spec.ts 仅在既有前端修改上更新两处 schema=1 断言。
- README.md / services/workbench/README.md 与本任务/总台账：当前能力、运行说明、验证与接续。
- 工作区还有 T004 前端修改；本轮保留其文件、测试和台账记录，不归入后端成果。

## 7. 验证

- Red：初始 Storage 未实现时存储测试失败；新增 RPC/只读/清理测试确认 6 failed / 33 passed，再实施修复。
- 最终 verify-backend.ps1 退出 0：87 passed（19.10 s），含 27 项存储回归；pip check、compileall 和 schema --check 均通过。
- Electron 构建与 @shell|@unit|@nav 14/14 通过，实际 schema=1 握手；桌面 typecheck、契约生成/漂移检查通过。
- wheel 构建通过；临时带空格目录独立安装，用 -I 隔离进程从已安装包导入，SQL 存在且 LF、草稿保存/EOF 提交/重启重放通过。
- 独立 review_backend_storage 报告 1 项 P2：SQL 行尾导致 hash 漂移；已固定 LF，审查员复审确认解除且 27/27 通过，无新增实质缺陷。
- 额外补测回调 CancelledError 真实 Red→Green，保证回滚后下一事务仍可用。

## 8. 遗留与接续

本任务范围内验证及审查已完成。接续 M1 Task 03（队列、事件、取消、恢复）；服务包/安装验收保留 G01。前端草稿持久化尚未接入，当前 local-only 后端入口不等于业务 owner 归属已完成。

## 9. 回写摘要

2026-10-18：T003 已完成；全量后端 87/87、Electron 14/14、独立 wheel 安装/重开验证通过；M1 保持进行中，下一后端任务为 Task 03，G01 服务发行与前端草稿接入仍未完成。


### 2026-10-18 / 实施与审查

- 保存 ACK 在事务 COMMIT 后发送；RPC 取消只取消等待，不取消已接受写入；close 排空写线程后关闭连接。
- 只读 reader 增加 SQLite authorizer，拒绝 ATTACH 和写 PRAGMA；满盘/只读/锁竞争均验证不留成功 operation。
- 迁移清理发生在 COMMIT 后，清理失败只告警；清单补齐 app/protocol 版本、哈希与附件范围。
- Ruling: 当前尚未发布存储版本，直接将首迁移固定为 LF；不添加历史 CRLF hash 兼容。已在本轮中间版本创建的临时测试库不视为已发行数据。
- Ruling: build.ps1 仅补齐本功能必需的 --collect-data / --copy-metadata，不扩大至 G01 整套发行实现；未宣称 PyInstaller 服务包已验证。
- 沿用本轮开始时的不自动提交/推送安排，Task 02 的提交步骤未执行；代码在 codex/backend-storage 工作区供审阅。

- 最终复核：87/87 全量后端、TypeScript 类型检查、契约漂移检查与 git diff --check 均通过；代码尚未提交/推送。
