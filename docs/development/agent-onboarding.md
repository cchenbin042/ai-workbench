# 知序：项目接手指南

> 整理日期：2026-10-25（Asia/Shanghai）。
> 面向读者：首次接手或跨会话继续开发的智能体。
> 代码快照：T008 完成于工作区（基于 `dda737476b00206a32402ba59ff90fb8e237f6b9`），分支 `codex/backend-tasks`；T006～T008 的改动均未提交。这是定位信息，不是要求切换分支或重置工作区。
> 当前判断：M1 的桌面壳、持久化、后端任务协调器与工作区/真实资料链路已实现；DeepSeek 接入与"资料到题库"的生成闭环尚未实现。

## 1. 五分钟阅读顺序

1. 阅读本文件，建立产品、架构和实现边界的整体认识。
2. 阅读 [开发任务总览](master-plan.md)，确认最新焦点、任务编号和缺口；本文件可能滞后于后续开发。
3. 阅读总览指向的当前任务明细，区分计划、实际改动和验证记录。最近完成的业务任务是 [T008：工作区、真实资料与来源快照](tasks/T008-2026-10-25-workspaces-materials.md)。
4. 按任务查阅 [PRD](../product/prd-ai-workbench-v1.md)、[技术方案](../technical/technical-design-v1.md) 和 [M1 实施计划](../superpowers/plans/2026-10-18-ai-workbench-m1-plan.md)。
5. 执行 `git status --short`、`git branch --show-current` 和 `git log -5 --oneline`，再读取目标模块和测试。不要从本文推导提交、推送或合并授权。

来源分工：PRD 定义产品行为，技术方案定义工程约束，契约和代码体现实际接口，任务明细记录实现与验证，总览管理开发进度。若发现它们互相矛盾，应定位差异并记录，不能把旧方案中的“待创建”或旧测试数量直接当作现状。

## 2. 产品是什么

知序是面向 Windows 的个人 AI 工作台，主要服务有 Java 背景、正在学习 Python/Agent 的个人开发者。借鉴 WorkBuddy 的导航、任务、资料和成果组织，业务逻辑自行实现。

首版 P0 主流程：

```text
选择资料或岗位主题 → 生成候选题 → 用户检查、编辑并选择入库
→ 文字/语音面试 → 基于回答依据的报告 → 手动复习 → 重开继续
```

- 模型方向是 DeepSeek 云端，本机不运行大模型。
- 资料、题库、报告、笔记和草稿本地持久化；生成、追问和转写依赖云端能力。
- 候选题必须经过检查才能入库；模型输出不能直接成为已验证知识。
- P1 才扩展课程学习复盘；不把播放器黑屏、原视频恢复或音画同步写成已解决。
- 首版不包含通用电脑控制、执行学习项目代码、通用编程代理、后台调度或团队系统。首页“开发/设计”是分类入口，不代表这些能力已经具备。

里程碑顺序是 D0 设计 → M1 真实建题 → M2 文字训练闭环 → M3 语音、MCP 与发行收口 → M4 课程学习。D0 已完成，M1 进行中，其余业务阶段待开始。

## 3. 架构与职责边界

```text
React renderer（页面、表单、临时输入、状态展示）
  → window.workbench（受限 preload bridge）
  → Electron main（窗口、IPC 校验、Python 子进程生命周期）
  ⇄ stdio JSON-RPC（UTF-8 JSON Lines）
Python application（严格契约、任务协调、业务提交）
  → SQLite（单写线程、事务、迁移和本地数据）
  → 后续接入：资料范围、DeepSeek、面试流程、ASR、MCP
```

- **正式项目没有 HTTP/FastAPI/WebSocket 后端端口。** 原型的静态 HTTP 服务不属于正式通信链。
- renderer 不直接读文件、写数据库、启动进程或接触供应商密钥。
- preload 只暴露固定方法；main 再校验发送窗口、主 frame、来源、方法和参数。
- Python 承担业务状态、幂等、来源快照与事务；main 不维护题库或面试业务状态。
- 当前不使用 ORM、Redis、向量库、LangChain/LangGraph 或通用编排框架。后端依赖保持精简，不因设计文档提到某个库就假定它已安装。

