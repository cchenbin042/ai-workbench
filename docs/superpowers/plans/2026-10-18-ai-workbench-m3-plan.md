# 知序 M3 语音与工具收口 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在文字闭环上接入逐轮语音、最小 stdio MCP、自定义 Agent 和本机数据管理，交付满足 P0 验收的 Windows 安装包。

**Architecture:** 麦克风由受控 renderer 显式启动，音频块写 Python 附件后才转写；MCP 仅在 Python 的统一授权与任务入口调用。沿用一个 AI 执行槽、不可变答案和事务/副作用账本。

**Tech Stack:** 既有桌面/Python/SQLite；MediaRecorder、httpx ASR、官方 MCP Python SDK、受限 JSON Schema 校验、PyInstaller/Forge、pytest/Playwright。

**Spec:** [技术方案第 9～15 节](../../technical/technical-design-v1.md)、[PRD](../../product/prd-ai-workbench-v1.md)、[实施总览](2026-10-18-ai-workbench-implementation-plan.md)、[M2 前置计划](2026-10-18-ai-workbench-m2-plan.md)。

## Global Constraints

继承总览全部约束；M2 门禁通过后实施。语音 180 秒/8 MiB/256 KiB 块、明确停止后云转写、核对后主动交答案；ASR 配置独立于 DeepSeek。只支持可信本地 stdio 服务，shell:false、参数数组、env 密钥引用；工具调用权限取交集，unknown 不自动重试。普通 Agent 上限 6 轮/每轮 3 工具/共 8 调用/10 分钟，工具 30 秒默认、120 秒上限。MCP 文本输入模型最多 64 KiB，返回帧上限 4 MiB。安装包不要求全局 Python/Node；P0 全验收未过不能标正式交付。

## Review Focus

- 录音中满盘、权限撤销、睡眠/离开页面：停止所有 tracks 且可解释附件状态（Task 17）。
- 停止后排队时取消/断网、转写迟到：不再发送或写结果，已确认文字不受影响（Task 18）。
- 工具描述声称只读却传越界路径、schema 变化：调用前拒绝或要求新授权（Task 19）。
- 外部写入成功但确认丢失、恢复后用户点继续：unknown 保留、不自动重放（Task 19、22）。
- 备份路径穿越、损坏包、新 schema 交旧应用、卸载保留数据：阻断破坏性操作并保留可恢复副本（Task 21、22）。

## 文件与契约分配

Task 17 拥有麦克风、流式本机附件；18 拥有 ASR 适配/转写状态；19 拥有 MCP 会话、权限与副作用；20 拥有 Agent 配置与有上限工具循环；21 拥有备份/恢复/删除；22 拥有 P0 汇总与发行。Task 19 的平台进程清理复用 Task 01 的封装，不添加按进程名批量终止逻辑。

### Task 17: 明确启动的录音与可靠本机附件

**Files:** Create `services/workbench/src/workbench/audio.py`、`migrations/0013_audio.sql`、`tests/test_audio.py`；Create main `permissions.ts`、renderer `hooks/useRecorder.ts`、`components/VoiceAnswer.tsx`、`tests/e2e/audio.spec.ts`；Modify InterviewPage/main index/preload/契约。迁移创建 attachments 并将 answers 的 attachment_id 关联到它，验证已有文字答案仍可读。

**Interfaces:** Consumes Task 11 submit_answer、既有系统能力检测；Produces `async begin_audio(command: dict, store: Storage) -> dict`、`async append_audio(command: dict, store: Storage) -> dict`、`async finish_audio(command: dict, store: Storage) -> dict`、`async discard_audio(command: dict, store: Storage) -> dict`；append 含 recording_id/chunk_index/base64，服务分配路径；`useRecorder(): {start(): Promise<void>; stop(): Promise<void>; discard(): Promise<void>; state: string}`。

