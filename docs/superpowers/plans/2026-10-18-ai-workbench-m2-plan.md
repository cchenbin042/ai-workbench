# 知序 M2 文字训练闭环 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在真实题库上完成一次有依据追问的文字面试，保存报告、成果及回忆复习，并能从已确认步骤恢复。

**Architecture:** 复用 M1 的 SQLite、任务/run 栅栏和文本客户端。面试由本地状态机决定提交与阶段，模型只提供受校验建议；报告、成果和用户笔记分别版本化。

**Tech Stack:** 既有 Electron/React/Python/SQLite，DeepSeek、受限 Markdown、pytest、Playwright。

**Spec:** [技术方案第 4～8、11～13 节](../../technical/technical-design-v1.md)、[PRD](../../product/prd-ai-workbench-v1.md)、[总览及公共接口](2026-10-18-ai-workbench-implementation-plan.md)、[M1 前置计划](2026-10-18-ai-workbench-m1-plan.md)。

## Global Constraints

继承总览全部约束；M1 门禁未通过不开始本计划。默认训练模式、20 分钟/5 主问题/最多 2 次追问均为软目标；只有活动面试接收回答。已提交答案不可覆盖；原操作重试先返回已有结果。模拟默认 DTO/事件不返回参考及未公开反馈；主动提示先记辅助再返回请求级别。复习自评只有 needs_practice/can_explain，不自动永久掌握；无总分、语音特征或人格评价。

## Review Focus

- 答案确认丢失、轮次已推进后用旧 revision 重试：返回原答案（Task 11、16）。
- 回答含 emoji/中英文混合：按 Unicode code point 验证追问摘录（Task 12）。
- 模拟提示失败或复习 reveal 写失败：不泄露未成功记账的参考（Task 12、15）。
- 题库/报告更新后重开旧面试与用户笔记：保留旧题、旧反馈和手工内容（Task 13、14）。
- 提前结束时尚有报告缺项、离线时重新进入：保留 finishing/partial 并仅重试缺项（Task 13、16）。

## 文件与契约分配

Task 10 拥有题目计划与活动面试；11 拥有答案提交、更正和分支；12 拥有追问/提示/单题反馈；13 拥有报告/笔记/Markdown 导出；14 拥有普通任务成果及交接；15 拥有回忆复习；16 确认整体恢复。所有任务只扩展自己 DTO/迁移和 RPC 注册，不替换 M1 事务、队列或来源模型。

### Task 10: 固定题目版本的面试准备与激活

**Files:** Create `services/workbench/src/workbench/interviews.py`、`migrations/0007_interviews.sql`、`tests/test_interviews.py`；Create renderer `pages/InterviewPage.tsx`、`components/InterviewSetup.tsx`、`tests/e2e/interview-setup.spec.ts`；Modify contracts/RPC/App。迁移创建 interviews/interview_turns/app_state。

**Interfaces:** Consumes Storage、TaskService.create、QuestionVersion；Produces `async create_interview(command: dict, store: Storage, tasks: TaskService) -> dict`、`async activate_interview(command: dict, store: Storage) -> dict`、`async get_interview(interview_id: str, store: Storage) -> dict`。create command 含 question_version_ids/role/mode/input_mode/duration_minutes/main_question_count/followup_limit + CommandMeta；默认公开响应只含当前题题干、提示状态与进度，不含答案。

- [ ] **Step 1: 写失败测试。** `test_one_selected_question_stays_one_and_freezes_settings` 选择 1 题，开始后修改全局默认/题库；`test_viewing_report_does_not_activate_interview`；空题/归档题阻断创建，切活动面试时已有录音或执行应先停止/等待保存。

```python
assert interview["question_count"] == 1
assert frozen_plan[0]["question_version_id"] == selected_version_id
assert interview["settings"]["followup_limit"] == 2
assert active_id_after_history_view == active_id_before
```

- [ ] **Step 2: 确认 Red。** `.\.venv\Scripts\python.exe -m pytest services/workbench/tests/test_interviews.py -q`；预期版本/活动指针断言失败。
- [ ] **Step 3: 实现。** 固定方向、分别记录的 Java/Python/Agent 深度、模式、参数、题目顺序和版本；不复制重复题凑数。preparing→awaiting_answer 保存第一题，Task 转 waiting_user 并释放槽。显式激活才改变单例指针；浏览报告/资料无此副作用。
- [ ] **Step 4: 确认 Green。** 重跑 pytest；`npm --prefix apps/desktop run test:e2e -- --grep "@interview-setup"`；无题时引导建题，手选单题能开始，修改默认不改变本场。
- [ ] **Step 5: 提交。** `git commit -m "feat: create versioned interview sessions"`，逐项暂存本任务代码/测试/契约。

