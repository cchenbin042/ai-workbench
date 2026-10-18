# 知序 · 个人 AI 工作台

日期：2026-10-18。当前阶段：**桌面壳、Python 服务与 SQLite 持久化已贯通；本地草稿保存/读取已实现，真实建题业务与服务发行包待完成。**

面向有 Java 背景、正在学习 Python/Agent 的个人开发者。借鉴 WorkBuddy 的共用导航、任务、资料、Agent 和成果组织，首批应用为面试题整理与 AI 面试官，再完善课程学习复盘。文本大模型方向为 DeepSeek 云端，本机不运行大模型。

## 当前交付

| 文件 | 用途 |
| --- | --- |
| [PRD v1.0](docs/product/prd-ai-workbench-v1.md) | 用户问题、首版范围、默认、11 项需求、数据/状态、24 项正式验收和里程碑 |
| [技术方案 v1.0](docs/technical/technical-design-v1.md) | Electron/React + Python + SQLite、通信与数据契约、任务恢复、模型/语音/MCP、分期验收与打包 |
| [实施方案](docs/superpowers/plans/2026-10-18-ai-workbench-implementation-plan.md) | M1/M2/M3 三份计划、接口与阶段验收；当前状态见开发台账 |
| [UI 页面与交互](docs/product/2026-10-18-workbench-ui-design.md) | 共用布局、13 类页面、动作/状态、响应式与截图 |
| [设计覆盖与实现差距](docs/product/2026-10-18-design-coverage.md) | 原型已做、演示、正式待开发及验证证据 |
| [原型体验说明](prototypes/workbench-ui/README.md) | 本机打开方式、体验顺序与检查命令 |
| [WorkBuddy 功能映射](docs/product/2026-10-18-workbuddy-feature-adaptation.md) | 借鉴点和自主实现边界 |
| [早期需求探索](docs/product/2026-10-18-learning-workbench-discovery.md) | 场景、确认记录与课程输入限制 |

当前行为以 PRD 为准，旧探索文档保留来历；原型用于交互表达，不替代正式验收。未明确的细节采用文档标明的设计默认，不记作用户逐项批准。

## 开发台账

- 总文档：[docs/development/master-plan.md](docs/development/master-plan.md)
- 任务明细：[docs/development/tasks/](docs/development/tasks/)
- 项目模板：[docs/development/task-template.md](docs/development/task-template.md)
- 维护规则：**每个开发任务完成后必须使用 `dev-task-tracker` skill 回写**；功能点完成即写明细，开发结束同步总文档。

## 后端脚手架

运行说明见 [services/workbench/README.md](services/workbench/README.md)，验证记录见 [backend-scaffold.md](docs/development/backend-scaffold.md)。在仓库根目录：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/bootstrap-backend.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify-backend.ps1
.\.venv\Scripts\python.exe -u -m workbench --data-dir 'D:\workbench data'
```

当前为本地 stdio 服务，不提供 HTTP 端口；需要向 stdin 发送 JSON-RPC。已提供 SQLite 与本地草稿保存/读取 RPC，使用示例见[后端说明](services/workbench/README.md)；模型调用、前端草稿持久化接入和安装包内 Python 服务继续按后续任务完成。

## 打开原型

在 PowerShell 启动本机静态服务：

```powershell
python -m http.server 8765 --bind 127.0.0.1 --directory 'D:\llm\agent\ai-workbench\prototypes\workbench-ui'
```

打开 `http://127.0.0.1:8765/`。推荐体验：资料库 → 添加一份笔记并选材 → 整理候选题 → 检查入库 → 单题面试 → 报告 → 加入复习 → 先回忆再核对。

直达页面：

- 任务工作台：`http://127.0.0.1:8765/?view=task-workbench`
- 资料库：`http://127.0.0.1:8765/?view=workspace`
- 题库：`http://127.0.0.1:8765/?view=bank`
- 报告示例：`http://127.0.0.1:8765/?view=report-example`
- 复习清单：`http://127.0.0.1:8765/?view=review`

原型资源来自本机；题库、笔记、回答及成果使用浏览器 localStorage。题目生成、追问、反馈、语音及 MCP 均为演示，未接入模型或外部工具，未读取真实学习项目。正式版的 SQLite、系统密钥、安全范围和恢复机制仍需实现。

## 验证与参考

本轮四组浏览器交互检查共 **42 项通过**，检查结果与截图保存在 `prototypes/workbench-ui/output/playwright`；详细范围和限制见[覆盖清单](docs/product/2026-10-18-design-coverage.md)。

既有输入与逆向资料：

- [WorkBuddy 5.8.3 分析报告](analysis/workbuddy-5.8.3/README.md)
- [深造播放器课程输入测试](analysis/szplayer-input-probe/README.md)

课程短片段音频已验证，播放器窗口画面仍为黑屏；不把原视频恢复或音画同步计为已解决。技术方案及其[文档检查记录](docs/technical/technical-design-verification.json)已提供，后续先按方案验证最小桌面包与本地通信，再完成 PRD 的 M1：真实资料 → DeepSeek 候选题 → 本地题库这条可用流程。真实模型、语音、MCP 和发行包测试仍待工程实现。
