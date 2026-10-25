import { MORE_PAGES, PAGES, type PageId } from '../navigation';
import { Icon } from './Icon';

interface PlaceholderPageProps {
  page: PageId;
  onNavigate: (page: PageId) => void;
}

export function PlaceholderPage({ page, onNavigate }: PlaceholderPageProps) {
  const info = PAGES[page];

  return (
    <section className="placeholder-page" aria-labelledby="page-title">
      <span className="eyebrow">SHARED SHELL · {info.milestone}</span>
      <h1 id="page-title" tabIndex={-1}>
        {info.label}
      </h1>
      <p className="launcher-subtitle">{info.description}</p>

      {page === 'more' ? <MoreHub onNavigate={onNavigate} /> : null}
      {page === 'assistant' ? <AssistantHub onNavigate={onNavigate} /> : null}
      {page === 'settings' ? <SettingsOverview /> : null}
      {!['more', 'assistant', 'settings'].includes(page) ? (
        <MilestoneCard page={page} onNavigate={onNavigate} />
      ) : null}
    </section>
  );
}

function MilestoneCard({ page, onNavigate }: PlaceholderPageProps) {
  const info = PAGES[page];
  return (
    <div className="placeholder-card">
      <span className="pill">待接入</span>
      <h2>本页将在 {info.milestone} 接入</h2>
      <p>{info.description}</p>
      <p className="placeholder-note">当前只提供共用导航与页面壳，不展示伪造的业务数据。</p>
      <button type="button" className="text-link" onClick={() => onNavigate('home')}>
        返回首页 <Icon name="arrow" size={14} />
      </button>
    </div>
  );
}

function MoreHub({ onNavigate }: Pick<PlaceholderPageProps, 'onNavigate'>) {
  return (
    <>
      <div className="hub-grid">
        {MORE_PAGES.map((page) => (
          <button
            key={page}
            type="button"
            className="hub-card"
            aria-label={PAGES[page].label}
            onClick={() => onNavigate(page)}
          >
            <span className="suggestion-icon">
              <Icon name={PAGES[page].icon} size={17} />
            </span>
            <span>
              <strong>{PAGES[page].label}</strong>
              <small>{PAGES[page].description}</small>
            </span>
          </button>
        ))}
      </div>
      <p className="placeholder-note">这些入口使用共用导航；业务能力仍在后续里程碑。</p>
    </>
  );
}

function AssistantHub({ onNavigate }: Pick<PlaceholderPageProps, 'onNavigate'>) {
  return (
    <div className="hub-grid">
      <button
        type="button"
        className="hub-card"
        aria-label="面试题整理 Agent"
        onClick={() => onNavigate('bank')}
      >
        <span className="suggestion-icon">
          <Icon name="book" size={17} />
        </span>
        <span>
          <strong>面试题整理 Agent</strong>
          <small>从资料生成候选题并检查入库；M1 接入。</small>
        </span>
      </button>
      <button
        type="button"
        className="hub-card"
        aria-label="AI 面试官 Agent"
        onClick={() => onNavigate('interview')}
      >
        <span className="suggestion-icon">
          <Icon name="bot" size={17} />
        </span>
        <span>
          <strong>AI 面试官 Agent</strong>
          <small>文字训练、追问与报告；M2 接入。</small>
        </span>
      </button>
    </div>
  );
}

function SettingsOverview() {
  return (
    <div className="settings-grid">
      <div className="settings-card">
        <strong>DeepSeek 文本模型</strong>
        <span className="pill">未配置</span>
        <p>M1 Task 05 接入接口地址、模型与系统密钥存储。</p>
      </div>
      <div className="settings-card">
        <strong>语音转写</strong>
        <span className="pill">未配置</span>
        <p>M3 接入独立 ASR；当前不访问麦克风。</p>
      </div>
      <div className="settings-card">
        <strong>本地 MCP</strong>
        <span className="pill">未连接</span>
        <p>M3 接入 stdio 工具、权限交集与调用记录。</p>
      </div>
    </div>
  );
}
