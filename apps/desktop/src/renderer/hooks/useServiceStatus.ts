import { useCallback, useEffect, useRef, useState } from 'react';

import type {
  BridgeEvent,
  InitializeResult,
  PingResult,
  ServiceStatus,
} from '@shared/bridge';

const startingStatus: ServiceStatus = {
  state: 'starting',
  consecutiveFailures: 0,
};

export interface ServiceConnection {
  status: ServiceStatus;
  initialize: InitializeResult | null;
  ping: PingResult | null;
  latencyMs: number | null;
  error: string | null;
  refreshing: boolean;
  refresh: () => Promise<void>;
}

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export function useServiceStatus(): ServiceConnection {
  const [status, setStatus] = useState<ServiceStatus>(startingStatus);
  const [initialize, setInitialize] = useState<InitializeResult | null>(null);
  const [ping, setPing] = useState<PingResult | null>(null);
  const [latencyMs, setLatencyMs] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const inFlight = useRef(false);

  const refresh = useCallback(async () => {
    if (inFlight.current) return;

    if (typeof window === 'undefined' || !window.workbench) {
      const message = '桌面 bridge 不可用';
      setError(message);
      setStatus({ state: 'disconnected', consecutiveFailures: 0, error: message });
      return;
    }

    inFlight.current = true;
    setRefreshing(true);
    setError(null);
    const startedAt = performance.now();

    try {
      const initializeResult = (await window.workbench.call(
        'system.initialize',
        {},
      )) as InitializeResult;
      const pingResult = (await window.workbench.call('system.ping', {})) as PingResult;
      const elapsed = Math.round(performance.now() - startedAt);

      setInitialize(initializeResult);
      setPing(pingResult);
      setLatencyMs(elapsed);
      setStatus({
        state: 'connected',
        protocolVersion: initializeResult.protocol_version,
        schemaVersion: initializeResult.schema_version,
        serviceInstanceId: initializeResult.service_instance_id,
        capabilities: initializeResult.capabilities,
        lastLatencyMs: elapsed,
        consecutiveFailures: 0,
      });
    } catch (cause) {
      const message = messageOf(cause);
      setError(message);
      setStatus((previous) => ({
        ...previous,
        state: 'disconnected',
        error: message,
      }));
    } finally {
      inFlight.current = false;
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    if (typeof window === 'undefined' || !window.workbench) return;

    const unsubscribe = window.workbench.subscribe((event: BridgeEvent) => {
      if (event.type !== 'service.status') return;
      setStatus(event.status);
      if (event.status.lastLatencyMs !== undefined) {
        setLatencyMs(event.status.lastLatencyMs);
      }
      if (event.status.error) setError(event.status.error);
    });

    void refresh();
    return unsubscribe;
  }, [refresh]);

  return { status, initialize, ping, latencyMs, error, refreshing, refresh };
}
