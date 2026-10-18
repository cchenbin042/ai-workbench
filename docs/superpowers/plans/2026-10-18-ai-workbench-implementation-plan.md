# 知序 P0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Windows 上交付“真实资料 → 候选题 → 本地题库 → 文字/语音面试 → 报告 → 手动复习 → 重开继续”的 P0 可用版本。

**Architecture:** Electron 主进程提供受限平台入口，React 负责界面，Python 本地服务拥有状态、范围与事务。renderer → main 使用 Electron IPC，main → Python 仅使用 stdio JSON-RPC；不新增本机 HTTP 服务。按三个可独立验收的增量计划实施，共用既有底座。

**Tech Stack:** Electron、React/TypeScript、Vite、Python 3.14、asyncio、SQLite、httpx、Pydantic、keyring、官方 Python MCP SDK、pytest、Playwright、PyInstaller、Electron Forge。

**Spec:** [技术方案 v1.0](../../technical/technical-design-v1.md)、[PRD v1.0](../../product/prd-ai-workbench-v1.md)、[UI 基线](../../product/2026-10-18-workbench-ui-design.md)。

日期：2026-10-18（Asia/Shanghai）。**状态：实施方案已编写，Task 01～22 均未开始。** 所有命令、测试和提交均为后续实施步骤，本轮没有创建正式工程、安装依赖或执行产品验收。当前目录没有 Git 元数据，也没有已采用的开发台账；本计划不伪造历史提交或已完成任务。

## Global Constraints

- 保留全局共用侧栏、中央“办公 / 开发 / 设计”布局，原型仅作参考，不把示例题和 localStorage 数据导入正式库。
- 单用户、多工作区、一个主窗口；原项目永远只读；不修改 `D:\python\tiangong_agent` 进行验收。
- Electron 44.9.0、React 19.3 系列、Node.js 24 LTS、Python 3.14 为技术方案的建议起点。Task 01 核验依赖并锁定精确版本，后续不静默换主版本。
- 无 ORM、Redis、向量数据库、LangChain/LangGraph 编排引擎；不增加账号、团队、插件市场、自动调度、远程 MCP OAuth、通用代码执行或实时双向语音。
- JSON-RPC 单帧上限 8 MiB；普通命令超时 10 秒；心跳每 5 秒一次、连续 3 次失败提示；启动 15 秒超时，退出清理 5 秒后进入显式强退分支。
- SQLite `foreign_keys=ON`、WAL、`synchronous=FULL`、`busy_timeout=5000`；单写线程，网络等待不持事务；迁移前 backup API 备份，版本不可原地覆盖。
- 一次最多一个主动 AI 执行，等待用户不占槽；取消撤销 active_run_id；所有生成结果提交前重新验证 run。
- 写命令按“请求形状与归属 → 幂等结果 → 新操作当前状态/revision → 写入”执行。operation_id 与 RPC id 分开，答案/候选另有实体唯一约束。
- 单份文本 200000 字节、本次 1000000 字节；输入软预算 24000 tokens、输出默认最多 8000 tokens、至少 20% 余量；不静默截断资料。
- 建题默认 10 道、范围 1～30；超过 10 道分批，每批最多 10 道；结构修复请求最多 1 次。
- 面试默认训练、20 分钟、5 道主问题、每题最多 2 次追问；时间和题数为软目标，手选不足不重复凑数。
- 语音最多 180 秒、8 MiB，优先 `audio/webm;codecs=opus`、64 kbps；音频块最多 256 KiB。停止后转写，用户核对文字后主动提交。
- 文本/ASR 默认 connect=10 秒、idle=60 秒、总时限=180 秒；仅明确 429/5xx 且无内容时最多自动重试 1 次；未知副作用不自动重放。
- 普通 Agent 最多 6 个模型轮次、每轮最多 3 个工具、总共最多 8 次工具调用、10 分钟执行时限；工具默认 30 秒、配置上限 120 秒。
- MCP 输出给模型最多 64 KiB、返回帧总量上限 4 MiB；仅用户信任的本地 stdio 服务，路径校验不宣称操作系统沙箱。
- 草稿停止输入 500 ms 后保存、800 ms 内尝试；收到覆盖当前内容的 ACK 才显示已保存；不存密钥到数据库、日志或导出。
- 验证 1280×800、1536×1000 和 Windows 100%/125%/150% 缩放；本地导航 300 ms 内反馈；10000 题检索 P95≤500 ms。
- 日志每份 5 MiB、保留 5 份；迁移备份最近 5 份、手动备份不自动删除。产品反馈默认无总分，不推断声音情绪或人格。

