# 知序 M1 真实建题 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用户能安装 Windows 应用、选择真实文本资料、配置 DeepSeek、生成并检查候选题、部分保存到本地题库和导出 JSON。

**Architecture:** 建立最小 Electron/Python 通信、单写 SQLite 与受控任务执行；资料/供应商/题库沿这条链逐步接入。不先建设空 Agent 平台。

**Tech Stack:** Electron + React/TypeScript + Python 3.14 + SQLite + httpx/Pydantic/keyring，pytest 与 Playwright。

**Spec:** [技术方案](../../technical/technical-design-v1.md)、[PRD](../../product/prd-ai-workbench-v1.md)、[实施总览与公共接口](2026-10-18-ai-workbench-implementation-plan.md)。

## Global Constraints

继承总览全部约束。M1 的明确数值：8 MiB RPC 帧、200000/1000000 字节文本范围、24000/8000 token 默认预算与 20% 余量、10 道默认候选、1～30 道范围、每批最多 10 道、结构修复最多 1 次、一个 AI 执行槽。题目、材料和配置版本不覆盖；原项目只读；真实测试必须单独标注服务类型。

## Review Focus

- 大小恰在边界、UTF-8 解码失败和 JSON 字段超长：不静默截断或发送乱码（Task 04、06）。
- 目录前缀相同但非子目录、junction 和读取时替换：拒绝读取/上传（Task 04）。
- 同操作旧 revision 重试、换操作 ID 保存同候选：只保留一次写入（Task 02、07）。
- 取消后迟到响应、重开 queued 任务：不写结果、不自动重发（Task 03、06）。
- 写库失败但界面仍有输入、schema 生成结果漂移：保持未保存状态、构建检查失败（Task 01、08）。

## 文件与契约分配

Task 01 拥有工程入口、协议、bridge 和契约生成；02 拥有事务与初始迁移；03 拥有任务/run/event；04 拥有工作区/资料/选择凭据；05 拥有文本配置/密钥/客户端；06 拥有候选生成；07 拥有题库及导出；08 拥有草稿交互；09 拥有阶段联调。后续任务可修改已列公共注册点，但不重命名前置 Interfaces。

### Task 01: 可启动的桌面壳与 Python 协议

**Files:** Create `.gitignore`、`apps/desktop/{package.json,package-lock.json,tsconfig.json,forge.config.ts,vite.main.config.ts,vite.preload.config.ts,vite.renderer.config.ts,index.html}`；`apps/desktop/src/main/{index,service-process,bridge}.ts`、`src/preload/index.ts`、`src/renderer/{main.tsx,App.tsx,styles.css}`；`services/workbench/{pyproject.toml,requirements.lock}`、`src/workbench/{__init__,__main__,rpc,contracts}.py`；`scripts/{bootstrap,verify,build}.ps1`、`scripts/export-contracts.py`、`docs/development/runtime-baseline.json`。Test `services/workbench/tests/test_rpc.py`、`tests/e2e/{playwright.config.ts,shell.spec.ts}`。生成 `contracts/{rpc.schema.json,generated.ts}`。

**Interfaces:** Consumes 无业务前置。Produces `JsonLineDecoder.feed(data: bytes) -> list[dict]`、`RpcRouter.register(method: str, handler: Callable) -> None`、`async RpcRouter.dispatch(request: dict, *, source: str) -> dict`、`system.initialize/ping/shutdown`；renderer 固定 `window.workbench.call(method, params): Promise<object>` 和 `subscribe(listener): () => void`。source 由 main 封装，不能采信 renderer 参数；内部注册方法不在公共白名单。公共 DTO 采用总览定义。

- [ ] **Step 1: 建立可安装的最小工程。** 确认仓库归属，再初始化/沿用 Git；创建配置和 bootstrap，用明确的 `py -3.14 -m venv .venv`。检查 Node 24、Python 3.14 x64；缺运行时明确失败，不改系统/Conda 环境。首次用 pip-tools 从 pyproject 的依赖/dev extra 生成带哈希 requirements.lock，后续先按锁文件装第三方依赖，再 `pip install --no-deps -e services/workbench`；npm 首次 install 生成锁，后续 ci。记录精确版本，npm 脚本定义 start/typecheck/test:e2e/package/make，增加 json-schema-to-typescript 开发依赖生成 TS，不自写 schema 转换器。Playwright 配置定位根目录测试；verify/build 对未实现阶段明确拒绝，不返回空成功。
- [ ] **Step 2: 写失败测试。** `test_decoder_handles_split_utf8_and_rejects_oversize` 拆分中文 UTF-8 及 LF 帧，再输入超限字节；`shell.spec.ts` 测未授权 IPC、renderer 无 Node API、schema 漂移检查失败。

