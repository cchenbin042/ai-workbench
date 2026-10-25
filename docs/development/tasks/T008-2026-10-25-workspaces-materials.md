# T008：工作区、真实资料与来源快照（M1 Task 04）

## 1. 任务信息

| 字段 | 内容 |
| --- | --- |
| 任务编号 | T008 |
| 类型 / 关联里程碑 | 后端 + 桌面开发 / M1 Task 04 |
| 状态 | 已完成 |
| 创建日期 | 2026-10-25 |
| 开始日期 | 2026-10-25 |
| 最近更新 | 2026-10-25 |
| 完成日期 | 2026-10-25 |
| 最近回写 | 2026-10-25 |
| 总文档 | [master-plan.md](../master-plan.md) |
| 前置依赖 | T005（后端任务协调器，提交 dda7374）；T006/T007 文档未提交改动保留在工作区 |
| 需求 / 设计 | [M1 Task 04](../../superpowers/plans/2026-10-18-ai-workbench-m1-plan.md)、[技术方案 §3.2/6](../../technical/technical-design-v1.md) |

## 2. 目标和范围

建立空间隔离的工作区与真实资料链路：目录授权只经 main 对话框登记为 grant；预览（读正文不落库）与选入（生成不可变 material_version）分开；路径安全（真实路径段包含检查、拒绝 junction/reparse/UNC/ADS、读取前后 stat 与 realpath 复核）；单份 200000 字节、单批合计 1000000 字节；UTF-8/BOM 解码失败可指定编码重读；关联移除后不再触碰文件系统，仅用快照回答。

使用 dev-task-tracker / TDD 流程：先写 12 项失败测试确认 Red，再实现转 Green。本次会话内完成，未提交（提交需用户授权）。

## 3. 功能点

| 编号 | 行为与验收 | 状态 |
| --- | --- | --- |
| F01 | 迁移 0003：workspaces / directory_links / materials / material_versions，schema=3 | 已完成 |
| F02 | 路径安全与受控读取（paths.py）：段包含、reparse 拒绝、替换检测、编码探测 | 已完成 |
| F03 | 工作区与目录关联（workspaces.py）：创建/列表/关联/移除/列出关联，grant 绑定与过期 | 已完成 |
| F04 | 资料导入与快照（materials.py）：importText/importFiles/listDirectory/preview/get/checkFreshness，版本不可变、同 hash 不新增版本、跨空间拒绝 | 已完成 |
| F05 | RPC 注册与契约导出：公开方法入 capabilities 与桌面白名单，internal.registerGrant 仅 main 可调 | 已完成 |
| F06 | 桌面端：dialogs.ts（chooseDirectory/chooseFiles）、preload/bridge 白名单、WorkspacePage、Sidebar 文案 | 已完成 |
| F07 | e2e @materials：真实目录链接、预览、仅导入选中文件、移除不删原文件、空间隔离 | 已完成 |

## 4. 实施与验收

- [x] 建立行为测试并确认 Red（12 项 NotImplementedError）。
- [x] 实现后端三个模块、迁移与 RPC 注册。
- [x] 后端全量 132/132，契约 schema 与 TypeScript 无漂移。
- [x] 桌面 typecheck、契约类型检查、e2e 全量 17/17（@shell|@unit|@nav|@materials）。
- [x] 回写任务明细、总览与接手指南。

## 5. 开发记录与决策

### 2026-10-25 / 实施