- [ ] **Step 1: 写失败测试。** `test_audio_chunks_are_ordered_bounded_and_idempotent` 测重复/跳号/不同内容同序号、256 KiB 块和 8 MiB 总限；`@audio stops tracks on limit navigation and storage failure` 测 180 秒、拒绝权限、睡眠/唤醒、写失败与离页。e2e 用假音频设备+可控时钟；真实 180 秒设备测试在 Task 22 补齐。

```python
assert persisted_chunk_count == unique_chunk_indices
assert total_bytes <= 8 * 1024 * 1024
assert stopped_at_seconds <= 180
assert answers_created_by_recording == 0
assert attachment_ready_before_all_chunks is False
```

- [ ] **Step 2: 确认 Red。** `.\.venv\Scripts\python.exe -m pytest services/workbench/tests/test_audio.py -q`；`npm --prefix apps/desktop run test:e2e -- --grep "@audio"`；预期重复块/停止清理断言失败。
- [ ] **Step 3: 实现。** 检查 ASR 配置和格式支持后，用户点击触发 app origin 一次性 audio 权限；拒绝 video/后台请求。优先 webm/opus、64 kbps，1 秒块、每块 ACK、有界缓冲；UI/服务都用本轮开始时间和累积大小控制上限。tmp 写失败停止 tracks，finish 核对 MIME/大小/时长/哈希后原子移动；不完整块标未完成而非可转写。离页/退出/睡眠停止并撤销本轮许可。
- [ ] **Step 4: 确认 Green。** 重跑目标测试；在 Windows 包实际点击录音/停止，状态、时长、停止按钮始终可见，达到上限不自动提交，未配服务时先显示配置缺口。此任务仍只验证本机附件，不声称 ASR 已接入。
- [ ] **Step 5: 提交。** `git commit -m "feat: record bounded audio attachments explicitly"`，不暂存音频文件。

### Task 18: 独立 ASR 与核对后提交

**Files:** Create `src/workbench/providers/asr.py`、`tests/test_asr.py`、`tests/e2e/asr.spec.ts`；Modify audio.py、providers/config.py、SettingsPage/VoiceAnswer/InterviewPage/契约。不新增 OSS、FFmpeg 或实时双向语音基础设施。

**Interfaces:** Consumes attachment ID、TaskService、ModelResult、submit_answer；Produces `async AsrClient.transcribe(attachment: dict, config: dict, cancel: asyncio.Event) -> dict`、`async transcribe_audio(command: dict, store: Storage, client: AsrClient, tasks: TaskService) -> dict`。结果为 transcript/attachment_id/provider_request_id/usage，不含已提交 answer_id；正式回答仍走 Task 11 的原提交函数。

- [ ] **Step 1: 写失败测试。** `test_stop_consent_and_queue_cancel_control_upload` 录制点击时保存“停止后发送”选择、附件 ready 前不上传、排队取消不上传；`test_late_asr_result_never_advances_turn`；`test_editable_transcript_retry_and_audio_delete_preserve_text`。

```python
assert uploads_before_attachment_ready == 0
assert uploads_after_queued_cancel == 0
assert answers_before_user_submit == 0
assert saved_answer["answer_text"] == user_corrected_transcript
assert saved_answer_after_audio_delete["answer_text"] == user_corrected_transcript
```

- [ ] **Step 2: 确认 Red。** `.\.venv\Scripts\python.exe -m pytest services/workbench/tests/test_asr.py -q`；预期排队取消/自动提交/迟到写入断言失败。
- [ ] **Step 3: 实现。** 默认 qwen3-asr-flash，用户配置账号地域/业务空间/密钥引用；通过官方兼容 `/chat/completions` 的 input_audio Base64 请求，不误用 `/audio/transcriptions`。connect=10/idle=60/total=180 秒，共用单槽；queued_transcription→transcribing→awaiting_confirmation，结果保存转写草稿。修正后主动提交，失败可重试同附件或切文字，删除音频不删除答案；只取文字字段，不用情绪标签评价用户。
- [ ] **Step 4: 确认 Green。** 重跑 pytest；`npm --prefix apps/desktop run test:e2e -- --grep "@asr"`；至少 10 段经授权 20～180 秒中文技术回答真实抽样，记录识别/修订/耗时/用量，不提前承诺准确率。账号不具备时留 blocked，不以固定转写替身算真实通过。
- [ ] **Step 5: 提交。** `git commit -m "feat: transcribe audio and confirm answers explicitly"`。