## Review Focus

以下五类组合故障最容易在单页面测试中遗漏，已经分配到任务的具体测试；实施审阅必须核对其证据。

1. 提交成功后断线、轮次前进，再带旧 revision 重试：返回原成功结果，不能误报失败或新增答案（Task 02、11、16）。
2. 合法目录名相近、junction、文件读取过程中被替换：任何越界或不稳定快照都在上传前阻断（Task 04）。
3. 模拟模式重开及主动看参考：默认快照/事件不带答案，辅助记录成功后只返回请求级别（Task 12、15、16）。
4. 录音期间存储失败/睡眠/权限撤销、停止后取消上传：停止 tracks、保留可恢复内容，不创建答案或继续发送（Task 17、18）。
5. MCP 已写外部文件但超时，随后崩溃重启：显示 unknown，不自动再写；只清理本应用拥有的进程（Task 19、22）。

## 1. 阅读顺序与任务依赖

| 计划 | 任务 | 交付后用户能做什么 | 前置条件 |
| --- | --- | --- | --- |
| [M1：真实建题](2026-10-18-ai-workbench-m1-plan.md) | Task 01～09 | 安装、选资料、用 DeepSeek 建候选、检查入库、查询与导出 | 技术方案；真实验证时配置用户自己的文本服务 |
| [M2：文字训练闭环](2026-10-18-ai-workbench-m2-plan.md) | Task 10～16 | 文字面试、追问、反馈、报告、成果交接、回忆复习、恢复 | M1 验收通过 |
| [M3：语音与工具收口](2026-10-18-ai-workbench-m3-plan.md) | Task 17～22 | 真实语音、stdio MCP、自定义 Agent、备份恢复、P0 安装包 | M2 验收通过；真实 ASR/可信测试服务可用 |

建议 Task 01 → 02 → 03 → 04 → 05 → 06 → 07 → 08 → 09 → 10～16 → 17～22 顺序执行。先让每个增量真实可用，再进入下一阶段；不要一次铺完全部页面和空模块。接口依赖较多，推荐实施方式为当前会话逐任务执行，减少交接时的契约漂移；本轮只准备计划，不默认启动实施。

## 2. 目录、所有权与文件规则

本节所有工程路径均为**计划创建**，不是当前已存在文件。详细任务清单中的测试文件同样在对应任务创建。

分计划为减少重复采用下列固定短路径规则：`src/workbench/`、`migrations/`、`tests/test_*.py` 均相对 `services/workbench/`；`tests/e2e/` 与 `tests/fixtures/` 相对仓库根；renderer 的 pages/components/hooks 相对 `apps/desktop/src/renderer/`。`contracts.py/rpc.py/tasks.py` 等模块简称指 `services/workbench/src/workbench/` 下文件；生成契约始终位于仓库根 `contracts/`。若任务写出完整仓库相对路径，以完整路径为准。

