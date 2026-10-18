import { useState } from 'react';

import { Icon, type IconName } from './Icon';

export type Scene = 'office' | 'develop' | 'design';

interface SceneInfo {
  name: string;
  icon: IconName;
  subtitle: string;
  suggestions: Array<{ icon: IconName; title: string; description: string }>;
}

const scenes: Record<Scene, SceneInfo> = {
  office: {
    name: '办公',
    icon: 'book',
    subtitle: '把琐碎交给助手，把时间留给真正重要的事。',
    suggestions: [
      { icon: 'book', title: '建立面试题库', description: '从岗位与资料生成候选题；M1 接入。' },
      { icon: 'bot', title: 'AI 面试官', description: '文字训练、追问与报告；M2 接入。' },
      { icon: 'layers', title: '整理学习笔记', description: '资料版本与来源快照；M1 Task 04。' },
    ],
  },
  develop: {
    name: '开发',
    icon: 'layers',
    subtitle: '理解项目的来龙去脉，让每次实现都更有思路。',
    suggestions: [
      { icon: 'folder', title: '项目理解', description: '只读目录关联与选材；Task 04。' },
      { icon: 'spark', title: '技术方案', description: '普通任务成果与交接；M2。' },
      { icon: 'bot', title: '项目面试', description: '基于真实资料出题；M1。' },
    ],
  },
  design: {
    name: '设计',
    icon: 'spark',
    subtitle: '让一个模糊的想法，逐步变成可以看见的方案。',
    suggestions: [
      { icon: 'spark', title: '界面草图', description: '设计入口仅表示分类，不承诺生成能力。' },
      { icon: 'layers', title: '信息架构', description: '后续按真实需求扩展。' },
      { icon: 'book', title: '方案排版', description: '后续按真实需求扩展。' },
    ],
  },
};

interface LauncherProps {
  scene: Scene;
  onSceneChange: (scene: Scene) => void;
}

export function Launcher({ scene, onSceneChange }: LauncherProps) {
  const [draft, setDraft] = useState('');
  const current = scenes[scene];

  return (
    <section className="launcher" aria-labelledby="launcher-title">
      <span className="eyebrow">DESKTOP SCAFFOLD</span>
      <h1 id="launcher-title">
        知序，和你一起完成<span className="heading-dot">。</span>
      </h1>
      <p className="launcher-subtitle">{current.subtitle}</p>

      <div className="scene-tabs" role="tablist" aria-label="工作模块">
        {(Object.keys(scenes) as Scene[]).map((key) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={scene === key}
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
          onChange={(event) => setDraft(event.target.value)}
          placeholder="今天想一起完成什么？业务执行将在后续任务接入。"
          aria-label="任务描述"
        />
        <div className="composer-toolbar">
          <span className="composer-hint">脚手架阶段仅保存本地输入，不发送任何请求</span>
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

      <div className="suggestion-grid">
        {current.suggestions.map((item) => (
          <button
            key={item.title}
            type="button"
            className="suggestion-card"
            title="后续任务接入后可执行"
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
          <p>Electron 桌面壳、受限 preload bridge、stdio JSON-RPC 握手与心跳。</p>
          <strong>尚未接入</strong>
          <p>真实资料读取、DeepSeek、题库、面试、语音、MCP 与安装包验收。</p>
        </div>
      </div>
    </section>
  );
}