### Task 19: 本地 stdio MCP、授权和副作用账本

**Files:** Create `src/workbench/tools/{__init__,mcp,policy}.py`、`migrations/0014_tools.sql`、`tests/test_mcp.py`、`tests/fixtures/mcp_server.py`；Create renderer `components/{ToolSettings,ToolApproval}.tsx`、`tests/e2e/tools.spec.ts`；Modify tasks/TaskPage/SettingsPage/契约及 `services/workbench/{pyproject.toml,requirements.lock}`。迁移创建 mcp_servers/tool_policies/tool_calls；阶段安装官方 SDK 与 jsonschema，更新带哈希锁文件；只启用所支持的 JSON Schema draft，未知 draft 阻断调用，不临时当无校验处理。

**Interfaces:** Consumes TaskService、Task 01 进程生命周期、path 边界；Produces `async McpManager.connect(server_id: str) -> dict`、`async McpManager.list_tools(server_id: str) -> list[dict]`、`async McpManager.close(server_id: str) -> None`、`authorize_tool(task: dict, tool: dict, args: dict, approval: dict | None) -> dict`、`async call_tool(command: dict, store: Storage, manager: McpManager, tasks: TaskService) -> dict`。authorize_tool 返回 allow/deny/approval_required 与原因；调用返回 call_id/status/result_summary。

- [ ] **Step 1: 写失败测试。** `test_policy_intersection_rejects_disabled_scope_and_schema_change`；`test_timeout_after_side_effect_stays_unknown_on_restart` 用本机测试服务先写一次临时标记再延迟返回；`test_approval_revalidates_and_binds_new_run`；检查 `.cmd/.bat`、隐式下载、未知工具和工具输出注入不扩大权限。

```python
assert denied_tool_call_count == 0
assert external_write_count_after_restart == 1
assert persisted_tool_status == "unknown"
assert approved_run_id != waiting_run_id
assert unrelated_user_process_was_terminated is False
```

- [ ] **Step 2: 确认 Red。** `.\.venv\Scripts\python.exe -m pytest services/workbench/tests/test_mcp.py -q`；协议测试启动真实 stdio 子进程，不能只 mock SDK 的 call_tool。
- [ ] **Step 3: 实现。** 参数数组启动用户选定 .exe 或解释器+脚本，必要环境白名单和 secret_ref，初始化/列工具/调用/取消/退出状态可见。校验 schema 与配置 hash、风险和路径，权限取连接/启用/Agent/任务/授权交集。未确认则持久化 proposal、释放槽，确认后排队、重新校验并绑定新 run。外部调用前存 started，结果不明记 unknown，不自动重放。4 MiB 帧限、64 KiB 入模限；清理只用持有句柄/Job Object，配置 UI 说明本地程序不是沙箱。
- [ ] **Step 4: 确认 Green。** 重跑 pytest；`npm --prefix apps/desktop run test:e2e -- --grep "@tools"`；可连接/列工具/允许调用，禁用/越界在执行前拒绝，工具崩溃只影响依赖任务；安装包退出后无自有服务残留。
- [ ] **Step 5: 提交。** `git commit -m "feat: add scoped stdio tools and side-effect tracking"`。

### Task 20: 自定义 Agent 与有限工具循环

**Files:** Create `src/workbench/agents.py`、`tests/test_agents.py`、renderer `pages/AgentsPage.tsx`、`tests/e2e/agents.spec.ts`；Modify flows/generic.py、providers/deepseek.py、__main__.py、contracts.py、TaskPage。既有 agent_configs/agent_config_versions 结构若不足，新增 `migrations/0015_agent_policy.sql`；不改已发布旧迁移 checksum。