```python
assert decoder.feed(first_half) == []
assert decoder.feed(second_half)[0]["method"] == "system.ping"
with pytest.raises(DomainError, match="FRAME_TOO_LARGE"):
    decoder.feed(b"x" * (8 * 1024 * 1024 + 1))
```

- [ ] **Step 3: 确认 Red。** `.\.venv\Scripts\python.exe -m pytest services/workbench/tests/test_rpc.py -q`；预期缺 decoder/dispatch 行为而失败，不能以依赖安装失败作为 Red。
- [ ] **Step 4: 实现最小通信。** stdout 仅协议、stderr 脱敏，日志 5 MiB 轮转并保留 5 份；main 以 `--data-dir <userData>` 传应用数据根，shell:false/windowsHide:true 启动。initialize 的 protocol_version=1、schema_version 初始为 0（Task 02 后读实际迁移版本），每进程生成 service_instance_id；15 秒握手、5 秒心跳/连续 3 次失败、EOF/退出清理。CSP、app origin、sender/main-frame 校验、preload 白名单按技术方案配置；实现契约导出与 `--check` 比较。build 用 PyInstaller onedir + Forge resources，把 Python 放 ASAR 外；实现受控子进程树清理封装，安装包内不依赖全局 Python。录音此任务只测 isTypeSupported，不访问麦克风。
- [ ] **Step 5: 确认 Green 与最小包。** 重跑目标 pytest；`npm --prefix apps/desktop run typecheck`；`npm --prefix apps/desktop run test:e2e -- --grep "@shell"`；`powershell -NoProfile -File scripts/build.ps1 -Stage M1`。预期启动握手、ping、拒绝非法调用、退出无遗留子进程；保存包大小/内存/版本，真实麦克风与密钥测试留后续任务。
- [ ] **Step 6: 提交。** 逐项暂存本任务文件，核对无 analysis 大文件/凭据/构建产物；`git commit -m "feat: bootstrap desktop and stdio service"`。

### Task 02: SQLite、幂等写与迁移备份

**Files:** Create `services/workbench/src/workbench/storage.py`、`migrations/0001_core.sql`、`tests/test_storage.py`；Modify `__main__.py`、`contracts.py`。0001 包含 schema_migrations/operations/drafts/notes 及当前所需约束，不提前建面试/MCP 空表。

**Interfaces:** Consumes `CommandMeta/DomainError`。Produces 总览的 `Storage.read/write_once/transaction`、`async Storage.open(path: Path) -> Storage`、`async Storage.close() -> None`、`async save_draft(command: dict, store: Storage) -> dict`；返回 draft_id/revision/saved_at。迁移校验与备份内聚于 storage.py。

- [ ] **Step 1: 写失败测试。** `test_operation_replay_precedes_revision_guard`：第一次写入成功，当前 revision 再变化，原 meta/payload 重试时用会抛错的 mutate；`test_migration_failure_preserves_backup` 和 `test_disk_full_rolls_back_operation` 注入迁移失败/SQLITE_FULL。

```python
assert replay_result == first_result
assert second_mutate_calls == 0
assert row_count_after_failed_write == row_count_before
assert backup_integrity == "ok"
```

- [ ] **Step 2: 确认 Red。** `.\.venv\Scripts\python.exe -m pytest services/workbench/tests/test_storage.py -q`；预期幂等顺序、回滚或备份断言失败。
- [ ] **Step 3: 实现。** 单写线程、参数化 SQL、JSON/FK/唯一约束，归属检查后查询 operation；仅新操作进入状态检查的 mutate。草稿按 revision 更新；同 ID 不同请求哈希冲突。迁移先 backup API，校验 checksum/integrity_check，失败禁写并保留备份；不复制正在 WAL 模式下的孤立主文件。
- [ ] **Step 4: 确认 Green。** 重跑目标测试，增加进程重开后 replay、只读/锁住/满盘、800 ms 保存尝试与 ACK 字段检查；预期操作结果和业务写同成败、无明文密钥列。
- [ ] **Step 5: 提交。** 暂存本任务具体文件与新增契约，`git commit -m "feat: add transactional storage and idempotent writes"`。

