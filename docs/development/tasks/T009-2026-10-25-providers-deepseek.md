# T009：DeepSeek 配置、系统密钥与文本请求（M1 Task 05）

## 1. 任务信息

| 字段 | 内容 |
| --- | --- |
| 任务编号 | T009 |
| 类型 / 关联里程碑 | 后端 + 桌面开发 / M1 Task 05 |
| 状态 | 已完成（真实连接已验证） |
| 创建日期 | 2026-10-25 |
| 开始日期 | 2026-10-25 |
| 最近更新 | 2026-10-25 |
| 完成日期 | 2026-10-25 |
| 最近回写 | 2026-10-25 |
| 总文档 | [master-plan.md](../master-plan.md) |
| 前置依赖 | T008（提交 440f421 已推送 origin/codex/backend-tasks） |
| 需求 / 设计 | [M1 Task 05](../../superpowers/plans/2026-10-18-ai-workbench-m1-plan.md)、[技术方案 §7.1](../../technical/technical-design-v1.md) |

## 2. 目标和范围

接入真实 DeepSeek 文本 provider：配置版本化（endpoint/model/parameters 不可变版本）、系统密钥存储（keyring + Windows 凭据管理器白名单，数据库只存引用）、带超时与受限重试的 chat completions 客户端、进入统一执行槽的最小连接测试（不带资料）、脱敏日志。用户在会话中提供了自己的 API key 用于真实验证；密钥只经 stdin/环境变量进入本机系统密钥存储，未写入任何仓库文件、文档、测试或日志。

## 3. 功能点

| 编号 | 行为与验收 | 状态 |
| --- | --- | --- |
| F01 | 迁移 0004：provider_configs/provider_config_versions + 内置 agent 种子（question_generation/interview，provider 引用置 NULL 表示跟随当前版本），schema=4 | 已完成 |
| F02 | providers.update 不可变配置版本（HTTPS 强制、loopback HTTP 例外）、providers.get/list | 已完成 |
| F03 | setSecret/deleteSecret：keyring 后端白名单（WinVaultKeyring）、DB 只存 `keyring:…` 引用 | 已完成 |
| F04 | DeepSeekClient：connect=10/idle=60/total=180 秒、401/403→AUTH_FAILED、429/5xx 无内容时退避重试 1 次（遵守 Retry-After）、未知断开/超时不自动重试、MODEL_EMPTY/MODEL_TRUNCATED、请求头与日志零密钥 | 已完成 |
| F05 | providers.test 经 tasks.create（generic + action=provider_connection_test）进入唯一执行槽；结果（ok/error_code/latency/model/request_id/usage）写入任务 checkpoint | 已完成 |
| F06 | 桌面 SettingsPage：配置编辑、密钥保存/删除（提交即清空输入）、测试连接并轮询任务结果；bridge 白名单扩展 | 已完成 |
| F07 | 真实 DeepSeek 验证：正向连接、无效密钥负路径、日志泄漏扫描 | 已完成 |

## 4. 实施与验收

- [x] 依赖（httpx 0.28.1、keyring 25.7.0）加入 pyproject 并以 pip-tools 重新生成带哈希 requirements.lock。
- [x] 8 项失败测试确认 Red，实现后 Green；后端全量 140/140，契约无漂移。
- [x] 桌面 typecheck、契约类型检查、e2e 18/18（新增 @settings 1 项）。
- [x] 真实 DeepSeek 服务验证（用户自己的账号）。
- [x] 回写任务明细、总览与接手指南。

## 5. 开发记录与决策

### 2026-10-25 / 实施

