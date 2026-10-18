import { useCallback, useEffect, useRef, useState } from 'react';

import type { BridgeEvent, ServiceStatus } from '@shared/bridge';

const startingStatus: ServiceStatus = {
  state: 'starting',
  consecutiveFailures: 0,
};

export interface ServiceConnection {
  status: ServiceStatus;
  latencyMs: number | null;
  error: string | null;
  refreshing: boolean;
  refresh: () => Promise<void>;
  reconnect: () => Promise<void>;
}

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export function useServiceStatus(): ServiceConnection {
  const [status, setStatus] = useState<ServiceStatus>(startingStatus);
  const [latencyMs, setLatencyMs] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const inFlight = useRef(false);
  const mounted = useRef(true);

  const applyStatus = useCallback((next: ServiceStatus) => {
    if (!mounted.current) return;
    setStatus(next);
    if (next.lastLatencyMs !== undefined) setLatencyMs(next.lastLatencyMs);
    setError(next.error ?? null);
  }, []);

  const run = useCallback(
    async (operation: () => Promise<ServiceStatus>) => {
      if (inFlight.current) return;
      if (typeof window === 'undefined' || !window.workbench) {
        const message = '桌面 bridge 不可用';
        if (mounted.current) {
          setError(message);
          setStatus({ state: 'disconnected', consecutiveFailures: 0, error: message });
        }
        return;
      }

      inFlight.current = true;
      if (mounted.current) setRefreshing(true);
      try {
        applyStatus(await operation());
      } catch (cause) {
        const message = messageOf(cause);
        if (mounted.current) {
          setError(message);
          setStatus((previous) => ({ ...previous, state: 'disconnected', error: message }));
        }
      } finally {
        inFlight.current = false;
        if (mounted.current) setRefreshing(false);
      }
    },
    [applyStatus],
  );

  const refresh = useCallback(
    () => run(() => window.workbench.getStatus()),
    [run],
  );

  const reconnect = useCallback(
    () => run(() => window.workbench.restartService()),
    [run],
  );

  useEffect(() => {
    mounted.current = true;
    if (typeof window === 'undefined' || !window.workbench) return;

    const unsubscribe = window.workbench.subscribe((event: BridgeEvent) => {
      if (event.type === 'service.status') applyStatus(event.status);
    });
    void refresh();
    return () => {
      mounted.current = false;
      unsubscribe();
    };
  }, [applyStatus, refresh]);

  return { status, latencyMs, error, refreshing, refresh, reconnect };
}
