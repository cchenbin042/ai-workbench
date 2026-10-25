# T007：Claude Code / OpenCode 联合 PRD 评审

## 1. 任务信息

| 字段 | 内容 |
| --- | --- |
| 任务编号 | T007 |
| 类型 / 关联里程碑 | 产品评审支撑 / M1～M3 建议，不直接改变既有范围 |
| 状态 | 已完成 |
| 创建日期 | 2026-10-19 |
| 开始日期 | 2026-10-19 |
| 最近更新 | 2026-10-19 |
| 完成日期 | 2026-10-19 |
| 最近回写 | 2026-10-19 |
| 总文档 | [master-plan.md](../master-plan.md) |
| 授权依据 | 用户要求协调 Claude Code、OpenCode 审查当前 PRD，讨论不合理之处并给出优化方案 |
| 评审基线 | [PRD v1.0](../../product/prd-ai-workbench-v1.md)、[接手指南](../agent-onboarding.md)、现有技术方案与任务记录 |

## 2. 目标、范围与所有权

输出可供用户决策的优化建议：哪些问题确实存在、为何需要改、推荐如何改、如何验收，以及有哪些意见分歧。保留原 PRD、业务代码和已确认用户要求；本任务不会自行批准功能删减、改变里程碑或启动开发。

- Claude Code：产品价值、首版范围与用户承诺审查；只写自己的评审报告。
- OpenCode：流程边界、可靠性与验收可执行性审查；只写自己的评审报告。
- 协调者：核对证据、主持交叉讨论、保存综合方案与协作记录、维护台账。
- 各智能体共用工作区，禁止覆盖他人文件和既有未提交改动；不运行安装、业务测试或 Git 提交/推送。

## 3. 功能点与验收

| 编号 | 预期结果 | 状态 |
| --- | --- | --- |
| F01 | 通过真实 Orca 运行时启动用户指定的 Claude Code 与 OpenCode，各自产出独立评审 | 已完成 |
| F02 | 两方阅读对方报告，对关键分歧交叉质询，保留共识和异议 | 已完成 |
| F03 | 综合方案包含建议优先级、条款修改、范围/里程碑建议、验收与待决策项 | 已完成 |
| F04 | 校验链接、原 PRD 未变、协作生命周期及文档一致性，并回写总览 | 已完成 |

## 4. 开发记录

### 2026-10-19 / F01：建立真实联合评审

- 使用 `orchestration` 与 `pm-agent` skill；CLI 为 `orca`，运行时 1.4.230。沙箱阻止访问 CLI，已通过命令提权审批读取指南并调用运行时。
- Run：`run_0b199c52dfdc`。
- Claude Code：`task_d1b6ee4ed22f` / `ctx_999b750fb99d`，启动回执 effective agent 为 `claude`，turnStart observed。
- OpenCode：`task_c21fca1b4ed3` / `ctx_aa4d1d959116`，启动回执 effective agent 为 `opencode`，输入 accepted；turnStart 观测不受支持，不据此声称已完成。
- 两者均沿用用户配置的模型，未指定或声称具体模型。
- 当前工作区已有 T006 文档未提交改动，保留。

## 5. 产物与验证

| 产物 | 状态 |
| --- | --- |
| [Claude Code 评审报告](../../product/reviews/2026-10-19-claude-prd-review.md) | 两轮完成；9 个独立问题、交叉回应与撤回项 |
| [OpenCode 评审报告](../../product/reviews/2026-10-19-opencode-prd-review.md) | 两轮完成；10 个独立问题、交叉回应与收窄项 |
| [综合优化方案](../../product/2026-10-19-prd-optimization-proposal.md) | 已保存：10 项核心建议、11 条验收、讨论表与两项待决策事项 |
| 链接/变更/生命周期核验 | 6 份 UTF-8 文档、70 个本地链接、占位符、差异与原基线未改检查通过；生命周期已核验 |

### 2026-10-19 / F02～F03：交叉讨论与综合

- 第一轮两个 Task/Dispatch 均合法结算 succeeded，读取报告后复用同一 Claude/OpenCode 会话进行第二轮，不启动替代 agent。
- Claude 第二轮：`task_6da2b9260c35` / `ctx_e91de177fe97`；OpenCode 第二轮：`task_f99f7eb1629f` / `ctx_bec9ac2e8ce9`。两者均发送合法 succeeded 完成报告。
- 双方撤回完整重排 M1、将资料限制直接称作数值冲突、以固定百分比/双人盲评作为单人产品硬门槛等观点。
- 综合方案保留选行能力、备份清理深度等分歧，给出协调者推荐；未把所有条目伪装成一致通过。
- 只读核对 `_requeue`：恢复按用户点击顺序追加队列，不承诺自动保留旧顺序；已据此修正综合方案。
- 原 PRD、技术方案、apps/services/contracts/scripts/tests 的 `git diff --exit-code` 为 0；未运行业务测试或供应商请求。
- 处理完消息后对两项最终 dispatch 执行 worker-release，返回 retained/external_terminal/processAction:none；未强制关闭。reclaimable 查询为空，四项 dispatch 均已结算。

## 6. 实际文件改动

- 新增两份评审报告、一份综合方案及本任务记录。
- README 添加综合方案入口；总览登记 T007、同日汇总及状态。
- 保留先前 T006 的未提交改动；原 PRD、技术方案、业务代码和实施计划不变。

## 7. 验证与限制

- 已确认真实 Orca agent 启动/复用回执、四项 succeeded 的 worker_done、消息确认和无待回收项。
- 最终 PowerShell 文档校验通过：6 份 UTF-8 文档、70 个本地链接均存在，无未完成占位符；四项 dispatch、保留的分歧与队列真实语义均已写入方案。
- `git diff --exit-code` 核对原 PRD、技术方案、apps/services/contracts/scripts/tests 和实施计划均未改；`git diff --check` 通过。
- 无真实 DeepSeek/ASR/MCP 测试、无安装/构建/提交/推送，无私人课程或源码读取；报告中的旧基线不是本轮复跑。

## 8. 接续与回写

2026-10-19：F01～F04 均完成。两轮联合评审、综合方案、文档和生命周期核验已完成，交付用户审阅。原 PRD 与现有门禁不变；真正范围取舍是内部试用/正式 M1 打包门禁关系及课程“第一版”的决策沿革。只有采纳后才同步改 PRD/计划，业务下一步仍为 M1 Task 04。
