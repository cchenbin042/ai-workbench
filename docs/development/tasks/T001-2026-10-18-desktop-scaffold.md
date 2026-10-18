# T001：桌面脚手架（前端部分）

## 1. 任务信息

| 字段 | 内容 |
|---|---|
| 任务编号 | T001 |
| 类型 / 关联里程碑 | 开发任务 / M1 |
| 状态 | 已完成 |
| 创建日期 | 2026-10-18 |
| 开始日期 | 2026-10-18 |
| 最近更新 | 2026-10-18 |
| 完成日期 | 2026-10-18 |
| 最近回写 | 2026-10-18 |
| 总文档 | [master-plan.md](../master-plan.md) |
| 前置依赖 | Node.js 24.13.1、npm 11.8.0、Python 3.14.2、项目 `.venv`；后端 stdio 服务由后端工作流提供（已实现，尚未提交） |
| 需求 / 设计 / 契约 | [M1 Task 01](../../superpowers/plans/2026-10-18-ai-workbench-m1-plan.md)、[技术方案 §2/§3/§11](../../technical/technical-design-v1.md)、[后端执行计划](../../superpowers/plans/2026-10-18-backend-scaffold-plan.md) |

## 2. 目标与主线关系

建立可启动、可构建的 Windows 桌面壳，并打通 renderer → preload → Electron main → Python stdio JSON-RPC 的最小通信链，为 M1 真实建题流程提供运行底座。本任务完成脚手架能力，不推进 M1 业务里程碑；资料、DeepSeek、题库、面试等业务流仍属于后续任务。

## 3. 范围与功能点

### 包含

