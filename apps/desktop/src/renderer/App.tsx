import { useState } from 'react';

import { Launcher, type Scene } from './components/Launcher';
import { Sidebar } from './components/Sidebar';
import { StatusPanel } from './components/StatusPanel';
import { useServiceStatus } from './hooks/useServiceStatus';

export default function App() {
  const connection = useServiceStatus();
  const [scene, setScene] = useState<Scene>('office');

  return (
    <div className="app-shell">
      <Sidebar />
      <main className="workspace">
        <header className="topbar">
          <div className="breadcrumb">
            <span className="breadcrumb-quiet">一个入口，开始不同的工作</span>
          </div>
          <div className="topbar-actions">
            <span className="prototype-tag">脚手架 · Task 01</span>
            <span className="topbar-version">v0.1.0</span>
          </div>
        </header>
        <Launcher scene={scene} onSceneChange={setScene} />
      </main>
      <StatusPanel connection={connection} />
    </div>
  );
}