- Ruling: 连接测试走 `task_type=generic` + `input.action=provider_connection_test`，不在 0002 的 CHECK 约束上重建任务表扩展 TaskType；生产 generic dispatcher 只放行该白名单动作，其余动作 FLOW_UNAVAILABLE。既有子进程测试断言"generic 不可恢复"随之更新为"恢复成功后执行失败"，并需按 RPC id 过滤事件通知（成功状态变化会推送事件）。
- Ruling: 内置 agent 种子的 provider_version_id 置 NULL，语义"跟随 provider 当前版本"，避免 Task 06 引用被钉死在过期配置版本；M3 自定义 agent 才显式钉版本。
- Ruling: 迁移种子存在行级循环外键（provider_configs.current_version_id ↔ provider_config_versions），按"先 NULL 插入、再插版本、UPDATE 回填"顺序解决。
- Ruling: 连接测试结果一律以 completed + 结构化 checkpoint 返回（ok=false + error_code），不用任务失败表达可预期的连接错误；无效密钥返回 AUTH_FAILED 由真实服务验证。
- Ruling: setSecret 先写 keyring 再写 DB（同值重放安全，崩溃窗口不丢密钥）；deleteSecret 对 keyring 缺失条目视为已达成。密钥通过 to_thread 调用，不阻塞事件循环。
- Ruling: usage 透传 DeepSeek 返回的整数字段（含 prompt_cache_hit/miss_tokens），非整数值丢弃；ModelResult 新增 `model` 字段记录供应商实际返回的模型名，连接测试同时记录请求配置模型与返回模型。
- Deviation: 计划中的 `tests/fixtures/http_provider.py` 用 httpx.MockTransport 实现受控替身（脚本化响应序列、记录请求元数据但不保存密钥），不起真实本地端口。
- Ruling: 日志只含 request_id/finish_reason/latency/usage；真实验证后对整个临时数据目录做泄漏扫描（含 bogus 密钥字符串）确认 CLEAN。

## 6. 实际文件改动

- `services/workbench/src/workbench/providers/{__init__,config,deepseek}.py`（新增）：配置版本、keyring 封装、连接测试流；DeepSeekClient。
- `services/workbench/src/workbench/migrations/0004_providers.sql`（新增）：4 表 + 内置种子。
- `services/workbench/src/workbench/contracts.py`：providers 相关 DTO；ModelResult 增加 model 字段。
- `services/workbench/src/workbench/__main__.py`：6 个 providers RPC 注册、generic 动作分发、capabilities 更新。
- `services/workbench/pyproject.toml`、`requirements.lock`：httpx/keyring 依赖与哈希锁。
- `apps/desktop/src/renderer/pages/SettingsPage.tsx`（新增）、`App.tsx`、`components/PlaceholderPage.tsx`（移除占位设置卡）、`shared/bridge.ts`、`styles.css`。
- `contracts/rpc.schema.json`、`contracts/generated.ts`。
- 测试：`tests/test_providers.py`、`tests/fixtures/http_provider.py`（新增）；`test_storage.py`（schema=4、表集合、降级测试改用 version=5）、`test_service_process.py`（generic 恢复新语义 + 事件过滤）；`tests/e2e/settings.spec.ts`（新增）。

## 7. 验证

| 命令 / 检查 | 结果 | 限制 |
| --- | --- | --- |
| scripts/verify-backend.ps1 | 140 passed（132 + 8 providers）；pip check、compileall、schema 一致 | 替身 HTTP + 可控 keyring，不含真实云服务 |
| npm desktop typecheck / contracts:types:check | 退出码 0 | — |
| npm desktop test:e2e --grep `@shell&#124;@unit&#124;@nav&#124;@materials&#124;@settings` | 18 passed（@settings 验证无密钥时 PROVIDER_NOT_CONFIGURED 全链路） | 开发环境，非发行包 |
| 真实 DeepSeek 正向 | ok=true，latency≈2.4～2.7s，model=deepseek-flash（真实存在），request_id 与 usage（24 tokens）返回 | 用户本人账号，单条最小请求，不含任何资料内容 |
| 真实 DeepSeek 负路径 | bogus key → AUTH_FAILED，任务 completed + 结构化错误 | 未触发生成计费 |
| 日志泄漏扫描 | 临时数据目录全部日志 CLEAN（真实密钥与 bogus 密钥均未出现） | — |
| 密钥存储 | WinVaultKeyring（Windows 凭据管理器）确认；本机已保存用户密钥供后续使用 | 开发机验证；安装包内验证属 G01 发行任务 |

## 8. 遗留与接续

- 下一业务任务为 M1 Task 06：带来源校验的候选题生成（上下文预算、来源校验、分批、检查点、取消栅栏）。
- SSE 流式预览未实现（P0 建题/反馈为非流式 JSON，M2 按需补）；ASR provider（kind=asr）与连接测试 UI 留 M3。
- 安装包内的系统密钥存取验证依赖 G01 发行包任务。
- 用户密钥现保存于本机系统凭据管理器（`ZhixuWorkbench / provider/text/api-key`）；如怀疑泄露应轮换。
