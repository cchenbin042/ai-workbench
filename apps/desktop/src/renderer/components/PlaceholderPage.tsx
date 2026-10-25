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
      {!['more', 'assistant'].includes(page) ? (
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