### Task 11: 回答、跳过、不知道和追加更正

**Files:** Modify `interviews.py`；Create `migrations/0008_answers.sql`、`tests/test_answers.py`、`tests/e2e/answers.spec.ts`；Modify InterviewPage 与 contracts。迁移创建 answers/answer_corrections；为 M3 attachment 引用预留 nullable 字段，真正 FK 在 Task 17 迁移建立并验证。

**Interfaces:** Consumes write_once、TaskService、活动题快照；Produces `async submit_answer(command: dict, store: Storage, tasks: TaskService) -> dict`、`async add_correction(command: dict, store: Storage) -> dict`。命令包含 interview_id/turn_id/answer_text/answer_kind/input_mode/attachment_id + CommandMeta；answer_kind=answered/skipped/unknown。skip 入口路由到同一函数，不另写一套提交逻辑。

- [ ] **Step 1: 写失败测试。** `test_replay_after_turn_advance_returns_original_answer` 先写成功、模拟丢失确认、推进状态后用旧 meta 重试；再换操作 ID 重复交同 turn。`test_failed_followup_never_rolls_back_answer` 在提交后云调用失败；`test_correction_appends_without_overwrite`。

```python
assert replay["answer_id"] == original["answer_id"]
assert answers_for_turn == 1
assert persisted_text_after_model_error == submitted_text
assert original_text_after_correction == submitted_text
assert len(corrections) == 1
```

- [ ] **Step 2: 确认 Red。** `.\.venv\Scripts\python.exe -m pytest services/workbench/tests/test_answers.py -q`；预期过早 STALE_TURN 或重复写/原文覆盖失败。
- [ ] **Step 3: 实现。** 归属→幂等→新操作活动/轮次/revision，答案+检查点+事件同事务；唯一 turn 防跨操作双写。提交成功才异步排判断；UI 提交中禁重复、确认前保留文本，错误不清输入；skip/unknown 单列，追加更正引用原答案。
- [ ] **Step 4: 确认 Green。** 重跑 pytest；`npm --prefix apps/desktop run test:e2e -- --grep "@answers"`；同场一次一题、旧面试不收回答、断线重开只留一条答案。
- [ ] **Step 5: 提交。** `git commit -m "feat: persist immutable interview answers"`。

### Task 12: 有依据的追问、提示与反馈时机

**Files:** Create `src/workbench/flows/interview.py`、`prompts/{followup,feedback,hints}.txt`、`migrations/0009_feedback.sql`、`tests/test_interview_flow.py`、`tests/e2e/interview-modes.spec.ts`；Modify interviews.py、InterviewPage/契约。迁移创建 hint_events/feedback_versions。

**Interfaces:** Consumes DeepSeekClient.complete、commit_run、已提交答案；Produces `validate_basis(basis: dict, answers: list[dict]) -> dict`、`async advance_interview(task_id: str, run_id: str, store: Storage, client: DeepSeekClient, tasks: TaskService) -> dict`、`async request_hint(command: dict, store: Storage, client: DeepSeekClient, tasks: TaskService) -> dict`。feedback DTO 字段和 evidence 引用采用技术方案 8.3，所有响应先做公开字段投影。

- [ ] **Step 1: 写失败测试。** `test_followup_basis_uses_unicode_codepoints` 构造“线程池🙂queue”及伪造引用；`test_simulation_hints_persist_before_release` 检查默认 snapshot/事件和 reference 主动提示；`test_hint_storage_failure_returns_no_reference` 注入 hint_event 写失败；`test_training_and_simulation_feedback_timing` 测两模式、0～2 次追问、取消中断、未知回答无编造原话。

```python
assert basis_quote == answer_text[start_offset:end_offset]
assert published_followups_for_main <= 2
assert "answer_points" not in default_public_turn
assert hint_commit_time <= hint_response_time
assert returned_hint_after_storage_failure is None
assert simulated_feedback_before_finish == []
```

- [ ] **Step 2: 确认 Red。** `.\.venv\Scripts\python.exe -m pytest services/workbench/tests/test_interview_flow.py -q`；预期引用/提示记账/反馈时机断言失败。
- [ ] **Step 3: 实现。** 模型只建议 followup/close，本地约束次数、题目/回答引用、字符偏移；错误最多修复一次，失败保留答案。direction/location/outline/reference 提示先记账再显示；模拟主动提示只返回请求级别。训练主问题关闭后反馈，模拟结束后反馈；进度只计主问题，软时间不截断提交/录音。所有云输出经 run 栅栏发布。
- [ ] **Step 4: 确认 Green。** 重跑 pytest；`npm --prefix apps/desktop run test:e2e -- --grep "@modes"`；用真实回答抽样核对追问贴合原话、合理替代方案、不编造工作经历，证据不足进入 uncertain_points。
- [ ] **Step 5: 提交。** `git commit -m "feat: add grounded followups hints and feedback"`。

