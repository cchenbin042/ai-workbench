# 知序本地后端

Python 3.14 + Pydantic 2 的本地 stdio JSON-RPC 服务，供 Electron 主进程启动。当前提供协议、严格契约、生命周期、SQLite 持久化及本地草稿保存/读取；资料、模型、语音和 MCP 业务按后续计划开发。

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

每行一个 UTF-8 JSON，以 LF 分隔；stdout 只输出协议，诊断写 stderr，运行日志位于 `<data-dir>/logs/backend.log`。日志每份 5 MiB、保留 5 个轮转备份；数据库位于 `<data-dir>/data/workbench.sqlite3`，迁移快照位于 `<data-dir>/backups/migration-*`。服务先完成数据库完整性及迁移检查，再接受请求。

可依次向 stdin 写入：

```json
{"jsonrpc":"2.0","id":"init-1","method":"system.initialize","params":{}}
{"jsonrpc":"2.0","id":"ping-1","method":"system.ping","params":{}}
{"jsonrpc":"2.0","id":"stop-1","method":"system.shutdown","params":{}}
```

- initialize 返回 `protocol_version=1`、`schema_version=1`（读取实际迁移版本）、每进程固定 UUID `service_instance_id` 及系统/草稿方法的 capabilities。
- ping 返回 `ok=true`、`status=ok` 及同一个服务实例 ID，兼容现有桌面客户端。
- shutdown 先返回 `status=shutting_down`，再退出；不需要父进程关闭 stdin。无 id 的合法 notification 不响应，shutdown notification 仍会停止服务。
- EOF 排空已接收的普通请求；最多等待 5 秒，随后取消未完成任务。主动 shutdown 取消其余请求，最多等待 2 秒排空写队列。同步处理器不能被 Python 强行中断，使用有界守护线程避免阻塞进程退出；数据库另有专用单写线程；已接受的写事务不随 RPC 取消而取消，关闭连接前排空这些写事务。若 ACK 丢失，使用原 operation_id 和原参数重试以取得已提交结果。

单帧最大 8 MiB（不含 LF），支持跨读取的 UTF-8 和多帧；超限后丢弃到下一 LF，再处理后续帧。无效 JSON/编码为 `-32700`，非法 envelope/批处理为 `-32600`，未知方法 `-32601`，非法参数 `-32602`，意外处理器异常 `-32603`。不回显原始输入和异常。接近上限的 ID 若使错误响应也超限，使用 `id:null` 的短错误响应，服务继续可用。

批处理未提供。合法 notification 无论成功或业务错误均无响应；显式 `id:null` 则是有响应请求。内部方法由路由注册与调用方 source 控制，params 不能提升 source；此限制不是操作系统沙箱。

## SQLite 与草稿接口

SQLite 使用单写线程、WAL、synchronous=FULL、foreign_keys=ON、busy_timeout=5000 ms；查询使用短生命周期只读连接。当前表只有 schema_migrations、operations、drafts、notes，不预建未来业务空表。notes 尚未提供业务 RPC。

草稿暂仅支持 `scope_id=local`、`owner_type=local` 的本地编辑器，以 owner_id 区分草稿。工作区/任务 owner 在具备真实归属校验后再开放；当前桌面 preload 白名单尚未接入草稿方法，前端持久化联调留给后续任务。

先保存，再等待 ACK 后读取（以下是两个独立请求）：

```json
{"jsonrpc":"2.0","id":"save-1","method":"drafts.save","params":{"operation_id":"editor-1-save-1","scope_id":"local","owner_type":"local","owner_id":"editor-1","expected_revision":null,"content_json":{"text":"初稿"}}}
{"jsonrpc":"2.0","id":"get-1","method":"drafts.get","params":{"scope_id":"local","owner_type":"local","owner_id":"editor-1"}}
```

保存 ACK 返回 `draft_id / revision / saved_at`，仅在 COMMIT 后发送；时间为 UTC ISO 8601。读取另返回 owner、scope 与 content_json。新建时 expected_revision 为 null 或省略；修改时使用上一次 ACK 的 revision，并为每次新保存生成新的 operation_id。content_json 必须是 JSON object，编码后的 UTF-8 最大 200000 字节；布尔 revision、非有限数、额外字段和不支持的 scope/owner 均拒绝。

- 同一 operation_id 与完全相同的已校验请求重试，返回第一次的 ACK，即使当前草稿已经有更新版本或服务已重启。
- 同一 operation_id 改参数返回 OPERATION_CONFLICT；新操作版本不匹配返回 REVISION_CONFLICT；缺失草稿返回 DRAFT_NOT_FOUND。
- 业务变更与 operation 结果在同一事务内提交；满盘、只读或锁定失败不留下成功记录。STORAGE_FULL / STORAGE_UNAVAILABLE 均返回 committed=false，前端应保留编辑缓冲。
- 800 ms 是本地正常环境的保存尝试验证，锁竞争最长等待 5000 ms；不把测试结果当作所有磁盘环境的延迟保证。

迁移 SQL 随 Python 包安装，行尾固定为 LF；已应用文件的内容不可修改，变更必须新增顺序版本。升级前使用 SQLite backup API 产生包含已提交 WAL 页的一致快照并验证 integrity；清单记录 schema/app/protocol 版本、SHA256 和范围。当前迁移快照不包含附件，不是完整离机备份。失败时停止启动并保留备份；不匹配的 checksum 或比应用更新的 schema 也会拒绝启动。

成功迁移后默认保留最近 5 份完整 migration-* 快照，不清理手动备份；清理失败只记录脱敏告警，不把已提交迁移误报失败。手动恢复界面和完整备份包仍属后续任务。

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