### Task 03: 任务队列、事件、取消与恢复

**Files:** Create `src/workbench/tasks.py`、`migrations/0002_tasks.sql`、`tests/test_tasks.py`、`tests/test_recovery.py`；Create renderer `pages/TaskPage.tsx`、`hooks/useTask.ts`；Modify `rpc.py`、`contracts.py`、`App.tsx`。迁移创建 tasks/task_runs/task_events。

**Interfaces:** Consumes Storage；Produces 总览 TaskService API，以及 `async get(task_id: str) -> dict`、`async list_events(task_id: str, after_seq: int) -> list[dict]`、`async recover_startup() -> list[dict]`。create command 采用技术方案的 task_type/workspace_id/agent_config_version_id/material_version_ids/input + operation_id；此阶段用内部受控测试流程，不对用户开放虚假 Agent。测试流程的 workspace/agent 引用暂为 null；不向尚未创建的表声明外键。Task 04/05 接入后，正式任务创建必须验证真实空间与 Agent 版本归属；这些顶层关联由服务校验和不可变快照保护，归档/删除不得留下历史缺口。

- [ ] **Step 1: 写失败测试。** `test_cancel_fences_late_commit` 取得 run、取消后尝试提交；`test_waiting_user_releases_slot`、`test_restart_never_replays_queued`、`test_snapshot_then_events_has_no_gap` 使用真实临时库和受控异步 barrier。

```python
assert late_error.code == "STALE_RUN"
assert generated_rows_after_cancel == 0
assert max_active_executions == 1
assert restarted_task["status"] == "interrupted"
assert delivered_seqs == sorted(set(expected_seqs))
```

- [ ] **Step 2: 确认 Red。** `.\.venv\Scripts\python.exe -m pytest services/workbench/tests/test_tasks.py services/workbench/tests/test_recovery.py -q`；预期 run 栅栏/恢复断言失败。
- [ ] **Step 3: 实现。** 仅允许技术方案状态迁移，FIFO 一个槽，waiting_user 释放；取消先事务撤销 run，再停请求。commit_run 内验证状态/run 后写业务和事件；事件提交后推送，快照带 last_seq、按 seq 补齐。启动旧 running/cancelling/queued→interrupted，等待用户保持；UI 显式继续且不自动重发。
- [ ] **Step 4: 确认 Green。** 重跑目标测试，并在真实子进程中断管道；`npm --prefix apps/desktop run test:e2e -- --grep "@tasks"`。预期结果先提交则保留、取消后迟到不写、旧实例事件不影响新界面。
- [ ] **Step 5: 提交。** `git commit -m "feat: add task queue cancellation and recovery"`，仅暂存该任务文件及生成契约。

### Task 04: 工作区、真实资料与来源快照

**Files:** Create `src/workbench/{workspaces,materials,paths}.py`、`migrations/0003_materials.sql`、`tests/test_materials.py`；Create main `dialogs.ts`、renderer `pages/{HomePage,WorkspacePage}.tsx`、`components/Sidebar.tsx`；Modify bridge/preload/App/契约。迁移创建 workspaces/directory_links/materials/material_versions。

**Interfaces:** Consumes Storage 与 main 内部注册入口。Produces `async create_workspace(command: dict, store: Storage) -> dict`、`async import_files(command: dict, store: Storage) -> dict`、`async import_text(command: dict, store: Storage) -> dict`、`async check_freshness(command: dict, store: Storage) -> dict`；`read_selected_file(path: Path, grant: dict) -> dict` 返回正文/哈希/编码/行范围。平台方法 chooseDirectory/chooseFiles 只返回服务登记的 grant ID。

- [ ] **Step 1: 写失败测试。** `test_scope_rejects_prefix_junction_and_replaced_file`；`test_text_limits_and_encoding` 测 200000/200001、合计 1000000/1000001 字节；`test_unlinked_source_uses_snapshot_without_reading_path`；两空间分别建资料验证不能借 ID 访问。