| 位置 | 职责 | 首次建立 |
| --- | --- | --- |
| `apps/desktop/src/main/{index,service-process,bridge,dialogs,permissions}.ts` | 窗口、Python 生命周期、IPC、选择凭据、麦克风/外链 | Task 01、04、17 |
| `apps/desktop/src/preload/index.ts` | 固定方法 bridge，事件订阅取消 | Task 01 |
| `apps/desktop/src/renderer/{App.tsx,main.tsx,styles.css}`、`pages/`、`components/`、`hooks/` | 共用布局和实际页面，不复制原型全局脚本 | Task 01 起按功能创建 |
| `services/workbench/src/workbench/{__main__,rpc,contracts,storage,tasks}.py` | 启动/协议、基础 DTO、事务、队列和 run 栅栏 | Task 01～03 |
| 同目录 `workspaces.py`、`materials.py`、`paths.py` | 工作区、选材、Windows 路径边界 | Task 04 |
| 同目录 `providers/{config,deepseek,asr}.py`、`context.py` | 密钥/配置、文本与 ASR 请求、上下文预算 | Task 05、06、18 |
| 同目录 `questions.py`、`flows/questions.py`、`prompts/questions.txt` | 候选整理、校验、版本、事务入库 | Task 06～07 |
| 同目录 `interviews.py`、`flows/interview.py`、`reports.py`、`reviews.py`、`artifacts.py` | 面试状态、反馈、报告、复习、普通成果 | Task 10～15 |
| 同目录 `audio.py`、`tools/{mcp,policy}.py`、`agents.py`、`flows/generic.py`、`data_admin.py` | 音频、工具授权、自定义任务、备份恢复 | Task 14、17～21 |
| `services/workbench/migrations/` | 按任务新增 SQL，不提前创建后续阶段空表 | Task 02 起 |
| `contracts/rpc.schema.json`、`contracts/generated.ts` | 从 Python DTO 生成的业务类型，不手工双写 | Task 01 建生成机制，后续任务扩展 |
| `services/workbench/tests/`、`tests/e2e/`、`tests/fixtures/` | 真实临时库/进程、桌面测试、可控外部服务 | 对应任务 |
| `scripts/{bootstrap,verify,build}.ps1`、`scripts/export-contracts.py`、`docs/development/runtime-baseline.json` | 可复现初始化、检查、打包、实际版本记录 | Task 01，逐阶段扩展 |
| `docs/development/acceptance/`、`output/verification/` | 不含凭据的验收记录和本机结果 | Task 09、16、22 |

每个任务维护自己新增 DTO 的定义与 RPC 注册，不创建通用业务框架。下游只依赖 Interfaces 区列出的函数；若实测必须改签名，先修改契约与直接调用方、补验证，再回写计划，不能让两份计划保留冲突名称。

## 3. 公共接口与测试约定

- `contracts.py` 定义 `CommandMeta(operation_id: str, method: str, scope_id: str, expected_revision: int | None)`、`DomainError(code: str, message: str, committed: bool=False)`、`ModelRequest`、`ModelResult`。ModelRequest 字段为 messages/model_id/response_format/max_tokens；ModelResult 字段为 content/finish_reason/request_id/usage。Task 20 以兼容默认值扩展工具字段。各业务 DTO 随拥有它的任务定义，禁止用未来未定义类型作接口。
- `storage.py` 提供 `async Storage.write_once(meta: CommandMeta, payload: dict, mutate: Callable[[sqlite3.Connection], dict]) -> dict`、`async Storage.read(sql: str, params: tuple=()) -> list[dict]`、`async Storage.transaction(mutate: Callable[[sqlite3.Connection], dict]) -> dict`；事务回调是同步函数，不发网络请求。只有确认调用归属的业务入口才调用 write_once。
- `tasks.py` 提供 `async TaskService.create(command: dict) -> dict`、`async TaskService.start(task_id: str) -> str`（返回 run_id）、`async TaskService.commit_run(task_id: str, run_id: str, mutate: Callable[[sqlite3.Connection], dict]) -> dict`、`async TaskService.cancel(task_id: str) -> dict`、`async TaskService.resume(task_id: str) -> dict`。附加查询方法由 Task 03 定义。
- 其他模块采用 `async operation(command: dict, ...) -> dict` 或下文具体签名，dict 在 RPC 入口先由 Pydantic DTO 校验；不因为示例用 dict 就跳过 schema。
- 测试代码块是必须实现的断言，测试名紧随 Step 1；块内结果变量由该步描述的 Given/When 构造。测试 fixture 在所列测试文件中创建，临时 SQLite 用 pytest tmp_path；禁止将演示数据或真实学习项目当作测试依赖。
- 所有 Python 测试从根目录用 `.\.venv\Scripts\python.exe -m pytest ...`；bootstrap 负责 editable 安装服务包，pytest-asyncio 用于 async 测试。npm 使用 `--prefix apps/desktop`。
- `scripts/verify.ps1 -Stage M1|M2|M3 [-Live]` 运行累计已实现用例；阶段尚不存在或测试没有收集到用例应失败，不能用 `--passWithNoTests`。-Live 未配置服务应 nonzero 并记 blocked；默认替身用例通过不能代替真实抽样。
- 新接口/业务逻辑走 Red → Green：先实现测试并确认预期行为失败，再写最小代码、运行目标测试。配置、说明和纯样式不制造无价值的镜像测试。每任务检查后单独提交具体文件，不使用 `git add .`。

