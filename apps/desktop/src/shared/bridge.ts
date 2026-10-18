export const PUBLIC_RPC_METHODS = ['system.ping'] as const;

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

export interface WorkbenchBridge {
  call(method: PublicRpcMethod, params?: Record<string, unknown>): Promise<unknown>;
  getStatus(): Promise<ServiceStatus>;
  restartService(): Promise<ServiceStatus>;
  subscribe(listener: (event: BridgeEvent) => void): () => void;
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
