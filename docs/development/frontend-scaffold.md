# 前端脚手架实施记录

日期：2026-10-18（Asia/Shanghai）。状态：桌面壳与受限 bridge 已可启动、已构建；本地服务握手仍被后端脚手架阻塞。

范围依据：[M1 Task 01](../superpowers/plans/2026-10-18-ai-workbench-m1-plan.md)、[技术方案](../technical/technical-design-v1.md)、[后端脚手架计划](../superpowers/plans/2026-10-18-backend-scaffold-plan.md)。本轮只交付前端部分，不把父计划 Task 01 标为整体完成。

## 已交付

| 区域 | 内容 |
| --- | --- |
| Electron 主进程 | 单实例锁、窗口、`app://workbench` 生产来源、CSP、权限拒绝、外链/新窗口拦截、Python 子进程生命周期 |
| Preload bridge | 公共 RPC 只保留 `system.ping`；另外固定暴露 `getStatus` / `restartService`；`subscribe` 返回取消订阅函数；不暴露 Node API |
| Renderer | React 19 + Vite，深色工作台骨架、三模块切换、主进程状态快照、重连按钮、键盘焦点与窄屏堆叠 |
| 服务进程适配 | stdio JSON-RPC 客户端、15 秒握手、5 秒心跳/连续 3 次失败后 30 秒低频探测、入站 8 MiB 帧上限、10 秒普通请求超时、退出清理 |
| 启动解释器 | 非打包态优先使用项目 `.venv` 的 Python；不存在时才回退 `py -3.14`；可用 `WORKBENCH_PYTHON` 覆盖 |
| 契约类型 | `json-schema-to-typescript` 生成器与 `--check` 漂移检测；等待后端导出 `contracts/rpc.schema.json` |
| 测试 | `tests/e2e/shell.spec.ts`：app origin、无 Node API、CSP、新窗口/外链拦截、协议穿越、服务握手、契约漂移；`tests/e2e/scaffold-unit.spec.ts`：IPC 策略、帧上限、venv 选择 |
| 脚本 | `scripts/bootstrap.ps1`、`scripts/verify.ps1`、`scripts/build.ps1` |

## 命令

```powershell
# 安装（后端脚本存在时优先复用）
powershell -NoProfile -File scripts/bootstrap.ps1

# 类型检查与构建
npm --prefix apps/desktop run typecheck
# 后端服务包尚未生成时，显式允许 shell-only 构建
powershell -NoProfile -File scripts/build.ps1 -Stage M1 -AllowShellOnly

# e2e（先构建；非打包态优先使用项目 .venv 的 Python 启动后端）
npm --prefix apps/desktop run test:e2e -- --grep "@shell|@unit"

# 阶段检查（后端测试当前仍为 Red，因此 M1 整体不会通过）
powershell -NoProfile -File scripts/verify.ps1 -Stage M1
```

Electron 二进制默认使用 `https://npmmirror.com/mirrors/electron/` 镜像；如网络可用可覆盖 `ELECTRON_MIRROR` / `ELECTRON_CUSTOM_DIR`。

## 当前验证

- `npm run typecheck`：通过。
- `npm run package`：通过，产物 `apps/desktop/out/ZhixuWorkbench-win32-x64`，主进程 `.vite/build/main.cjs`，preload `.vite/build/preload.cjs`。
- Playwright `@unit`：3 项通过（IPC sender/origin/method/params、入站帧上限与分片 UTF-8、venv 启动选择）。
- Playwright `@shell`：4 项通过（app origin/无 Node API、CSP、弹窗与外链拦截、协议路径穿越）；服务握手 1 项失败，原因是 `services/workbench/src/workbench/rpc.py` 与 `__main__.py` 仍为 `NotImplementedError` 桩；契约漂移 1 项因 `contracts/rpc.schema.json` 尚未导出而跳过。
- 安装包当前不含 Python 服务：后端脚手架范围明确不包含 PyInstaller 与桌面打包。`build.ps1` 默认在缺少服务包时失败；`-AllowShellOnly` 可显式构建 shell-only 包。`verify.ps1` 同样把缺少服务包和缺少契约 schema 计为失败。

## 安全边界

- Renderer：`contextIsolation=true`、`nodeIntegration=false`、`sandbox=true`、`webSecurity=true`。
- 生产来源仅 `app://workbench`；自定义协议拒绝路径穿越，并附带 CSP 与 `nosniff`。
- IPC 同时校验 sender frame、来源 origin 和方法白名单；自定义 `app:` scheme 的 origin 显式解析为 `app://host`（Node 的 `URL.origin` 对非特殊 scheme 返回 `null`）。renderer 参数不能指定 source。
- 窗口打开、导航到外部来源、`webview` 附加均被阻断；所有权限请求当前拒绝。
- 本机服务权限校验不是操作系统沙箱；MCP/工具强隔离属于后续独立工作。

## 未完成 / 阻塞

1. 真实 `system.initialize/ping/shutdown` 实现与后端测试，由后端脚手架负责；当前 `pytest` 还因 `request` 是 pytest 9 保留参数名而在收集阶段失败。
2. `contracts/rpc.schema.json` 与 `contracts/generated.ts` 的正式生成。
3. PyInstaller onedir 服务包、安装包内启动、无 Python/Node 环境验证。
4. Windows Job Object 子进程树管理尚未实现；当前使用 `taskkill /T` 并等待退出，作为脚手架阶段的受控清理。完整隔离在打包阶段补齐。
5. 业务页面（资料、DeepSeek、题库、面试、语音、MCP）按 M1～M3 后续任务实现。
6. 打包后 `extraResource` 已预留 `services/workbench/dist/workbench-service`；该目录创建后 Forge 会自动纳入。