## 4. 验收映射与阶段门禁

| 验收 | 实施任务 | 主要证据 |
| --- | --- | --- |
| AC01 | 04、06、09 | 实际文件范围与请求正文比对 |
| AC02 | 05、09 | 系统密钥、最小真实请求、日志脱敏 |
| AC03 | 06、07、09 | 10 道候选只入 5 道、重试仍 5 道 |
| AC04 | 06、07 | Schema 与来源失败、相似题比较 |
| AC05 | 07、09 | 筛选/零结果、10000 题基线 |
| AC06 | 10、16 | 单题计划、参数快照 |
| AC07 | 11、12、16 | 回答唯一、重试顺序、追问依据 |
| AC08 | 11、12、16 | 模式/提示/跳过/不知道 |
| AC09 | 17、18、22 | 180 秒录音、真实转写与主动提交 |
| AC10 | 17、18、22 | 拒绝设备、断网与切文字恢复 |
| AC11 | 12、13、16 | 人工核对真实回答与反馈依据 |
| AC12 | 13、16 | 题目旧版本、用户笔记、报告再生成 |
| AC13 | 15、16 | 复习去重、reveal 事务、重开辅助 |
| AC14 | 15、16 | 多次尝试、自评与时间 |
| AC15 | 03、06、12、18、19 | 取消竞态与 run 提交栅栏 |
| AC16 | 03、11、16、19、22 | 断电/管道断线、检查点、副作用 unknown |
| AC17 | 19、22 | 真实 stdio 进程与越界拒绝 |
| AC18 | 20、22 | 配置版本、交集权限、流程不可越权 |
| AC19 | 02、08、17、21 | 写失败无假成功、可复制、可重试 |
| AC20 | 14、16、20 | 新稿比较与成果快照交接 |
| AC21 | 07、13、14、22 | 完整字段导出、无密钥/旁路材料 |
| AC22 | 08、22 | Windows 尺寸、缩放与键盘 |
| AC23 | 07、08、13、15、16 | 离线本地读写与云动作保留输入 |
| AC24 | 22 | 安装包端到端完整切片与服务类型标记 |

FR01→01/04/08；FR02→04/06；FR03→06/07；FR04→07；FR05→10/11/12；FR06→17/18；FR07→13/14；FR08→15；FR09→02/03/08/16；FR10→05/18/21；FR11→19/20。门禁任务 09/16/22 不创建新业务需求，只确认前述能力真实贯通。

阶段门禁要求：累计自动检查通过、对应真实抽样有记录、阻塞项清零、说明已知限制。M1/M2 只能按相关切片验收；语音或工具未实现时不能把整个 AC24 或 P0 标完成。不按工期猜测通过日期。

## 5. 证据、提交与接续

每任务保存失败测试的原因、通过命令/输出摘要和实际改动文件；每阶段结果写入 `output/verification/<date>-<stage>/result.json`，至少含 task_ids、AC 编号、app/schema/protocol 版本、环境、live/stub、passed/failed/skipped/blocked、限制与证据路径。日志与结果不含凭据或完整私人材料。

当前没有 Git。Task 01 实施时先检查上级仓库：若本目录不属于其他仓库再初始化；若已有仓库则沿用，不覆盖历史。`.gitignore` 排除 `.venv`、node_modules、构建/运行数据、录音、凭据、`output/` 与既有大体积分析产物；需要保留的设计文档明确逐项加入。任务提交只包含实际已通过检查的源文件/测试/契约/记录，不提交本机临时日志。

中断实施时在正在执行的任务复选框下追加日期、已做/未做、实际命令和恢复入口，保留未完成复选框；不因一个测试替身通过勾选真实服务验收。遇依赖或账号阻塞，先继续本阶段不依赖它的测试，不临时换服务或开启付费账号。

后续课程 M4 仅继承材料版本、任务和成果接口；课程输入、时间对齐、语雀写入另写 P1 方案。本轮不提前创建课程解析器或语雀写入模块。

## 6. 本轮计划检查

按 writing-plans 自查 Spec coverage、Step scan、Type consistency、Review Focus、Proportion。检查产物为 [implementation-plan-verification.json](implementation-plan-verification.json)，仅证明计划结构、链接和映射检查，不表示计划中的工程测试已经执行。