### Task 13: 版本化报告、独立笔记与 Markdown 导出

**Files:** Create `src/workbench/reports.py`、`migrations/0010_reports.sql`、`tests/test_reports.py`、renderer `pages/ReportPage.tsx`、`components/SafeMarkdown.tsx`、`tests/e2e/reports.spec.ts`；Modify interviews.py、exports.py、SettingsPage、契约。迁移创建 report_versions，用户笔记复用 notes。

**Interfaces:** Consumes feedback_versions、immutable answers、atomic_export；Produces `async finish_interview(command: dict, store: Storage, tasks: TaskService) -> dict`、`async build_report(task_id: str, run_id: str, store: Storage, client: DeepSeekClient, tasks: TaskService) -> dict`、`async save_report_note(command: dict, store: Storage) -> dict`、`async export_report(command: dict, store: Storage) -> dict`。原回答/反馈/笔记分别返回，partial/complete 明确。

- [ ] **Step 1: 写失败测试。** `test_early_finish_and_partial_report_resume`：提前结束、某题反馈失败、恢复仅补缺项；`test_regeneration_preserves_old_report_and_notes`；`test_markdown_export_has_answers_hints_sources_without_secrets`；前端测试 raw HTML/远程图片不会执行或自动加载。

```python
assert task_status_before_required_feedback == "queued"
assert report_after_one_failed_section["status"] == "partial"
assert completed_feedback_ids_after_retry == original_completed_ids
assert old_report_after_regeneration == old_report_before
assert user_note_after_regeneration == edited_user_note
```

- [ ] **Step 2: 确认 Red。** `.\.venv\Scripts\python.exe -m pytest services/workbench/tests/test_reports.py -q`；预期 finishing/版本覆盖/导出字段失败。
- [ ] **Step 3: 实现。** finish 保存结束意图→finishing→queued，完整报告后才 completed；统计从数据库计算，跳过和未完成范围单列。重生成固定输入并新增版本；笔记用独立 revision 保存，离线可改。Markdown 按白名单显示、禁止原始 HTML/远程图，外链经 main 校验；导出显式字段、排除非本轮正文。
- [ ] **Step 4: 确认 Green。** 重跑 pytest；`npm --prefix apps/desktop run test:e2e -- --grep "@reports"`；更新题库/重新生成/重启后旧报告和笔记不变，提前结束可导出已完成部分且标清缺项。
- [ ] **Step 5: 提交。** `git commit -m "feat: add versioned reports and safe Markdown export"`。

### Task 14: 普通任务成果、新稿比较与建题交接

**Files:** Create `src/workbench/artifacts.py`、`flows/generic.py`、`prompts/generic.txt`、`migrations/0011_artifacts.sql`、`tests/test_artifacts.py`、renderer `components/ArtifactEditor.tsx`、`tests/e2e/artifacts.spec.ts`；Modify TaskPage、materials.py、contracts。迁移创建 artifacts/artifact_versions，并在任务检查点记录后继成果版本。

**Interfaces:** Consumes DeepSeekClient、commit_run、SafeMarkdown、import_text；Produces `async run_generic(task_id: str, run_id: str, store: Storage, client: DeepSeekClient, tasks: TaskService) -> dict`、`async save_artifact_revision(command: dict, store: Storage) -> dict`、`async compare_artifacts(command: dict, store: Storage) -> dict`、`async handoff_to_questions(command: dict, store: Storage, tasks: TaskService) -> dict`。本阶段 run_generic 只调用文本生成，无外部工具；Task 20 再扩展工具循环。

- [ ] **Step 1: 写失败测试。** `test_user_edit_survives_model_revision_and_handoff`：先保存用户稿、续聊生成新稿、比较后仍保留原稿，再转建题；`test_cancel_cannot_overwrite_artifact`。

```python
assert saved_user_version["content_md"] == user_edited_text
assert generated_revision["base_version_id"] == user_version_id
assert handoff_material["sha256"] == selected_artifact_hash
assert original_artifact_after_handoff == original_artifact_before
assert automatically_saved_questions == []
```