运行基线来自仓库锁文件与已有记录：Python 3.14、Node.js 24、Electron 44.9.0、React 19.3.1、TypeScript 7.0.2、Vite 8.3.4、Pydantic 2。版本是本项目记录，不是对外部最新版本的声明；安装以锁文件为准。

## 4. 从哪里读代码

| 路径 | 职责与接手提示 |
| --- | --- |
| [apps/desktop/src/main/index.ts](../../apps/desktop/src/main/index.ts) | 桌面入口；单实例、窗口、`app://workbench`、CSP、安全选项、服务启停 |
| [service-process.ts](../../apps/desktop/src/main/service-process.ts) | Python 启动、请求超时、握手、心跳、状态与进程退出 |
| [main/bridge.ts](../../apps/desktop/src/main/bridge.ts) / [ipc-policy.ts](../../apps/desktop/src/shared/ipc-policy.ts) | IPC 注册与来源、方法白名单检查 |
| [preload/index.ts](../../apps/desktop/src/preload/index.ts) / [shared/bridge.ts](../../apps/desktop/src/shared/bridge.ts) | `window.workbench`、公开 RPC 列表、状态与事件类型；白名单含 `system.ping`、`workspaces.*` 与 `materials.*` |
| [renderer/App.tsx](../../apps/desktop/src/renderer/App.tsx) / [navigation.ts](../../apps/desktop/src/renderer/navigation.ts) / [Launcher.tsx](../../apps/desktop/src/renderer/components/Launcher.tsx) | 共用导航、页面切换、模块选择和内存中的首页草稿；资料库页已接真实数据，其余业务页仍为占位 |
| [main/dialogs.ts](../../apps/desktop/src/main/dialogs.ts) | 目录/文件选择对话框，把结果经 `internal.registerGrant` 登记为 grant 后只返回 grant ID；e2e 用 `WORKBENCH_TEST_DIALOG_DIR` 替身（打包态禁用） |
| [renderer/pages/WorkspacePage.tsx](../../apps/desktop/src/renderer/pages/WorkspacePage.tsx) | 资料库正式页：空间、目录关联、元数据清单、预览、导入、新鲜度 |
| [workbench/__main__.py](../../services/workbench/src/workbench/__main__.py) | `python -m workbench` 入口、RPC 注册、服务生命周期、任务恢复和事件推送 |
| [rpc.py](../../services/workbench/src/workbench/rpc.py) | JSON Lines 分帧、大小限制、请求分发和安全错误响应 |
| [contracts.py](../../services/workbench/src/workbench/contracts.py) | Pydantic DTO 与业务错误；严格类型、拒绝额外字段 |
| [storage.py](../../services/workbench/src/workbench/storage.py) | SQLite 单写线程、`transaction`、`write_once`、草稿、迁移备份 |
| [tasks.py](../../services/workbench/src/workbench/tasks.py) | `TaskService`；FIFO、执行代次、取消、检查点、恢复与事件 |
| [paths.py](../../services/workbench/src/workbench/paths.py) | Windows 路径安全：规范化、段包含、reparse/UNC/ADS 拒绝、读取前后复核与编码探测 |
| [workspaces.py](../../services/workbench/src/workbench/workspaces.py) / [materials.py](../../services/workbench/src/workbench/materials.py) | 工作区与目录关联；grant 注册表、资料导入、不可变版本、预览与新鲜度 |
| [migrations/](../../services/workbench/src/workbench/migrations) | `0001_core.sql`～`0003_materials.sql`；当前数据库 schema 为 3 |
| [contracts/](../../contracts) | Python 导出的 JSON Schema 和生成的 TypeScript 类型 |
| [services/workbench/tests/](../../services/workbench/tests) / [tests/e2e/](../../tests/e2e) | 后端真实 SQLite/子进程测试，桌面 Playwright 检查 |
| [scripts/](../../scripts) | Windows 安装、构建、契约导出与验证脚本 |
| [prototypes/workbench-ui/](../../prototypes/workbench-ui) | 独立交互原型，用于设计参考，使用示例数据和 localStorage |