- Ruling: 计划中的 renderer `pages/HomePage.tsx` 未单独创建——T004 的 Launcher 已覆盖首页壳，本任务只新增资料库页；该偏差记录于此，不代表首页能力缺失。
- Ruling: `import_files(command, store, grants=None)` 的 grants 为可选参数：link 流程不依赖注册表，文件 grant 流程必须提供；与计划签名 `import_files(command, store)` 兼容。
- Ruling: 文件读取全部发生在存储事务之外（read → 单次 write_once 事务插入），失败整批不落库。
- Ruling: 目录关联唯一性用部分唯一索引 `(workspace_id, root_key) WHERE removed_at IS NULL`，允许移除后重新关联；root_key 为 realpath 后 casefold 字符串，解决 Windows 大小写。
- Ruling: 超限错误码在 handler 层抛 `CONTEXT_TOO_LARGE`（DTO 校验只能给 -32602），与计划测试断言一致。
- Ruling: 资料匹配键 source_key = 规范路径 casefold；同路径再次导入时 hash 与当前版本相同则不新增版本，不同则 version_no+1，历史版本不可变。
- Ruling: `check_freshness` 对文件资料按 source_json 的 root_key 匹配有效关联；无关联（曾关联已移除或 files-grant 导入）返回 snapshot_only 且零文件系统访问（测试以 probe_stat 计数为证）。
- Ruling: 排除规则：目录 `.git/node_modules/.venv/venv/__pycache__/target/build/dist`，文件 `.env*`、凭据扩展/名称、非白名单扩展（`.md/.txt/.json/.py/.java`）；清单根本不展示被排除项，导入授权（grant/link）是第二道闸。
- Ruling: `internal.registerGrant` 注册于 Python 路由但不在 capabilities；桌面 `PUBLIC_RPC_METHODS` 不放行，e2e 断言 renderer 调用被拒。
- Ruling: e2e 对话框用 `WORKBENCH_TEST_DIALOG_DIR` 环境变量替身（`app.isPackaged` 时禁用）；正式链路仍走 `dialog.showOpenDialog` → `internal.registerGrant` → grant ID。
- Ruling: 修正 4 项既有迁移测试的构造顺序：真实 0003 存在后，合成迁移目录需在首次 open 前 monkeypatch，使数据库先停在 schema 2；伪造"更新数据库"改用 version=4。
- Deviation: 会话中段 `electron-forge package` 出现 `SHASUMS256.txt` 联网失败（@electron/get 对校验文件始终 cache Bypass）；在 forge.config.ts 钉住 electron zip 的官方 sha256（`download.checksums`）后离线可打包，同时收紧供应链。该 zip 哈希来自 Oct 18 经 @electron/get 校验过的缓存。

## 6. 实际文件改动

- `services/workbench/src/workbench/paths.py`：路径规范化、段包含、逐组件 reparse 检查、受控读取（stat/身份/realpath 三重复核）、编码探测（BOM/UTF-8/NUL、白名单重编码）。
- `services/workbench/src/workbench/workspaces.py`：工作区 CRUD（create/list/listLinks）、linkDirectory/unlinkDirectory。
- `services/workbench/src/workbench/materials.py`：GrantRegistry、register_grant、listDirectory（排除+reparse 跳过+上限截断）、importFiles/importText、list/get、previewFile、checkFreshness。
- `services/workbench/src/workbench/migrations/0003_materials.sql`：4 表 + 2 索引 + 1 部分唯一索引。
- `services/workbench/src/workbench/contracts.py`、`__main__.py`：新 DTO 与 13 个公开方法 + 1 个内部方法注册；capabilities 更新。
- `contracts/rpc.schema.json`、`contracts/generated.ts`：导出更新。
- `apps/desktop/src/main/dialogs.ts`（新增）、`index.ts`（接线）、`shared/bridge.ts`、`preload/index.ts`、`forge.config.ts`（校验和钉住）。
- `apps/desktop/src/renderer/pages/WorkspacePage.tsx`（新增）、`App.tsx`、`components/Sidebar.tsx`、`components/PlaceholderPage.tsx`（删除已不可达的 WorkspacePlaceholder）、`styles.css`。
- 测试：`services/workbench/tests/test_materials.py`（新增 12 项）、`test_storage.py`（schema=3、表集合、4 项迁移测试修正）、`test_service_process.py`（schema=3）；`tests/e2e/materials.spec.ts`（新增 3 项）、`shell.spec.ts`（schema=3、拒调方法改 internal.registerGrant）、`navigation.spec.ts`（资料库正式页断言）、`support/workbench-app.ts`（支持注入环境变量）。

## 7. 验证

| 命令 / 检查 | 结果 | 限制 |
| --- | --- | --- |
| scripts/verify-backend.ps1 | 132 passed（任务 120 + 新增 12）；pip check、compileall、schema 一致 | 真实 SQLite/子进程/临时目录，不含真实云服务 |
| pytest test_materials.py | 12 passed（先 Red：12 项 NotImplementedError） | junction 用 `_winapi.CreateJunction` 真实创建 |
| npm desktop typecheck / contracts:types:check | 退出码 0 | — |
| npm desktop test:e2e --grep `@shell&#124;@unit&#124;@nav&#124;@materials` | 17 passed（@materials 3 项为新用例） | 对话框经测试环境变量替身；不是发行包验收 |
| Python 环境 | `.venv` Python 3.14.2 本会话可直接运行；T006 期间的启动问题未复现，未另定位 | — |

## 8. 遗留与接续

- 下一个业务任务为 M1 Task 05：DeepSeek 配置、系统密钥与文本请求；Task 06～07 候选题与题库按计划接续。
- "读取新版"当前经 UI 再次勾选导入实现（版本由服务端去重/递增），未做单键快捷入口；G01 服务打包、G04 Job Object 独立保留。
- 材料 owner/任务归属校验在 Task 06 接入 material_version_ids 时按方案补真实引用校验。
- T006/T007 的文档改动仍为未提交状态；本任务代码同样未提交，等待用户授权后一并处理。