```python
assert excluded_files_sent == []
assert oversized_error.code == "CONTEXT_TOO_LARGE"
assert cross_workspace_error.code == "SOURCE_OUT_OF_SCOPE"
assert old_version["sha256"] == original_hash
assert filesystem_reads_after_unlink == 0
```

- [ ] **Step 2: 确认 Red。** `.\.venv\Scripts\python.exe -m pytest services/workbench/tests/test_materials.py -q`；Windows junction 用临时目录创建并清理，不能因缺权限静默跳过整个资料范围测试。
- [ ] **Step 3: 实现。** 目录关联只列元数据、明确选择才读正文；默认排除凭据/依赖/缓存/二进制，特殊文件单独确认。真实路径段、大小写、reparse/UNC/设备路径/ADS 检查，打开后核对目标/标识与前后 stat；UTF-8/BOM 失败显示重新选编码。来源版本不可变，变化时由用户选择旧快照/新版/移除。页面实现办公/开发/设计分类与空间，选材和预览分开。
- [ ] **Step 4: 确认 Green。** 重跑目标测试；`npm --prefix apps/desktop run test:e2e -- --grep "@materials"`；预期预览真实内容、请求仅选中资料、移除关联不删原文件、空间隔离。
- [ ] **Step 5: 提交。** `git commit -m "feat: add scoped workspaces and source snapshots"`。

### Task 05: DeepSeek 配置、密钥与文本请求

**Files:** Create `src/workbench/providers/{__init__,config,deepseek}.py`、`migrations/0004_providers.sql`、`tests/test_providers.py`、`tests/fixtures/http_provider.py`、renderer `pages/SettingsPage.tsx`；Modify contracts/RPC。迁移包含 provider_configs/provider_config_versions 与只够内置流程引用的 agent_configs/agent_config_versions 初始记录，M3 再开放自定义编辑。

**Interfaces:** Consumes TaskService 协调器、ModelRequest/ModelResult。Produces `async DeepSeekClient.complete(request: ModelRequest, cancel: asyncio.Event) -> ModelResult`、`async update_provider(command: dict, store: Storage) -> dict`、`set_secret(secret_ref: str, value: str) -> None`、`async test_provider(command: dict, store: Storage, tasks: TaskService) -> dict`。完整请求仅在 Python 内构造，setSecret 不回显。

- [ ] **Step 1: 写失败测试。** `test_provider_errors_preserve_input_and_redact_secrets`、`test_retry_only_explicit_no_content_error`：替身返回 401、429/5xx、空内容、截断 SSE、已出内容后断线，keyring 用可控测试后端；Windows 系统后端另做真实验证。

```python
assert calls_after_explicit_429 <= 2
assert calls_after_unknown_disconnect == 1
assert secret_value not in captured_logs + exported_config
assert connection_test_materials == []
```

- [ ] **Step 2: 确认 Red。** `.\.venv\Scripts\python.exe -m pytest services/workbench/tests/test_providers.py -q`；预期超时/重试或脱敏断言失败。
- [ ] **Step 3: 实现。** endpoint/model 配置版本、Windows 系统 keyring 后端白名单、自检失败不降级；默认 deepseek-flash，JSON Output 和 thinking disabled；connect=10/idle=60/total=180 秒。未知断开不重发、取消关闭流，完整 SSE 事件解析；最小连接测试不带资料，进入统一执行槽。
- [ ] **Step 4: 确认 Green。** 重跑替身测试；在安装包配置测试密钥，完成系统后端存/取/删与一条最小真实请求，日志只显示 request ID/耗时/用量。缺账号时记录 blocked，不能写“真实连接通过”。
- [ ] **Step 5: 提交。** `git commit -m "feat: integrate DeepSeek and system secret storage"`，不提交凭据或原始请求。

### Task 06: 带来源校验的候选题生成

**Files:** Create `src/workbench/{context,questions}.py`、`flows/{__init__,questions}.py`、`prompts/questions.txt`、`migrations/0005_candidates.sql`、`tests/test_candidates.py`；Create renderer `pages/GeneratePage.tsx`；Modify tasks/RPC/契约。0005 创建 candidate_batches，Question/Candidate DTO 的字段沿技术方案 7.2 定义。