`analysis/`、`output/`、依赖与构建产物受 `.gitignore` 排除；README 中的本机分析资料不保证在新克隆中存在。

## 5. 已经实现到哪里

| 能力 | 当前事实 | 尚未完成的边界 |
| --- | --- | --- |
| 桌面壳与导航 | T001/T004 已完成；共用侧栏、分类、页面占位、焦点管理、服务状态 | 多数业务页面未实现；切页保留输入不等于重启后可恢复 |
| 本地协议 | T002 已完成；握手、ping、shutdown、帧限制、错误处理和 EOF 清理 | 新业务 RPC 的前端接线逐任务进行 |
| SQLite 与草稿 | T003 已完成；WAL、单写线程、幂等写、revision、迁移备份、`drafts.save/get` | 当前只支持 `local` 范围和 owner；前端未接草稿持久化 |
| 后端任务协调 | T005 已完成；单槽 FIFO、取消、run 栅栏、同事务事件、恢复与分页查询 | 没有真实 Agent handler；`tasks.create` 未作为公开 stdio 方法注册，任务 UI 未接入 |
| 工作区与真实资料 | T008 已完成；schema=3 四表、grant 目录授权、路径安全受控读取、不可变来源快照、预览/导入分离、新鲜度检查、@materials e2e | 任务级 material_version_ids 归属校验待 Task 06 接入；"读取新版"经再次勾选导入实现，无专用快捷入口；导出/归档未做 |
| DeepSeek 与题库 | 已有 DTO、PRD 和计划 | 配置、系统密钥、真实 provider、生成、检查入库、检索导出待实现 |
| 面试、报告、复习 | 原型可表达交互，M2 有计划 | 正式业务尚未实现 |
| 语音与 MCP | 原型演示，M3 有计划 | 真实 ASR/MCP 接入与验收尚未完成 |
| 发行包 | 已有 Electron 桌面壳产物；forge.config.ts 已钉住 electron zip sha256 | PyInstaller 与服务包缺失；未验证无 Python/Node 环境运行 |

后端目前注册的公开方法是：`system.initialize/ping/shutdown`、`drafts.save/get`、`tasks.get/list/cancel/resume/continue`、`events.list`、`operations.get`、`workspaces.create/list/listLinks/linkDirectory/unlinkDirectory`、`materials.listDirectory/importFiles/importText/list/get/checkFreshness/previewFile`。另有仅 main 可调的 `internal.registerGrant`（选择凭据登记）。公开不等于前端已接：桌面 bridge 白名单当前放行 `system.ping`、`workspaces.*` 与 `materials.*`，任务类方法尚未开放。

数据库现有表：`schema_migrations`、`operations`、`drafts`、`notes`、`tasks`、`task_runs`、`task_events`、`workspaces`、`directory_links`、`materials`、`material_versions`。`notes` 已建表但未开放业务 RPC。

## 6. 后续修改必须保留的机制

### 协议和契约

- stdout 只输出协议帧，诊断走 stderr；不要在 stdout 打调试日志。单帧上限为 8 MiB。
- `id` 是单次 RPC 标识；`operation_id` 是业务幂等标识。超时或 ACK 丢失时使用原操作 ID 和原参数查询或重试，不把超时当成事务失败。
- 业务 DTO 以 Python 为源，变更后导出 Schema 并生成 TypeScript。手写的桌面 bridge 白名单仍需单独接线，生成类型不会自动开放 IPC。
- 初始化当前返回 `protocol_version=1`、实际迁移得到的 `schema_version=3` 和每进程固定的 `service_instance_id`。旧文档中的 schema=1/2 是历史记录。

### 存储和任务