- [ ] **Step 2: 确认 Red。** `.\.venv\Scripts\python.exe -m pytest services/workbench/tests/test_artifacts.py -q`；预期续聊覆盖或交接引用漂移失败。
- [ ] **Step 3: 实现。** model/user 分版本、明确保存、编辑 buffer 不被推送替换；模型新稿关联 base，用户比较后选择保存。交接复制选定版本成为 material_version，再创建建题任务，仍需候选校验/用户入库。generic 的内置默认配置只引用文本服务，权限不扩大。
- [ ] **Step 4: 确认 Green。** 重跑 pytest；`npm --prefix apps/desktop run test:e2e -- --grep "@artifacts"`；真实续聊一轮，切页签、取消、旧版本查看和导出不丢用户文本。
- [ ] **Step 5: 提交。** `git commit -m "feat: version artifacts and hand off snapshots to questions"`。

### Task 15: 先回忆、再核对的手动复习

**Files:** Create `src/workbench/reviews.py`、`migrations/0012_reviews.sql`、`tests/test_reviews.py`、renderer `pages/ReviewPage.tsx`、`tests/e2e/reviews.spec.ts`；Modify ReportPage/BankPage/契约。迁移创建 review_items/review_attempts 和未完成 attempt 唯一部分索引。

**Interfaces:** Consumes QuestionVersion、Storage.write_once/save_draft；Produces `async add_review(command: dict, store: Storage) -> dict`、`async start_review(command: dict, store: Storage) -> dict`、`async reveal_reference(command: dict, store: Storage) -> dict`、`async save_attempt(command: dict, store: Storage) -> dict`。reveal 先写 reference_seen_at 后返回参考，自评 needs_practice/can_explain。

- [ ] **Step 1: 写失败测试。** `test_reveal_assistance_survives_restart` 从两报告加入同题、开始回忆/看参考/重开；`test_failed_reveal_never_returns_reference` 注入存储失败；完成后再练创建新 attempt。

```python
assert unique_review_items == 1
assert initial_reference_fields == []
assert reopened_attempt["reference_seen_at"] is not None
assert returned_reference_after_failed_write is None
assert next_attempt_id != completed_attempt_id
```

- [ ] **Step 2: 确认 Red。** `.\.venv\Scripts\python.exe -m pytest services/workbench/tests/test_reviews.py -q`；预期辅助被清空/错误返回参考或重复复习项失败。
- [ ] **Step 3: 实现。** 同题合并来源，先发不含答案的回忆响应，草稿复用 ACK 保存；reveal 单调记账；保存自评/时间/是否辅助，不自动移除或永久掌握，支持未练/有记录筛选、手动移除和单题再面试。
- [ ] **Step 4: 确认 Green。** 重跑 pytest；`npm --prefix apps/desktop run test:e2e -- --grep "@reviews"`；断网回忆/笔记可保存，重开未完成草稿不清辅助事实。
- [ ] **Step 5: 提交。** `git commit -m "feat: add persistent recall and manual review"`。

### Task 16: 文字闭环、故障恢复与 M2 门禁

**Files:** Create `tests/e2e/m2-flow.spec.ts`、`services/workbench/tests/test_m2_faults.py`、`docs/development/acceptance/m2.md`；Modify verify.ps1、build.ps1、README.md；复用现有 e2e 进程启动 fixture，为测试服务注入提交前/后 barrier。

**Interfaces:** Consumes Task 10～15 的完整流程；Produces `verify.ps1 -Stage M2 [-Live]`，累计 M1 和 M2 检查/真实抽样证据，无新增业务入口。

- [ ] **Step 1: 写失败测试。** `test_kill_after_answer_commit_resumes_only_missing_work` 杀真实 Python 子进程；`test_cancel_race_preserves_committed_but_rejects_late`；`@M2 interview report recall restart` 桌面完整流程，包含模拟快照重开与辅助事实。

```python
assert answers_after_restart == 1
assert model_calls_before_user_resume == 0
assert persisted_feedback_versions == expected_confirmed_versions
assert stale_run_writes == 0
```

- [ ] **Step 2: 确认新用例执行结果。** `.\.venv\Scripts\python.exe -m pytest services/workbench/tests/test_m2_faults.py -q`；`npm --prefix apps/desktop run test:e2e -- --grep "@M2"`。若贯通已通过不故意改坏代码，否则记录具体 Red 并修复拥有问题的模块。
- [ ] **Step 3: 执行累计与真实样本。** `powershell -NoProfile -File scripts/verify.ps1 -Stage M2`；同命令加 `-Live` 核对实际追问、合理替代答案、uncertain/partial 与报告证据。真实服务失败保留原回答，语音/MCP 此时仍未完成。
- [ ] **Step 4: 核对门禁。** AC06～08、11～16、20 和 AC21/23 的文字相关部分；题库修订不改旧报告、笔记独立、复习辅助跨重启、离线可用，证据写 m2.md。生成本阶段 Windows 安装包重跑文字主流程。
- [ ] **Step 5: 提交。** `git commit -m "test: verify text interview recovery and review workflow"`；更新实际状态后再进入 M3。