**Interfaces:** Consumes DeepSeekClient、MaterialVersion 快照、TaskService.commit_run。Produces `build_context(materials: list[dict], input_tokens: int=24000, output_tokens: int=8000) -> dict`、`validate_candidates(payload: dict, sources: list[dict]) -> dict`、`async run_question_generation(task_id: str, run_id: str, store: Storage, client: DeepSeekClient, tasks: TaskService) -> dict`。

- [ ] **Step 1: 写失败测试。** `test_candidate_validation_and_batch_resume`：请求 11 道分 10+1、断开后只补缺批；缺字段/假 source/越界行号/空输出不入库；`test_cancel_during_repair_cannot_publish` 在唯一一次结构修复中取消。预算含 prompt/schema，UTF-8 估计保守且标估计。

```python
assert requested_batch_sizes == [10, 1]
assert repair_calls <= 1
assert invalid_result["can_commit"] is False
assert published_batches_after_cancel == 0
assert uploaded_source_ids == selected_version_ids
```

- [ ] **Step 2: 确认 Red。** `.\.venv\Scripts\python.exe -m pytest services/workbench/tests/test_candidates.py -q`；预期数量/来源/取消栅栏失败。
- [ ] **Step 3: 实现。** 正文范围与 token 预算预检，不够则阻断并让用户缩小范围；无资料强制 model_training。保留主题摘要、分批检查点，完整结果经 DTO/来源校验再生成服务分配 candidate_id；少于请求数量准确显示，不自动无限补齐。UI 显示真实步骤、字段错误、编辑/选择/取消，等待检查释放槽。
- [ ] **Step 4: 确认 Green。** 重跑 pytest；`npm --prefix apps/desktop run test:e2e -- --grep "@candidates"`；预期原始响应不能直接入库、取消无迟到批次、重开可检查已保存候选。
- [ ] **Step 5: 提交。** `git commit -m "feat: generate validated interview candidates"`。

### Task 07: 题库事务、版本、搜索与 JSON 导出

**Files:** Modify `questions.py`；Create `migrations/0006_question_bank.sql`、`tests/test_questions.py`、`src/workbench/exports.py`、renderer `pages/BankPage.tsx`；Modify main dialogs/契约。迁移包含 questions/question_versions/question_search/candidate_commits。

**Interfaces:** Consumes Storage.write_once 与候选版本。Produces `normalize_title(title: str) -> str`、`async commit_candidates(command: dict, store: Storage) -> dict`、`async update_question(command: dict, store: Storage) -> dict`、`async list_questions(command: dict, store: Storage) -> dict`、`async export_questions(command: dict, store: Storage) -> dict`、`atomic_export(target_grant: dict, content: bytes) -> dict`。列表返回 items/total，提交返回 created/updated/skipped/committed_question_version_ids。

- [ ] **Step 1: 写失败测试。** `test_commit_five_then_retry_with_different_operation` 选 5/10、先同 ID 再换 ID 保存；`test_edit_versions_and_similarity_never_auto_merge`；`test_search_literal_wildcards_and_export_scope` 查询 `%/_`、空结果和跨空间导出。

```python
assert question_count_after_all_retries == 5
assert old_version["body_json"] == original_body
assert similar_question_was_auto_deleted is False
assert empty_search["items"] == []
assert secret_value not in exported_json
```

- [ ] **Step 2: 确认 Red。** `.\.venv\Scripts\python.exe -m pytest services/workbench/tests/test_questions.py -q`；预期重复写/覆盖历史/检索范围失败。
- [ ] **Step 3: 实现。** NFKC/casefold/空白规范化、保留代码符号；明确重复提示，近似仅比较。按技术方案事务顺序处理整批用户选择，唯一映射跨 operation 防重；题库修订建新版本，归档不删除历史。检索投影同事务更新，LIKE 转义、页长默认 50/最多 200。导出显式字段与选定来源，临时文件原子替换且显示覆盖确认。
- [ ] **Step 4: 确认 Green。** 重跑 pytest；`npm --prefix apps/desktop run test:e2e -- --grep "@bank"`；10000 题至少 100 次查询记录 P95≤500 ms 的实际环境，未达标才验证 SQLite FTS5 trigram 后替换投影，不添加向量库。
- [ ] **Step 5: 提交。** `git commit -m "feat: add versioned question bank and JSON export"`。

### Task 08: 草稿 ACK、共用导航与离线操作

