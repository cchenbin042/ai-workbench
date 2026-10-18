import type { ServiceConnection } from '../hooks/useServiceStatus';
import { Icon } from './Icon';

const stateLabels = {
  starting: '连接中',
  connected: '已连接',
  disconnected: '未连接',
  stopped: '已停止',
} as const;

function mediaEncoding(): string {
  if (typeof MediaRecorder === 'undefined') return 'MediaRecorder 不可用';
  return MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
    ? 'audio/webm;codecs=opus 可用'
    : '目标语音编码不可用';
}

interface StatusPanelProps {
  connection: ServiceConnection;
}

export function StatusPanel({ connection }: StatusPanelProps) {
  const { status, initialize, latencyMs, error, refreshing, refresh } = connection;
  const runtime = typeof window !== 'undefined' ? window.workbench?.runtime : undefined;
  const instance = status.serviceInstanceId ?? initialize?.service_instance_id ?? '—';
  const capabilities = status.capabilities ?? initialize?.capabilities ?? [];

  return (
    <aside className="status-panel" aria-label="本地服务状态">
      <div className="status-heading">
        <div>
          <span className="eyebrow">LOCAL SERVICE</span>
          <h2>本地服务</h2>
        </div>
        <span className={`status-badge ${status.state}`} data-testid="service-status">
          <span className="status-dot" />
          {stateLabels[status.state]}
        </span>
      </div>

      <dl className="status-list">
        <div>
          <dt>协议版本</dt>
          <dd data-testid="service-protocol">
            {status.protocolVersion ?? initialize?.protocol_version ?? '—'}
          </dd>
        </div>
        <div>
          <dt>数据版本</dt>
          <dd data-testid="service-schema">
            {status.schemaVersion ?? initialize?.schema_version ?? '—'}
          </dd>
        </div>
        <div>
          <dt>服务实例</dt>
          <dd className="mono" data-testid="service-instance" title={instance}>
            {instance === '—' ? instance : `${instance.slice(0, 8)}…`}
          </dd>
        </div>
        <div>
          <dt>最近心跳</dt>
          <dd data-testid="service-latency">
            {latencyMs === null ? '—' : `${latencyMs} ms`}
          </dd>
        </div>
        <div>
          <dt>语音编码</dt>
          <dd data-testid="media-capability">{mediaEncoding()}</dd>
        </div>
      </dl>

      {error ? (
        <div className="status-error" role="alert">
          <Icon name="alert" size={16} />
          <span>{error}</span>
        </div>
      ) : null}

      <div className="status-section">
        <span className="section-title">可用能力</span>
        <ul className="capability-list">
          {capabilities.length === 0 ? <li>尚未取得</li> : null}
          {capabilities.map((capability) => (
            <li key={capability}>{capability}</li>
          ))}
        </ul>
      </div>

      <button
        type="button"
        className="refresh-button"
        onClick={() => void refresh()}
        disabled={refreshing}
        data-testid="refresh-connection"
      >
        <Icon name="refresh" size={16} />
        {refreshing ? '正在重试…' : '重新连接'}
      </button>

      <div className="status-section runtime">
        <span className="section-title">运行环境</span>
        <dl className="status-list">
          <div>
            <dt>Electron</dt>
            <dd>{runtime?.electron || '—'}</dd>
          </div>
          <div>
            <dt>Chromium</dt>
            <dd>{runtime?.chrome || '—'}</dd>
          </div>
          <div>
            <dt>平台</dt>
            <dd>{runtime?.platform || '—'}</dd>
          </div>
        </dl>
      </div>

      <p className="status-note">
        IPC 仅开放 system.initialize / system.ping；renderer 不暴露 Node API。
        本地服务校验不是操作系统沙箱。
      </p>
    </aside>
  );
}