**Interfaces:** Consumes call_tool/authorize_tool、run_generic、配置/任务快照。Produces `async save_agent_version(command: dict, store: Storage) -> dict`、`async create_agent_task(command: dict, store: Storage, tasks: TaskService) -> dict`；将 Task 14 的 run_generic 显式扩展为 `async run_generic(task_id: str, run_id: str, store: Storage, client: DeepSeekClient, tasks: TaskService, *, manager: McpManager | None=None) -> dict`，由 __main__.py 任务注册处注入既有 manager。None 保持原无工具路径。扩展 ModelRequest 为 `tools: list[dict]=[] / tool_choice: str | None=None`，ModelResult 为 `tool_calls: list[dict]=[]`；默认值用 Pydantic default_factory，不能共享可变列表。文本旧调用不传这些字段仍按原路径运行。

- [ ] **Step 1: 写失败测试。** `test_agent_versions_do_not_mutate_active_tasks`；`test_custom_prompt_cannot_change_interview_flow_or_expand_scope`；`test_generic_loop_releases_slot_on_approval_and_stops_at_limits` 分别触发 6 轮、每轮 3 工具、共 8 调用、10 分钟预算，等待用户时间不算执行时间。

```python
assert active_task_agent_version_id == original_version_id
assert custom_agent_can_submit_interview_answer is False
assert model_rounds <= 6
assert max_tools_in_round <= 3
assert total_tool_calls <= 8
assert timeout_seconds == 600
```

- [ ] **Step 2: 确认 Red。** `.\.venv\Scripts\python.exe -m pytest services/workbench/tests/test_agents.py -q`；预期配置覆盖/越权或循环上限失败。
- [ ] **Step 3: 实现。** 保存名称/说明/文本模型引用/允许工具新版本，新任务冻结旧版；内置 flow_type 不可由提示词切换。发给模型前过滤工具，再次校验返回参数，超限或需授权进入 waiting_user；工具输出仅数据。候选和成果仍须用户确认，不能让模型直接 commit 题库。Task 14 无工具任务路径继续工作。
- [ ] **Step 4: 确认 Green。** 重跑 pytest；`npm --prefix apps/desktop run test:e2e -- --grep "@agents"`；内置题库和文字面试在断开所有 MCP 后完整可用，旧配置任务不随新版本改变。
- [ ] **Step 5: 提交。** `git commit -m "feat: version agents and bound generic tool execution"`。

### Task 21: 完整备份、恢复与范围明确的数据删除

**Files:** Create `src/workbench/data_admin.py`、`tests/test_data_admin.py`、renderer `components/DataManagement.tsx`、`tests/e2e/data-admin.spec.ts`；Modify storage.py/audio.py/dialogs.ts/SettingsPage/契约。备份/删除队列状态复用 attachments 与 operations，不额外建调度服务。

**Interfaces:** Consumes Storage、附件、平台选择/覆盖凭据；Produces `async create_backup(command: dict, store: Storage) -> dict`、`async restore_backup(command: dict, store: Storage, tasks: TaskService) -> dict`、`async delete_local_data(command: dict, store: Storage) -> dict`、`async delete_attachment(command: dict, store: Storage) -> dict`。返回具体对象清单、备份 manifest/hash/schema、完成或可重试失败，不以 UI 隐藏替代删除。

- [ ] **Step 1: 写失败测试。** `test_backup_restore_consistency_and_no_secret_export`，WAL 写入+附件同时变化时冻结快照；`test_reject_traversal_corruption_and_newer_schema`；`test_audio_delete_retry_keeps_confirmed_answer`；`test_deletion_never_touches_linked_project`。

```python
assert restored_integrity == "ok"
assert escaped_paths_created == []
assert linked_project_hash_after_delete == linked_project_hash_before
assert confirmed_answer_after_delete == confirmed_answer_before
assert secret_value not in backup_manifest_and_files
```

