import { PAGES, PRIMARY_PAGES, type PageId } from '../navigation';
import { Icon } from './Icon';

interface SidebarProps {
  activePage: PageId;
  onNavigate: (page: PageId) => void;
}

export function Sidebar({ activePage, onNavigate }: SidebarProps) {
  return (
    <aside className="sidebar" aria-label="全局导航">
      <div className="brand">
        <div className="brand-name">
          知序<span className="brand-dot">.</span>
        </div>
        <div className="brand-sub">YOUR AI WORKBENCH</div>
      </div>

      <nav className="nav" aria-label="主导航">
        {PRIMARY_PAGES.map((page) => (
          <button
            key={page}
            type="button"
            className={`nav-item ${activePage === page ? 'active' : ''}`}
            aria-current={activePage === page ? 'page' : undefined}
            aria-label={PAGES[page].label}
            onClick={() => onNavigate(page)}
          >
            <Icon name={PAGES[page].icon} />
            <span>{PAGES[page].label}</span>
            {page === 'assistant' ? <span className="beta-label">BETA</span> : null}
          </button>
        ))}
      </nav>

      <div className="sidebar-section">
        <div className="sidebar-section-head">
          <span>
            任务 <span className="dim">(0)</span>
          </span>
        </div>
        <p className="sidebar-empty">任务记录将在本地服务接入后显示。</p>
        <button
          type="button"
          className="text-link"
          onClick={() => onNavigate('tasks')}
        >
          查看全部任务 <Icon name="arrow" size={14} />
        </button>
      </div>

      <div className="sidebar-section">
        <div className="sidebar-section-head">
          <span>
            空间 <span className="dim">(0)</span>
          </span>
        </div>
        <p className="sidebar-empty">工作区与目录关联在资料库页管理。</p>
        <button
          type="button"
          className="text-link"
          onClick={() => onNavigate('workspace')}
        >
          打开资料库 <Icon name="arrow" size={14} />
        </button>
      </div>

      <div className="sidebar-footer">
        <button
          type="button"
          className={`nav-item ${activePage === 'settings' ? 'active' : ''}`}
          aria-current={activePage === 'settings' ? 'page' : undefined}
          aria-label="设置与工具"
          onClick={() => onNavigate('settings')}
        >
          <Icon name="settings" />
          <span>设置与工具</span>
        </button>
        <div className="user">
          <span className="avatar">我</span>
          <div>
            <strong>本地用户</strong>
            <small>本地资料 · 云端能力</small>
          </div>
        </div>
        <p className="sidebar-boundary">共用导航已接通；业务数据尚未接入。</p>
      </div>
    </aside>
  );
}
