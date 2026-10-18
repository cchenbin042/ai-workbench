import { Icon, type IconName } from './Icon';

interface NavItem {
  label: string;
  icon: IconName;
  hint: string;
}

const navItems: NavItem[] = [
  { label: '新建任务', icon: 'home', hint: '任务流程将在 M1 后续任务接入' },
  { label: '助理', icon: 'bot', hint: '内置 Agent 将在 M2 接入' },
  { label: '专家 · 技能 · 连接器', icon: 'layers', hint: '工具与 MCP 将在 M3 接入' },
  { label: '定时任务', icon: 'clock', hint: '后台调度不在 P0 范围' },
  { label: '资料库', icon: 'book', hint: '真实资料读取将在 M1 Task 04 接入' },
];

export function Sidebar() {
  return (
    <aside className="sidebar" aria-label="全局导航">
      <div className="brand">
        <div className="brand-name">
          知序<span className="brand-dot">.</span>
        </div>
        <div className="brand-sub">YOUR AI WORKBENCH</div>
      </div>

      <nav className="nav" aria-label="主导航">
        {navItems.map((item) => (
          <button key={item.label} type="button" className="nav-item" title={item.hint}>
            <Icon name={item.icon} />
            <span>{item.label}</span>
          </button>
        ))}
      </nav>

      <div className="sidebar-section">
        <span className="section-title">空间</span>
        <div className="space-item">
          <Icon name="folder" size={16} />
          <span>tiangong_agent</span>
        </div>
        <p className="space-description">Agent 学习与项目实践 · 只读关联将在 Task 04 建立</p>
      </div>

      <div className="sidebar-footer">
        <button type="button" className="nav-item" title="模型与工具配置将在后续任务接入">
          <Icon name="settings" />
          <span>设置与工具</span>
        </button>
        <p className="sidebar-boundary">脚手架阶段：未读取项目文件，未调用模型。</p>
      </div>
    </aside>
  );
}