**Files:** Create renderer `hooks/useDraft.ts`、`components/{SaveStatus,ErrorNotice}.tsx`；Modify HomePage/TaskPage/GeneratePage/BankPage/WorkspacePage/App/styles；Create `tests/e2e/drafts.spec.ts`、`services/workbench/tests/test_drafts.py`；Modify drafts RPC 注册。

**Interfaces:** Consumes drafts.get/save 的 revision/saved_at、TaskService.get。Produces `useDraft(owner: {type: string; id: string}): {value: object; setValue(value: object): void; flush(): Promise<void>; saved: boolean}`；数据库仍由 Task 02 的 save_draft 写入，不另造前端持久化。

- [ ] **Step 1: 写失败测试。** `drafts.spec.ts` 中 `@drafts ignores stale ack and preserves unsaved input`：连续输入、旧 ACK、切模块/页签、断开 Python/断网、恢复；`test_draft_revision_conflict` 用实际库验证。

```typescript
expect(savedIndicator).toBe(false); // 旧 ACK 不能覆盖当前编辑的保存状态
expect(restoredDraft).toBe(latestAcknowledgedDraft);
expect(copyableTextAfterFailure).toBe(latestEditedText);
```

- [ ] **Step 2: 确认 Red。** `npm --prefix apps/desktop run test:e2e -- --grep "@drafts"`；预期旧确认/切页丢失断言失败，先确保不是应用无法启动。
- [ ] **Step 3: 实现。** 500 ms debounce、800 ms 内尝试、同草稿一个在途请求，切页 flush；ACK 只覆盖对应 revision。共用侧栏、办公/开发/设计分类保留输入与所选空间，空态/错误有可复制内容；任务右侧步骤/资料/成果窄屏堆叠。离线题库/笔记可读写，云动作解释依赖并保留输入。
- [ ] **Step 4: 确认 Green。** 重跑目标 e2e 与 `.\.venv\Scripts\python.exe -m pytest services/workbench/tests/test_drafts.py -q`；检查两档桌面尺寸/键盘/减少动态效果，记录本地导航反馈延迟，不把 390px 当客户端发布目标。
- [ ] **Step 5: 提交。** `git commit -m "feat: persist drafts with acknowledged save state"`。

### Task 09: M1 实际切片验收与交接

**Files:** Create `tests/e2e/m1-flow.spec.ts`、`docs/development/acceptance/m1.md`；Modify scripts/verify.ps1、scripts/build.ps1、README.md。证据写 `output/verification/<date>-M1/`，不加入真实凭据/私人正文。

**Interfaces:** Consumes Task 01～08 的真实 RPC/页面；Produces `verify.ps1 -Stage M1 [-Live]`，输出 result.json、报告路径和明确退出码。无新增业务接口。

- [ ] **Step 1: 写失败测试。** `@M1 selected sources to five saved questions` 在桌面通过真实文件选择、替身生成 10 题、修改/选 5、重复保存、重开检索导出；刻意断开本地服务后输入仍可复制。

```typescript
expect(savedQuestionCount).toBe(5);
expect(reopenedQuestionCount).toBe(5);
expect(sentFileIds).toEqual(selectedFileIds);
expect(exportedQuestionIds).toEqual(savedQuestionIds);
```

- [ ] **Step 2: 运行并定位 Red。** `powershell -NoProfile -File scripts/verify.ps1 -Stage M1`；新端到端用例若失败，记录具体未贯通环节；已经通过则保留现状，不故意破坏业务制造 Red。
- [ ] **Step 3: 补齐联调与真实验收。** 只修此切片暴露问题；`powershell -NoProfile -File scripts/verify.ps1 -Stage M1 -Live` 执行真实 DeepSeek 样本并人工核对来源/合理方案，再生成安装包，在无 Python/Node 的 Windows x64 环境启动。账号/环境缺失时标 blocked，保留自动化通过范围。
- [ ] **Step 4: 核对门禁。** AC01～05、19、21/23 的题库切片证据齐全、无阻塞项；文本连接、系统密钥和发行包必须有实际结果。m1.md 记录版本、资源、真服务/替身、限制和恢复步骤。
- [ ] **Step 5: 提交。** `git commit -m "test: verify M1 source to question-bank workflow"`；README 写 M1 实际状态，只有上述门禁满足才进入 M2。