- [ ] **Step 2: 确认 Red。** `.\.venv\Scripts\python.exe -m pytest services/workbench/tests/test_data_admin.py -q`；预期副本不一致、越界恢复或误删断言失败。
- [ ] **Step 3: 实现。** 暂停写/附件变更、backup API+manifest+附件引用；恢复前显示替换范围、备份当前库、关闭连接/录音/工具，再校验版本和每个目标规范路径/哈希后替换；损坏/更新 schema 阻断。选择删除范围时列依赖/备份/凭据项，归档与删除分开。音频删除中→文件删除→已删除，可重试且答案保留；只在应用数据根内执行。保留最近 5 份迁移备份，手动备份不清理。
- [ ] **Step 4: 确认 Green。** 重跑 pytest；`npm --prefix apps/desktop run test:e2e -- --grep "@data-admin"`；包内实际备份→修改数据→恢复、密钥重配、附件删除失败重试，不把本机删除解释为供应商云端删除。
- [ ] **Step 5: 提交。** `git commit -m "feat: back up restore and delete scoped local data"`。

### Task 22: 全量验收、Windows 发行与接续说明

**Files:** Create `tests/e2e/p0-flow.spec.ts`、`services/workbench/tests/test_release_faults.py`、`docs/development/acceptance/p0.md`、`docs/development/release-checklist.md`；Modify verify.ps1/build.ps1、runtime-baseline.json、README.md。证据写 `output/verification/<date>-M3/`。

**Interfaces:** Consumes全部已实现模块；Produces `verify.ps1 -Stage M3 [-Live]`、`build.ps1 -Stage M3` 和 `verify.ps1 -Stage M3 -InstalledApp '<absolute-exe-path>'`。InstalledApp 参数在此任务建立，测试直接启动发行包，不依赖 Vite/源码解释器。

- [ ] **Step 1: 写验收测试。** `@P0 materials questions text voice report review restart` 在安装包完成选材→10 道→入 5 道→文字/语音→报告→复习→重启；`test_unknown_tool_does_not_replay_after_service_crash`；桌面涵盖两尺寸、100/125/150% 缩放、键盘/标签/焦点、减弱动态效果。

```typescript
expect(savedQuestionCount).toBe(5);
expect(voiceAnswerText).toBe(userConfirmedText);
expect(reopenedAttempt.reference_seen_at).not.toBeNull();
expect(toolExternalWritesAfterRestart).toBe(1);
expect(ownedProcessesAfterExit).toEqual([]);
```

- [ ] **Step 2: 执行累计自动检查。** `powershell -NoProfile -File scripts/verify.ps1 -Stage M3`；预期 typecheck、契约无漂移、累计 pytest/e2e 无失败，未收集测试或未知 skip 不算通过。发现失败回到拥有模块修复，不在 e2e 隐藏失败。
- [ ] **Step 3: 执行真实服务和设备抽样。** 同命令加 `-Live`，核对 DeepSeek 追问/依据、至少 10 段中文 ASR、真实麦克风 180 秒上限、拒绝/睡眠/断网；真实本机 stdio 测试服务证实 unknown/越界/取消。分别记录结果、用量和人工修订，账号缺失即 blocked。
- [ ] **Step 4: 验证发行包。** `powershell -NoProfile -File scripts/build.ps1 -Stage M3`；在无 Node/Python 的 Windows x64 环境安装，用 InstalledApp 路径运行累计端到端；检查中文/空格路径、系统 keyring、子进程树清理、升级迁移/恢复/卸载保留数据。对外分发前验证签名；本机包测试不宣称已公开发布。
- [ ] **Step 5: 核对并记录 P0。** p0.md 逐项列 AC01～24 的 actual result、证据及真实/替身/阻塞；全过才写 P0 完成。有阻塞保留状态和下一条操作，P1 课程不补入本阶段。README 记录版本、安装/配置/恢复/限制。
- [ ] **Step 6: 提交。** `git commit -m "test: verify P0 desktop release and recovery"`；保存源码/测试/脱敏验收说明，不提交密钥、录音、构建包或私人材料正文。
