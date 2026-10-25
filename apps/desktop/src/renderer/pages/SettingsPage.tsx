import { useCallback, useEffect, useRef, useState } from 'react';

interface ProviderConfig {
  provider_id: string;
  kind: 'text';
  version_no: number;
  endpoint: string;
  model_id: string;
  parameters: Record<string, unknown>;
  secret_ref: string | null;
  has_secret: boolean;
}

interface TaskSnapshot {
  task_id: string;
  status: 'queued' | 'running' | 'waiting_user' | 'completed' | 'failed' | 'cancelled';
  checkpoint: Record<string, unknown>;
}

interface TestOutcome {
  ok?: boolean;
  error_code?: string | null;
  latency_ms?: number | null;
  model_id?: string | null;
  request_id?: string | null;
  usage?: Record<string, number>;
}

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function sleep(milliseconds: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

export function SettingsPage() {
  const [config, setConfig] = useState<ProviderConfig | null>(null);
  const [endpoint, setEndpoint] = useState('');
  const [modelId, setModelId] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [testing, setTesting] = useState(false);
  const [outcome, setOutcome] = useState<TestOutcome | null>(null);
  const pollFrame = useRef(0);

  const call = useCallback(
    async <T,>(
      method: Parameters<typeof window.workbench.call>[0],
      params?: Record<string, unknown>,
    ): Promise<T> => (await window.workbench.call(method, params)) as T,
    [],
  );

  const loadConfig = useCallback(async () => {
    const result = await call<ProviderConfig>('providers.get', { kind: 'text' });
    setConfig(result);
    setEndpoint(result.endpoint);
    setModelId(result.model_id);
  }, [call]);

  useEffect(() => {
    loadConfig().catch((cause) => setError(messageOf(cause)));
  }, [loadConfig]);

  useEffect(() => () => {
    pollFrame.current += 1;
  }, []);

  const run = useCallback(async (action: () => Promise<string | void>) => {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const message = await action();
      if (message) setNotice(message);
    } catch (cause) {
      setError(messageOf(cause));
    } finally {
      setBusy(false);
    }
  }, []);

  const saveProvider = () =>
    run(async () => {
      const result = await call<ProviderConfig>('providers.update', {
        operation_id: crypto.randomUUID(),
        kind: 'text',
        endpoint: endpoint.trim(),
        model_id: modelId.trim(),
      });
      setConfig(result);
      return '配置已保存，新任务将使用新版本。';
    });

  const saveSecret = () =>
    run(async () => {
      const secret = apiKey;
      setApiKey('');
      await call('providers.setSecret', {
        operation_id: crypto.randomUUID(),
        kind: 'text',
        secret,
      });
      await loadConfig();
      return '密钥已存入系统密钥存储（Windows 凭据管理器）。';
    });

  const deleteSecret = () =>
    run(async () => {
      await call('providers.deleteSecret', { operation_id: crypto.randomUUID(), kind: 'text' });
      await loadConfig();
      return '已删除系统密钥存储中的密钥。';
    });

  const testConnection = () =>
    run(async () => {
      setTesting(true);
      setOutcome(null);
      const frame = ++pollFrame.current;
      try {
        const task = await call<TaskSnapshot>('providers.test', {
          operation_id: crypto.randomUUID(),
          kind: 'text',
        });
        let snapshot = task;
        for (let attempts = 0; attempts < 120; attempts += 1) {
          if (pollFrame.current !== frame) return;
          snapshot = await call<TaskSnapshot>('tasks.get', { task_id: task.task_id });
          if (['completed', 'failed', 'cancelled'].includes(snapshot.status)) break;
          await sleep(500);
        }
        setOutcome(snapshot.checkpoint as TestOutcome);
      } finally {
        setTesting(false);
      }
    });

  return (
    <section className="placeholder-page" aria-labelledby="page-title">
      <span className="eyebrow">SHARED SHELL · M1 TASK 05</span>
      <h1 id="page-title" tabIndex={-1}>
        设置与工具
      </h1>
      <p className="launcher-subtitle">配置 DeepSeek 文本模型；密钥只进入系统密钥存储。</p>

      {error ? (
        <p className="materials-error" role="alert">
          {error}
        </p>
      ) : null}
      {notice ? <p className="settings-notice">{notice}</p> : null}

      <div className="settings-grid" data-testid="settings-page">
        <div className="materials-card" data-testid="provider-panel">
          <h2>DeepSeek 文本模型</h2>
          {config ? (
            <p className="placeholder-note">
              当前版本 v{config.version_no} · 密钥
              {config.has_secret ? '已配置' : '未配置'}
            </p>
          ) : (
            <p className="dim">尚未加载配置。</p>
          )}
          <label className="settings-field">
            接口地址
            <input
              data-testid="provider-endpoint"
              value={endpoint}
              onChange={(event) => setEndpoint(event.target.value)}
              spellCheck={false}
            />
          </label>
          <label className="settings-field">
            模型 ID
            <input
              data-testid="provider-model"
              value={modelId}
              onChange={(event) => setModelId(event.target.value)}
              spellCheck={false}
            />
          </label>
          <div className="materials-row">
            <button
              type="button"
              className="primary-button"
              data-testid="save-provider"
              disabled={busy}
              onClick={saveProvider}
            >
              保存配置
            </button>
            <button
              type="button"
              className="text-link"
              data-testid="test-connection"
              disabled={busy || testing}
              onClick={testConnection}
            >
              测试连接（进入任务队列）
            </button>
          </div>
          {outcome ? (
            <pre className="materials-preview" data-testid="test-result">
              {JSON.stringify(outcome, null, 2)}
            </pre>
          ) : null}
        </div>

        <div className="materials-card" data-testid="secret-panel">
          <h2>API 密钥</h2>
          <p className="placeholder-note">
            密钥保存在 Windows 系统凭据管理器；数据库只保存引用，日志与导出不含密钥。
          </p>
          <label className="settings-field">
            密钥（sk-…，提交后立即从界面清除）
            <input
              type="password"
              data-testid="api-key"
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
              autoComplete="off"
            />
          </label>
          <div className="materials-row">
            <button
              type="button"
              className="primary-button"
              data-testid="save-secret"
              disabled={busy || apiKey.length === 0}
              onClick={saveSecret}
            >
              保存密钥
            </button>
            <button
              type="button"
              className="text-link"
              data-testid="delete-secret"
              disabled={busy || !config?.has_secret}
              onClick={deleteSecret}
            >
              删除密钥
            </button>
          </div>
          <p className="placeholder-note">
            测试连接不带任何资料内容；用量与延迟来自真实供应商响应。
          </p>
        </div>
      </div>
    </section>
  );
}
