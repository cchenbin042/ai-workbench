# 知序后端脚手架 Implementation Plan

> **For agentic workers:** Use subagent-driven-development for the user-authorized backend portion of M1 Task 01. The parent M1 task remains incomplete until desktop delivery and its own acceptance pass.

**Goal:** 提供可安装、可启动、可测试的 Python 3.14 本地服务，后续桌面通过 stdio JSON-RPC 使用它。

**Spec:** [技术方案](../../technical/technical-design-v1.md)、[M1 计划](2026-10-18-ai-workbench-m1-plan.md)。

**Scope ruling:** 用户本轮明确要求“使用子代理完成后端脚手架”。执行 M1 Task 01 的后端部分，不执行 SQLite、任务业务、Electron、模型/语音/MCP、Windows 安装包和前端 TS 类型生成。复用 JSON-RPC/Pydantic 契约、项目私有 venv、协议/进程测试。原 M1 Task 01 不能整体勾选完成。

## Global Constraints

- Python 3.14，src 布局，Pydantic 2；不改全局/Conda 环境，不创建业务空模块或仅供未来使用的框架。
- stdio JSON-RPC 2.0，UTF-8 LF 分帧，单帧上限 8 MiB。stdout 只输出协议；日志不输出原始请求/凭据。
- 提供 system.initialize/ping/shutdown；protocol_version=1、schema_version=0，每个服务进程一个 UUID service_instance_id。
- 按现有 API 保留 JsonLineDecoder.feed(data: bytes) -> list[dict]、RpcRouter.register(method, handler)、async RpcRouter.dispatch(request, *, source)。source 不能从 params 伪造。
- CLI `python -u -m workbench --data-dir <directory>`；正常 shutdown 返回确认后及时退出，不能等父进程关闭 stdin 才退出；EOF 也正常退出。
- 错误符合 JSON-RPC 标准，支持明确的 notification 无响应；无效版本、方法、参数、ID、UTF-8、超长帧不能导致原始异常/敏感数据回显。批处理不在本轮接口范围，明确拒绝。
- Windows 真实子进程验证含保持 stdin 打开的 shutdown、EOF、分片输入、多请求、坏请求之后有效请求、stdout/stderr 分离。长/慢 handler 不阻塞 ping 的基础测试应覆盖读写生命周期。
- 数据目录仅用于日志/本地运行元数据，本轮不创建虚假 SQLite。5 MiB 日志轮转，保留 5 份；完整未来权限依赖桌面 IPC 的校验，不声称本脚手架构成安全沙箱。
- 仅提交代码、测试、锁文件和脱敏说明，不提交 .venv、输出/日志、私人正文或凭据。不推送/发布。

## Review Focus

1. UTF-8 字符分在两个片段、同片段含多帧，以及恰好/超过 8 MiB 的边界。
2. shutdown 时 stdin 仍打开，或父进程直接关闭输入；服务都能及时退出，无读线程阻止解释器结束。
3. notification、显式 id:null、布尔 ID、NaN/Infinity、非法 params 与异常 handler 的错误响应安全且有确定语义。
4. 同时接收慢请求与 ping，响应按各自 ID 区分，协议 stdout 没有启动日志或调试输出。
5. bootstrap/verify 在带空格目录下可运行；schema --check 检测漂移；不存在的完整 M1/M2/M3 阶段不能返回成功。

### Task 1: Backend scaffold

**Files owned by implementer:**

- `services/workbench/pyproject.toml`、`requirements.lock`、`README.md`。
- `services/workbench/src/workbench/__init__.py`、`__main__.py`、`rpc.py`、`contracts.py`；只有职责明确需要时再拆 service.py/logging.py，不添加空业务文件。
- `services/workbench/tests/test_rpc.py`、`test_service_process.py`，可为真实子进程增加小型 test-only helper。
- `scripts/bootstrap-backend.ps1`、`verify-backend.ps1`、`export-contracts.py`。
- `contracts/rpc.schema.json`。

**Interfaces:**

- `JsonLineDecoder.feed(data: bytes) -> list[dict]`；8 MiB 之前有界缓冲，跨 chunk UTF-8 不损坏。拒绝时给 DomainError/标准协议错误，不泄漏输入。
- `RpcRouter.register(method: str, handler: Callable, *, internal: bool=False) -> None`，支持同步或 async handler。
- `async RpcRouter.dispatch(request: dict, *, source: str='bridge') -> dict | None`；internal 方法默认不可从 bridge 调用，None 仅代表合法 notification 无响应，缺/非法请求 ID 的错误按协议返回 null。
- `contracts.py` 定义 CommandMeta(operation_id/method/scope_id/expected_revision)、DomainError(code/message/committed)、ModelRequest(messages/model_id/response_format/max_tokens)、ModelResult(content/finish_reason/request_id/usage) 与系统/JSON-RPC DTO；字段校验由 Pydantic 提供，拒绝危险的宽松类型转换。
- initialize 返回上述版本/UUID/能力；ping 返回可读正常状态；shutdown 先写确认再退出。启动错误/诊断仅 stderr/日志，系统 handler 不回显 params。
- bootstrap 创建根 `.venv`，锁定可重装依赖；verify 执行 backend 全量测试、compileall 与 schema --check，失败应非零。脚本默认只验证后端，不伪装 M1 整体验收。

- [ ] **Step 1: 配置与可安装包。** 建立 pyproject/src/test 配置，依赖仅 pydantic，dev pytest/pytest-asyncio/pip-tools。Python 3.14 已存在，用项目 .venv；生成带 SHA256 哈希的 requirements.lock，editable 安装用 --no-deps；后续 bootstrap 使用锁文件，不每次重新解析版本。
- [ ] **Step 2: 测试先行并记录 Red。** 用行为测试覆盖 Review Focus；临时最小接口占位可抛 NotImplementedError，确认失败源于未实现行为，不把缺依赖/导入错误当作 Red。记录具体测试名、命令、失败摘要。
- [ ] **Step 3: 实现最小 RPC/CLI。** 按接口与约束完成分帧/校验/路由/初始化/进程生命周期，避免取消后阻塞 readline 的非守护线程让 shutdown 挂住；保持代码简洁并只使用确有必要的依赖。
- [ ] **Step 4: 复现验证。** 执行全量 backend pytest、真实 Windows 子进程握手/ping/shutdown/EOF/慢请求、compileall、schema 导出及 --check。实际执行 PowerShell bootstrap/verify；改坏临时 schema 的 --check 应失败后恢复。README 给出可复制命令和数据目录/错误/范围说明。
- [ ] **Step 5: 自查与提交。** 记录测试与限制，提交仅本任务拥有文件，commit message `feat: scaffold Python stdio backend`。不触碰根 README、技术/产品/总计划、根 .gitignore、runtime-baseline 和根验收文件；这些由主代理回写。写详细 report 到主代理提供路径，最终回复只含状态、commit、测试摘要和 concerns。
