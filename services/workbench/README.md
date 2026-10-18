# 知序本地后端

Python 3.14 + Pydantic 2 的本地 stdio JSON-RPC 服务，供 Electron 主进程启动。当前提供协议、基础契约和生命周期；尚未实现 SQLite、资料、模型、语音和 MCP 业务。

## 安装和检查

在仓库根目录执行（Windows，需已安装 CPython 3.14）：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/bootstrap-backend.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-backend.ps1
```

安装脚本创建根 `.venv`，按带 SHA256 的 `requirements.lock` 安装，再通过 `--no-deps --no-build-isolation` editable 安装服务包；不会更改全局或 Conda 环境。已有 `.venv` 版本不匹配时明确失败。脚本可从其他当前目录调用，也支持仓库路径带空格。

`verify-backend.ps1` 运行依赖一致性、全量后端 pytest、compileall 和 schema 漂移检查；任何步骤失败返回非零。这是后端检查，不代表完整 M1 或安装包验收。

## 启动和协议

```powershell
.\.venv\Scripts\python.exe -u -m workbench --data-dir 'D:\workbench data'
```

每行一个 UTF-8 JSON，以 LF 分隔；stdout 只输出协议，诊断写 stderr，运行日志位于 `<data-dir>/logs/backend.log`。数据目录当前仅用于日志，每份 5 MiB、保留 5 个轮转备份；不创建虚假 SQLite。

可依次向 stdin 写入：

```json
{"jsonrpc":"2.0","id":"init-1","method":"system.initialize","params":{}}
{"jsonrpc":"2.0","id":"ping-1","method":"system.ping","params":{}}
{"jsonrpc":"2.0","id":"stop-1","method":"system.shutdown","params":{}}
```

- initialize 返回 `protocol_version=1`、`schema_version=0`、每进程固定 UUID `service_instance_id` 及三个系统方法的 capabilities。
- ping 返回 `ok=true`、`status=ok` 及同一个服务实例 ID，兼容现有桌面客户端。
- shutdown 先返回 `status=shutting_down`，再退出；不需要父进程关闭 stdin。无 id 的合法 notification 不响应，shutdown notification 仍会停止服务。
- EOF 排空已接收的普通请求；最多等待 5 秒，随后取消未完成任务。主动 shutdown 取消其余请求，最多等待 2 秒排空写队列。同步处理器不能被 Python 强行中断，使用有界守护线程避免阻塞进程退出；以后数据库写入应使用专用有序生命周期，不能依赖守护线程保证持久化。

单帧最大 8 MiB（不含 LF），支持跨读取的 UTF-8 和多帧；超限后丢弃到下一 LF，再处理后续帧。无效 JSON/编码为 `-32700`，非法 envelope/批处理为 `-32600`，未知方法 `-32601`，非法参数 `-32602`，意外处理器异常 `-32603`。不回显原始输入和异常。接近上限的 ID 若使错误响应也超限，使用 `id:null` 的短错误响应，服务继续可用。

批处理未提供。合法 notification 无论成功或业务错误均无响应；显式 `id:null` 则是有响应请求。内部方法由路由注册与调用方 source 控制，params 不能提升 source；此限制不是操作系统沙箱。

## 公共契约

`src/workbench/contracts.py` 定义严格 DTO、CommandMeta、DomainError、ModelRequest/ModelResult 和系统结果。`rpc.py` 保留 `JsonLineDecoder.feed`、`RpcRouter.register`、`RpcRouter.dispatch`，同步和异步 handler 都可注册。

```powershell
.\.venv\Scripts\python.exe scripts/export-contracts.py
.\.venv\Scripts\python.exe scripts/export-contracts.py --check
# 安装桌面 npm 依赖后，使用现有生成器同步 TypeScript
npm --prefix apps/desktop run contracts:types
npm --prefix apps/desktop run contracts:types:check
```

导出的 JSON Schema 位于根 `contracts/rpc.schema.json`。`--output <path>` 可指定临时路径，`--check` 比较文件，不修改漂移文件，缺失和漂移均返回 1。

仅更新依赖时重新锁定（正常 bootstrap 不解析新版本）：

```powershell
.\.venv\Scripts\python.exe -m piptools compile --extra dev --generate-hashes --allow-unsafe --no-emit-index-url --no-emit-trusted-host --output-file services/workbench/requirements.lock services/workbench/pyproject.toml
```

日志和测试输出不提交。后端脚手架已经过真实 Windows 子进程验证；PyInstaller 服务包、无 Python/Node 机器运行及完整 M1 仍是后续任务。