| 功能点 | 计划行为与验收条件 | 状态 | 实际记录 |
|---|---|---|---|
| F01 Electron 主进程与安全边界 | `app://workbench` 生产来源；contextIsolation/sandbox；CSP；权限、外链、新窗口、webview 拦截 | 已完成 | [2026-10-18 F01](#2026-10-18-f01electron-主进程安全边界与-renderer-壳) |
| F02 Preload bridge 与 IPC 策略 | 固定 bridge；公共 RPC 仅 `system.ping`；sender/frame/origin/方法/参数校验 | 已完成 | [2026-10-18 F02](#2026-10-18-f02preload-bridge-与-ipc-策略) |
| F03 stdio 服务客户端、握手与恢复 | 15 秒握手、5 秒心跳、30 秒恢复探测、入站 8 MiB 帧上限、重启入口 | 已完成 | [2026-10-18 F03](#2026-10-18-f03服务客户端握手与恢复) |
| F04 契约类型与构建/验证 | schema → TypeScript 生成与漂移检查；桌面构建；失败门禁脚本 | 已完成 | [2026-10-18 F04](#2026-10-18-f04契约类型构建与验证脚本) |

### 不包含

- PyInstaller 服务包、安装包内服务启动、无 Python/Node 环境验收（G01）。
- M1 业务页面与真实 DeepSeek/ASR 接入（G03、G05）。
- Windows Job Object 子进程树管理；当前使用 `taskkill /T` 并等待退出（G04）。
- 后端与契约文件的提交；这些文件由后端工作流维护（G02）。

## 4. 实施步骤与验收

- [x] 确认前置依赖和当前基线：Node 24、Python 3.14、项目 `.venv`、现有设计文档与 M1 计划。
- [x] 完成 F01～F04，并在每个阶段运行类型检查、构建或测试。
- [x] 执行与变更相匹配的验证：typecheck、Windows 桌面包、Playwright 单元/壳测试、契约漂移检查。
- [x] 逐项核对验收：app origin、无 Node API、CSP、IPC 白名单、服务握手、路径穿越拦截、失败门禁。
- [x] 补齐文件清单、遗留问题和接续步骤。
- [x] 回写总文档任务索引、里程碑、焦点、缺口和每日汇总。

补充验收条件：

- 生产 renderer 从 `app://workbench` 加载，`window.require` / `window.process` 不可用。
- 非公开方法（`system.shutdown`、`system.initialize`、`materials.list`）在 renderer 与主进程两侧均被拒绝。
- 后端服务可用时，状态面板显示 `已连接`、协议 1、schema 0，并能通过心跳获取延迟。
- 缺少服务包或契约 schema 时，`build.ps1` / `verify.ps1` 不得返回空成功。

## 5. 开发记录

### 2026-10-18 F01：Electron 主进程、安全边界与 Renderer 壳

- **当次状态：**已完成。
- **实际行为：**应用可从 `app://workbench` 启动；深色工作台壳、办公/开发/设计切换和服务状态面板正常渲染；外部导航、弹窗和 `webview` 被阻断；所有权限请求被拒绝。
- **实现与决策：**Electron 44 + React 19 + Vite 8；自定义 `app:` 协议服务静态文件并拒绝路径穿越；CSP 区分开发/生产；`app.setName('ZhixuWorkbench')` 固定数据目录；修正 Node 对非特殊 scheme 的 `URL.origin` 返回 `null` 的问题，显式解析 `app://host`。
- **修改文件：**`apps/desktop/src/main/index.ts`、`apps/desktop/src/renderer/App.tsx`、`components/`、`styles.css`、`forge.config.ts`、Vite 配置。
- **验证：**`npm --prefix apps/desktop run typecheck` 通过；`npm --prefix apps/desktop run package` 通过；Playwright 的 app origin、CSP、弹窗/外链、路径穿越用例通过。
- **问题与处理：**Forge Vite 对两个 `index.ts` 入口默认都输出 `index.cjs`，通过覆盖 main `fileName` 与 preload `entryFileNames` 解决。
- **下一步：**接入并验证本地服务客户端。

### 2026-10-18 F02：Preload bridge 与 IPC 策略

- **当次状态：**已完成。
- **实际行为：**renderer 只能调用 `system.ping` 和固定的 `getStatus` / `restartService`；非公开方法在 preload 和 main 两侧均被拒绝；renderer 无 Node API。
- **实现与决策：**公共方法与 sender/frame/origin 判定抽成 `ipc-policy.ts` 纯函数；main 与 preload 双层校验；`system.initialize` 收归主进程，避免 renderer 绕过握手。
- **修改文件：**`apps/desktop/src/preload/index.ts`、`apps/desktop/src/main/bridge.ts`、`apps/desktop/src/shared/{bridge,ipc-policy}.ts`。
- **验证：**`@unit` 的 sender/origin/method/params 用例 3/3 通过；`@shell` 的非公开方法拒绝用例通过。
- **问题与处理：**自定义 `app:` origin 在 Node 中为 `null`，原实现会误拒生产 IPC；已修复并加入回归断言。
- **下一步：**完成服务进程适配与恢复。

### 2026-10-18 F03：服务客户端、握手与恢复

- **当次状态：**已完成。
- **实际行为：**主进程优先使用项目 `.venv` 的 Python 启动本地服务；握手成功后显示协议/数据版本和延迟；心跳连续失败可低频探测并支持主进程重启；服务退出或协议异常时拒绝挂起请求并更新状态。
- **实现与决策：**`service-process.ts` 管理 stdio JSON-RPC、15 秒握手、5 秒心跳、3 次失败后 30 秒恢复探测、10 秒请求超时；入站使用自带有界 `JsonLineReader`，拒绝超过 8 MiB 的帧；握手失败终止子进程；退出使用 `taskkill /T` 并等待，Job Object 留给打包阶段。
- **修改文件：**`apps/desktop/src/main/service-process.ts`、`apps/desktop/src/shared/{json-line-reader,service-launch}.ts`、`apps/desktop/src/renderer/hooks/useServiceStatus.ts`、`components/StatusPanel.tsx`。
- **验证：**`@unit` 的帧上限/分片 UTF-8/venv 选择用例 3/3 通过；后端可用后，`@shell` 服务握手用例通过，状态面板显示 `已连接`、协议 1、schema 0。
- **问题与处理：**早期后端为 `NotImplementedError` 桩，握手用例失败；后端实现完成后复跑转为通过。该历史结论已在本记录中更正，不改变当时失败记录。
- **下一步：**补齐安装包内服务启动。

### 2026-10-18 F04：契约类型、构建与验证脚本

- **当次状态：**已完成。
- **实际行为：**`contracts/rpc.schema.json` 可生成 `contracts/generated.ts`；`--check` 能检测漂移；`bootstrap.ps1` / `verify.ps1` / `build.ps1` 可执行；缺少服务包或契约 schema 时脚本失败而非空成功。
- **实现与决策：**使用 `json-schema-to-typescript` 生成类型，不手写转换；验证脚本累计运行后端测试、typecheck、打包、e2e 和契约检查；`build.ps1` 默认要求服务包，`-AllowShellOnly` 仅用于显式脚手架构建。
- **修改文件：**`apps/desktop/scripts/generate-contract-types.mjs`、`scripts/{bootstrap,verify,build}.ps1`、`tests/e2e/{shell,scaffold-unit}.spec.ts`。
- **验证：**`npm --prefix apps/desktop run contracts:types:check` 通过；Playwright `@shell|@unit` 9/9 通过；`scripts/build.ps1 -Stage M1 -AllowShellOnly` 通过；严格 `-Stage M1` 因缺少 `workbench-service.exe` 按预期失败。
- **下一步：**安装 PyInstaller，生成服务包并验证安装包内握手。

## 6. 实际文件改动

| 文件 | 新增 / 修改 / 删除 | 实际用途 |
|---|---|---|
| `.gitignore` | 修改 | 忽略桌面与服务构建产物 |
| `apps/desktop/package.json`、`package-lock.json` | 新增 | Electron/React/Vite/Playwright 依赖与 npm 脚本 |
| `apps/desktop/{forge.config.ts,tsconfig.json,index.html}` | 新增 | Forge/Vite/TypeScript 配置 |
| `apps/desktop/vite.{main,preload,renderer}.config.ts` | 新增 | 三端构建、入口命名与别名 |
| `apps/desktop/src/main/{index,bridge,service-process,forge-globals.d.ts}.ts` | 新增 | 窗口、安全、IPC、服务生命周期 |
| `apps/desktop/src/preload/index.ts` | 新增 | 受限 bridge |
| `apps/desktop/src/shared/{bridge,ipc-policy,json-line-reader,service-launch}.ts` | 新增 | 公共类型、IPC 策略、帧读取、解释器选择 |
| `apps/desktop/src/renderer/**` | 新增 | React 工作台壳、状态面板、组件与样式 |
| `tests/e2e/{playwright.config,shell.spec,scaffold-unit.spec}.ts` | 新增 | 桌面与纯函数验证 |
| `scripts/{bootstrap,verify,build}.ps1` | 新增 | 安装、累计验证、构建与失败门禁 |
| `docs/development/frontend-scaffold.md`、`runtime-baseline.json` | 新增/修改 | 前端实施记录与运行时基线 |
| `contracts/rpc.schema.json`、`contracts/generated.ts` | 依赖，非本任务提交 | 后端工作流生成，本任务只消费与校验 |

提交：`0d77993 feat: bootstrap Electron desktop shell`、`ede04f2 fix: harden desktop scaffold lifecycle and IPC`。

## 7. 验证结果

| 日期 | 执行目录 / 命令或检查 | 实际结果 | 范围与限制 |
|---|---|---|---|
| 2026-10-18 | 仓库根 / `npm --prefix apps/desktop run typecheck` | 通过 | 静态类型检查 |
| 2026-10-18 | `apps/desktop` / `npm run package` | 通过，产物 `out/ZhixuWorkbench-win32-x64` | shell-only，未含服务包 |
| 2026-10-18 | `apps/desktop` / `node scripts/run-playwright.mjs --grep '@shell\|@unit'` | 9/9 通过 | 含真实本地服务握手；不含真实 DeepSeek/ASR |
| 2026-10-18 | 仓库根 / `.venv/Scripts/python.exe -m pytest services/workbench/tests -q` | 54 passed | 后端工作流提供的依赖证据 |
| 2026-10-18 | `apps/desktop` / `npm run contracts:types:check` | 通过 | schema 由后端工作流生成 |
| 2026-10-18 | 仓库根 / `scripts/build.ps1 -Stage M1 -AllowShellOnly` | 通过 | 显式 shell-only |
| 2026-10-18 | 仓库根 / `scripts/build.ps1 -Stage M1` | 按预期失败 | 缺少 `resources/workbench-service/workbench-service.exe` |

历史说明：同日早期后端仍为 `NotImplementedError` 桩时，`@shell` 为 4 通过 / 1 失败 / 1 跳过；后端实现完成后的最新结果为 9/9 通过。旧失败记录保留在上述开发记录中，不伪装为从未发生。

## 8. 遗留问题与接续步骤

| 问题 / 未完成项 | 影响与恢复条件 | 后续任务或步骤 |
|---|---|---|
| 安装包缺本地服务 | 严格构建失败，打包后无法握手 | 安装 PyInstaller，生成 onedir 服务包，复跑严格构建与打包内握手 |
| 后端/契约文件未提交 | 当前仅在工作区可用 | 由后端工作流提交；本任务不代提交 |
| M1 业务流未开始 | 资料、DeepSeek、候选、题库、导出均未实现 | 按 M1 Task 02～09 顺序实施 |
| Job Object 未实现 | 强制退出时极端情况下可能残留孙进程 | 在发行包任务中补齐并做故障注入 |
| 真实 DeepSeek/ASR 未配置 | 真实生成、转写和用量未验证 | 配置用户服务后执行真实样本；缺账号时记受阻 |

接续入口：下一次先读 [master-plan.md](../master-plan.md) 的缺口与焦点，再读本文件第 8 节；从“M1 服务打包与安装验收”开始，先确认 `.venv/Scripts/pyinstaller.exe` 与服务包路径，再执行严格构建。

## 9. 回写总文档摘要

- **回写日期：**2026-10-18。
- **任务状态：**已完成（前端脚手架范围内）。
- **完成的功能点：**F01 Electron 主进程与安全边界；F02 Preload bridge 与 IPC 策略；F03 服务客户端、握手与恢复；F04 契约类型、构建与验证脚本。
- **里程碑变化：**M1 从设计基线推进到桌面/本地服务脚手架贯通；M1 仍未完成，业务流与服务打包未交付。
- **新增 / 解除的阻塞与范围变化：**解除开发态服务握手阻塞（后端已实现并通过 54 项测试）；保留服务打包阻塞；新增后端/契约文件未提交的依赖说明。
- **下一步：**建立 M1 服务打包与安装验收任务，完成后进入 M1 Task 02～09。