- SQLite 使用单写线程、WAL、`synchronous=FULL`、外键和忙等待。事务回调保持同步，网络请求不占写事务。
- `Storage.write_once` 将业务变更和操作结果放在同一事务；提交后才确认成功。RPC 等待者取消不能撤销已接受的数据库写入。
- 修改已应用迁移会触发 checksum 校验；新增迁移顺序编号，SQL 保持 LF，并保留迁移前备份机制。
- `TaskService` 只有一个主动执行槽。进入 `waiting_user` 或终态释放槽；取消中尚未停止的 handler 仍占槽。
- 业务结果经 `commit_run` 校验当前 run 后提交；取消撤销执行代次，迟到结果应被 `STALE_RUN` 拒绝。
- 重启将旧 queued/running/cancelling 标为 interrupted，不自动重发任务。用户显式 resume；waiting_user 检查点和终态保留。
- 事件与业务状态同事务提交，通知尽力推送。断线用 `events.list(after_seq)` 补齐，按 seq 去重，实时通知还要核对服务实例。
- 短暂存储失败只重试本地获取槽或收尾，不借此重复调用模型或工具。后续实体落地时补真实空间、Agent 版本和资料归属校验。

### 正式资料与安全边界

T008 已实现以下要求（不要回退）：目录授权只经 main 对话框登记为 grant（`internal.registerGrant`，renderer 白名单拒绝）；预览与选入分开（`materials.previewFile` 不落库，`importFiles` 生成不可变版本）；资料默认只读；单份文本上限 200000 字节、单批合计 1000000 字节；模型上下文预算另行校验。历史来源版本不可变，同路径重新导入 hash 相同不新增版本，变化则 version_no+1；关联移除后 `check_freshness` 不再触碰文件系统，只用快照回答。

仍是后续实现要求：模型上下文预算在 Task 06 接入；资料/题目等实体的任务归属与 Agent 版本校验在 Task 06 按真实引用补齐。DeepSeek 密钥按方案进入系统密钥存储，数据库保存引用；不能把密钥、私人资料或完整输入写进日志、文档和测试证据。当前 Windows 进程树清理使用 `taskkill /T`，Job Object 仍是发行阶段缺口。

## 7. 运行与检查

以下命令均在仓库根目录执行，环境是 Windows PowerShell。首次安装需要 Node.js 24 与 Python 3.14；现有 `.venv` 和 `node_modules` 不需要为阅读项目重新安装。

环境提示：T006 文档检查阶段曾出现 `.venv` Python 找不到基础 CPython 的启动问题；T008 会话（2026-10-25）已确认 `.\.venv\Scripts\python.exe` 可正常运行（3.14.2），未另定位原因。运行测试前仍应先执行版本确认，不因目录存在就默认可运行。

```powershell
# 首次安装两端依赖
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/bootstrap.ps1

# 启动开发桌面，main 会启动项目 Python 服务
npm --prefix apps/desktop start

# 后端完整检查：依赖、pytest、compileall、Schema 漂移
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-backend.ps1

# 前端类型与契约检查
npm --prefix apps/desktop run typecheck
npm --prefix apps/desktop run contracts:types:check

# 修改 Python DTO 后更新生成产物，再执行上述检查
.\.venv\Scripts\python.exe scripts/export-contracts.py
npm --prefix apps/desktop run contracts:types

# 桌面检查：npm 的 pretest:e2e 会先构建桌面包，并启动测试窗口
npm --prefix apps/desktop run test:e2e -- --grep '@shell|@unit|@nav'
```

单独调试后端：

```powershell
.\.venv\Scripts\python.exe -u -m workbench --data-dir 'D:\workbench data'
```

它等待 stdin 的 JSON-RPC，不会打开网页。数据落在 `<data-dir>/data/workbench.sqlite3`，日志在 `<data-dir>/logs/`，迁移备份在 `<data-dir>/backups/`。桌面默认使用 Electron userData，可由 `WORKBENCH_DATA_DIR` 指定；测试应使用独立临时目录。协议样例见 [后端 README](../../services/workbench/README.md)。

