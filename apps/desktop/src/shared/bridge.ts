export const PUBLIC_RPC_METHODS = [
  'system.ping',
  'tasks.get',
  'workspaces.create',
  'workspaces.list',
  'workspaces.listLinks',
  'workspaces.linkDirectory',
  'workspaces.unlinkDirectory',
  'materials.listDirectory',
  'materials.importFiles',
  'materials.importText',
  'materials.list',
  'materials.get',
  'materials.checkFreshness',
  'materials.previewFile',
  'providers.get',
  'providers.list',
  'providers.update',
  'providers.setSecret',
  'providers.deleteSecret',
  'providers.test',
] as const;

export type PublicRpcMethod = (typeof PUBLIC_RPC_METHODS)[number];

export interface InitializeResult {
  protocol_version: number;
  schema_version: number;
  service_instance_id: string;
  capabilities: string[];
  started_at?: string;
}

export interface PingResult {
  ok: boolean;
  service_instance_id?: string;
  timestamp?: string;
}

export type ServiceState = 'starting' | 'connected' | 'disconnected' | 'stopped';

export interface ServiceStatus {
  state: ServiceState;
  protocolVersion?: number;
  schemaVersion?: number;
  serviceInstanceId?: string;
  capabilities?: string[];
  lastLatencyMs?: number;
  consecutiveFailures: number;
  error?: string;
}

export interface ServiceStatusEvent {
  type: 'service.status';
  status: ServiceStatus;
}

export interface RpcEvent {
  type: 'rpc.event';
  payload: unknown;
}

export type BridgeEvent = ServiceStatusEvent | RpcEvent;

export interface SelectionGrant {
  grantId: string;
  kind: 'directory' | 'files';
  expiresAt: string;
  root: string | null;
  files: string[];
}

export interface WorkbenchBridge {
  call(method: PublicRpcMethod, params?: Record<string, unknown>): Promise<unknown>;
  getStatus(): Promise<ServiceStatus>;
  restartService(): Promise<ServiceStatus>;
  subscribe(listener: (event: BridgeEvent) => void): () => void;
  chooseDirectory(): Promise<SelectionGrant | null>;
  chooseFiles(): Promise<SelectionGrant | null>;
  runtime: {
    platform: string;
    electron: string;
    chrome: string;
    node: string;
  };
}

declare global {
  interface Window {
    workbench: WorkbenchBridge;
  }
}
