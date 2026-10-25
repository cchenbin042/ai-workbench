import { useCallback, useEffect, useState } from 'react';

import { Launcher, type Scene } from './components/Launcher';
import { PlaceholderPage } from './components/PlaceholderPage';
import { Sidebar } from './components/Sidebar';
import { StatusPanel } from './components/StatusPanel';
import { useServiceStatus } from './hooks/useServiceStatus';
import { WorkspacePage } from './pages/WorkspacePage';
import { PAGES, type PageId } from './navigation';

export default function App() {
  const connection = useServiceStatus();
  const [page, setPage] = useState<PageId>('home');
  const [scene, setScene] = useState<Scene>('office');
  const [draft, setDraft] = useState('');

  useEffect(() => {
    const frame = requestAnimationFrame(() => {
      document.getElementById('page-title')?.focus();
    });
    return () => cancelAnimationFrame(frame);
  }, [page]);

  const navigate = useCallback((next: PageId) => setPage(next), []);
  const current = PAGES[page];

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        跳到主要内容
      </a>
      <Sidebar activePage={page} onNavigate={navigate} />
      <main className="workspace" id="main-content" tabIndex={-1}>
        <header className="topbar">
          <div className="breadcrumb">
            {page === 'home' ? (
              <span className="breadcrumb-quiet">一个入口，开始不同的工作</span>
            ) : (
              <>
                <button
                  type="button"
                  className="breadcrumb-back"
                  onClick={() => navigate('home')}
                >
                  新建任务
                </button>
                <span className="breadcrumb-separator">›</span>
                <strong>{current.label}</strong>
              </>
            )}
          </div>
          <div className="topbar-actions">
            <span className="prototype-tag">共用壳 · T004</span>
            <span className="topbar-version">v0.1.0</span>
          </div>
        </header>
        {page === 'home' ? (
          <Launcher
            scene={scene}
            onSceneChange={setScene}
            draft={draft}
            onDraftChange={setDraft}
            onNavigate={navigate}
          />
        ) : page === 'workspace' ? (
          <WorkspacePage />
        ) : (
          <PlaceholderPage page={page} onNavigate={navigate} />
        )}
      </main>
      <StatusPanel connection={connection} />
    </div>
  );
}