打包判断要区分：`npm --prefix apps/desktop run package` 可成功生成桌面壳；完整 `scripts/build.ps1 -Stage M1` 要求内含 Python 服务。当前缺少 `.venv/Scripts/pyinstaller.exe` 和 `services/workbench/dist/workbench-service`，不能将 shell-only 构建当作可发行版本。`scripts/verify.ps1 -Stage M1` 也会检查服务包；其现有脚手架检查不覆盖尚未实现的完整业务验收。

## 8. 验证证据与适用范围

| 时间与来源 | 命令或检查 | 已知结果 | 能证明什么 |
| --- | --- | --- | --- |
| 2026-10-25，T008 会话实际执行 | `scripts/verify-backend.ps1` | 132 passed；pip check、compileall、Schema 一致 | 当前后端基线通过（含 T008 的 12 项资料测试）；不含真实云服务 |
| 2026-10-25，同一会话 | desktop `typecheck`、`contracts:types:check`、`test:e2e --grep "@shell&#124;@unit&#124;@nav&#124;@materials"` | 退出码 0；17 passed（@materials 3 项新增） | 类型与契约一致；资料库页经真实服务完成链接/预览/导入/隔离验收；对话框为测试替身，非发行包验收 |
| 2026-10-19，T006/T007 会话 | `scripts/verify-backend.ps1` | 120 passed，26.67s | 当时基线；schema=2 时代记录 |
| 2026-10-18，[T005 最终验收](tasks/T005-2026-10-18-backend-tasks.md) | `@shell`、`@unit`、`@nav` | 历史记录为 14 passed | 桌面壳、通信与导航；现由 17 项覆盖 |

尚未核验或尚未实现：真实 DeepSeek/ASR/MCP、候选题生成到题库闭环（Task 05～09）、前端草稿与任务联调、Python 服务发行包、无开发环境的安装运行、Job Object 子进程树管理。后续接手应按实际变更重新运行必要检查，不能无限沿用本文结果。

T008 会话中 Python 3.14.2 环境可直接运行，T006 期间的启动问题未复现、未另定位；会话中段出现过 GitHub 网络不可达导致 Forge 校验文件（SHASUMS256.txt）下载失败，已通过 forge.config.ts 钉住 electron zip sha256 解决离线打包。

## 9. 推荐接续顺序

1. **M1 Task 05：DeepSeek 配置与密钥。** 接入真实 provider、系统密钥存储（keyring + Windows 后端白名单）、连接测试和错误处理；`providers/`、`0004_providers.sql`、SettingsPage 按计划创建。不提前伪造生成结果；缺账号时记录 blocked。
2. **Task 06～07：候选题与题库。** 接上下文预算、来源校验（material_version_ids 归属校验在这里补齐）、候选检查、事务入库、版本、搜索和 JSON 导出。
3. **Task 08～09：草稿与端到端验收。** 完成草稿 ACK、错误/离线状态与 M1 实际切片验收；前端 TaskPage/useTask 和后端任务 RPC 的接入也仍需落实。
4. **保留 G01/G04 的发行工作。** Python 打包与进程树管理是独立缺口；不能因业务开发继续而将其默认为已解决。

任务台账编号 `Txxx` 与实施计划的 `Task xx` 是两套编号。本次新增 T006 是文档支撑任务，不能据此将下一项业务任务误认成 Task 06；下一个新开发任务需检查索引后分配未占用的 T 编号。

## 10. 协作与维护约定

- 回复用中文，代码与标识符保持英文；沿用既有模块和测试方式。
- 开发前读总览和当前明细；任务结束用 `dev-task-tracker` 回写。文档维护不等于新业务交付。
- 保留已有未提交改动；提交、推送、合并和部署依用户授权判断，历史推送记录不代表长期授权。
- 原型只作视觉和交互参考，不能把示例数据或 localStorage 直接接成正式存储。
- 本文件在架构、RPC 可达范围、schema、主线或验证基线发生实质变化时更新，并注明日期与证据。动态进度仍维护在总览和任务明细。
- [runtime-baseline.json](runtime-baseline.json) 保存早期脚手架快照，其中旧分支、57 项后端和 9 项桌面测试不是当前全量状态；同样不要用 README 的历史原型说明覆盖新代码事实。

