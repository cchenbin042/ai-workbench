import type { PageId } from '../navigation';
import { Icon, type IconName } from './Icon';

export type Scene = 'office' | 'develop' | 'design';

interface Suggestion {
  icon: IconName;
  title: string;
  description: string;
  page: PageId;
}

interface SceneInfo {
  name: string;
  icon: IconName;
  subtitle: string;
  suggestions: Suggestion[];
}

const scenes: Record<Scene, SceneInfo> = {
  office: {
    name: '办公',
    icon: 'book',
    subtitle: '把琐碎交给助手，把时间留给真正重要的事。',
    suggestions: [
      {
        icon: 'book',
        title: '建立面试题库',
        description: '从岗位与资料生成候选题；M1 接入。',
        page: 'bank',
      },
      {
        icon: 'bot',
        title: 'AI 面试官',
        description: '文字训练、追问与报告；M2 接入。',
        page: 'interview',
      },
      {
        icon: 'layers',
        title: '整理学习笔记',
        description: '资料版本与来源快照；M1 Task 04。',
        page: 'workspace',
      },
    ],
  },
  develop: {
    name: '开发',
    icon: 'layers',
    subtitle: '理解项目的来龙去脉，让每次实现都更有思路。',
    suggestions: [
      {
        icon: 'folder',
        title: '项目理解',
        description: '只读目录关联与选材；Task 04。',
        page: 'workspace',
      },
      {
        icon: 'spark',
        title: '技术方案',
        description: '普通任务成果与交接；M2。',
        page: 'tasks',
      },
      {
        icon: 'bot',
        title: '项目面试',
        description: '基于真实资料出题；M1。',
        page: 'bank',
      },
    ],
  },
  design: {
    name: '设计',
    icon: 'spark',
    subtitle: '让一个模糊的想法，逐步变成可以看见的方案。',
    suggestions: [
      {
        icon: 'spark',
        title: '界面草图',
        description: '设计入口仅表示分类，不承诺生成能力。',
        page: 'agents',
      },
      {
        icon: 'layers',
        title: '信息架构',
        description: '后续按真实需求扩展。',
        page: 'agents',
      },
      {
        icon: 'book',
        title: '方案排版',
        description: '后续按真实需求扩展。',
        page: 'workspace',
      },
    ],
  },
};

interface LauncherProps {
  scene: Scene;
  onSceneChange: (scene: Scene) => void;
  draft: string;
  onDraftChange: (value: string) => void;
  onNavigate: (page: PageId) => void;
}

export function Launcher({
  scene,
  onSceneChange,
  draft,
  onDraftChange,
  onNavigate,
}: LauncherProps) {
  const current = scenes[scene];

  return (
    <section className="launcher" aria-labelledby="page-title">
      <span className="eyebrow">SHARED SHELL · T004</span>
      <h1 id="page-title" tabIndex={-1}>
        知序，和你一起完成<span className="heading-dot">。</span>
      </h1>
      <p className="launcher-subtitle">{current.subtitle}</p>

      <div className="scene-tabs" role="group" aria-label="工作模块">
        {(Object.keys(scenes) as Scene[]).map((key) => (
          <button
            key={key}
            type="button"
            aria-pressed={scene === key}
            className={`scene-tab ${scene === key ? 'selected' : ''}`}
            onClick={() => onSceneChange(key)}
          >
            <Icon name={scenes[key].icon} size={16} />
            {scenes[key].name}
          </button>
        ))}
      </div>

      <div className="composer">
        <textarea
          value={draft}
          onChange={(event) => onDraftChange(event.target.value)}
          placeholder="今天想一起完成什么？业务执行将在后续任务接入。"
          aria-label="任务描述"
        />
        <div className="composer-toolbar">
          <span className="composer-hint">共用壳阶段仅保留本地输入，不发送任何请求</span>
          <div className="composer-actions">
            <span className="model-status" title="M1 Task 05 接入">
              DeepSeek 未配置
            </span>
            <span className="model-status" title="M3 接入">
              语音未配置
            </span>
            <button
              type="button"
              className="send-button"
              disabled
              title="任务执行尚未接入"
              aria-label="发送任务（尚未接入）"
            >
              →
            </button>
          </div>
        </div>
        <div className="composer-context">
          <span className="context-chip" title="M1 Task 04 接入">
            <Icon name="folder" size={14} />
            未连接工作区
          </span>
          <span className="context-chip">
            <Icon name="shield" size={14} />
            只读访问
          </span>
          <span className="context-note">由你选择本次资料范围</span>
        </div>
      </div>

      <div className="suggestion-grid">
        {current.suggestions.map((item) => (
          <button
            key={item.title}
            type="button"
            className="suggestion-card"
            onClick={() => onNavigate(item.page)}
          >
            <span className="suggestion-icon">
              <Icon name={item.icon} size={17} />
            </span>
            <span>
              <strong>{item.title}</strong>
              <small>{item.description}</small>
            </span>
          </button>
        ))}
      </div>

      <div className="scaffold-boundary">
        <Icon name="check" size={16} />
        <div>
          <strong>本轮已接通</strong>
          <p>共用导航、Electron 桌面壳、受限 preload bridge、stdio JSON-RPC 握手与心跳。</p>
          <strong>尚未接入</strong>
          <p>真实资料读取、DeepSeek、题库、面试、语音、MCP 与安装包验收。</p>
        </div>
      </div>
    </section>
  );
}
