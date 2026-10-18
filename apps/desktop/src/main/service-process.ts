import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process';
import { EventEmitter } from 'node:events';
import fs from 'node:fs';
import path from 'node:path';
import readline from 'node:readline';

import { app } from 'electron';

import type {
  InitializeResult,
  PingResult,
  ServiceStatus,
} from '../shared/bridge';
import { FrameTooLargeError, JsonLineReader, MAX_FRAME_BYTES } from '../shared/json-line-reader';
import { resolvePythonCommand } from '../shared/service-launch';

const HANDSHAKE_TIMEOUT_MS = 15_000;
const REQUEST_TIMEOUT_MS = 10_000;
const HEARTBEAT_TIMEOUT_MS = 4_000;
const HEARTBEAT_INTERVAL_MS = 5_000;
const RECOVERY_PROBE_INTERVAL_MS = 30_000;
const MAX_FAILED_HEARTBEATS = 3;

interface PendingRequest {
  resolve: (value: unknown) => void;
  reject: (reason: Error) => void;
  timer: NodeJS.Timeout;
}

interface LaunchCommand {
  command: string;
  args: string[];
  cwd: string;
  env: NodeJS.ProcessEnv;
}

export interface ServiceOptions {
  dataDir: string;
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export class WorkbenchService extends EventEmitter {
  private child: ChildProcessWithoutNullStreams | null = null;
  private pending = new Map<string, PendingRequest>();
  private nextRequestId = 0;
  private heartbeatTimer: NodeJS.Timeout | null = null;
  private recoveryTimer: NodeJS.Timeout | null = null;
  private exitHandled = false;
  private stopping = false;
  private status: ServiceStatus = {
    state: 'stopped',
    consecutiveFailures: 0,
  };

  constructor(private readonly options: ServiceOptions) {
    super();
  }

  getStatus(): ServiceStatus {
    return { ...this.status };
  }

  async start(): Promise<InitializeResult> {
    if (this.child) throw new Error('SERVICE_ALREADY_RUNNING');
    this.stopping = false;
    this.exitHandled = false;
    this.stopHeartbeat();
    this.clearRecoveryTimer();
    this.updateStatus({ state: 'starting', error: undefined, consecutiveFailures: 0 });

    let launch: LaunchCommand;
    try {
      launch = resolveLaunchCommand(this.options.dataDir);
    } catch (error) {
      this.failStart(error);
      throw error;
    }

    const child = spawn(launch.command, launch.args, {
      cwd: launch.cwd,
      env: launch.env,
      shell: false,
      windowsHide: true,
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    this.child = child;

    child.stderr.setEncoding('utf8');
    const stdoutReader = new JsonLineReader();
    child.stdout.on('data', (chunk: Buffer) => {
      try {
        for (const line of stdoutReader.feed(chunk)) this.handleLine(line);
      } catch (error) {
        this.handleProtocolFailure(error);
      }
    });
    readline.createInterface({ input: child.stderr }).on('line', (line) => {
      console.error('[workbench-service]', line);
    });

    child.once('error', (error) => this.handleExit(errorMessage(error)));
    child.once('exit', (code, signal) => {
      this.handleExit(`本地服务已退出（code=${String(code)}, signal=${String(signal)}）`);
    });

    try {
      const result = await this.request<InitializeResult>(
        'system.initialize',
        {},
        HANDSHAKE_TIMEOUT_MS,
      );
      this.updateStatus({
        state: 'connected',
        protocolVersion: result.protocol_version,
        schemaVersion: result.schema_version,
        serviceInstanceId: result.service_instance_id,
        capabilities: result.capabilities,
        consecutiveFailures: 0,
        error: undefined,
      });
      this.startHeartbeat();
      return result;
    } catch (error) {
      this.failStart(error);
      throw error;
    }
  }

  async restart(): Promise<ServiceStatus> {
    try {
      await this.stop();
      await this.start();
    } catch {
      // start() records the failure in status; the renderer reads the snapshot.
    }
    return this.getStatus();
  }

  async request<T>(
    method: string,
    params: Record<string, unknown> = {},
    timeoutMs = REQUEST_TIMEOUT_MS,
  ): Promise<T> {
    const child = this.child;
    if (!child || child.killed || child.stdin.destroyed) {
      throw new Error('SERVICE_DISCONNECTED');
    }

    const id = `rpc-${++this.nextRequestId}`;
    const frame = `${JSON.stringify({ jsonrpc: '2.0', id, method, params })}\n`;
    if (Buffer.byteLength(frame, 'utf8') > MAX_FRAME_BYTES) {
      throw new Error('FRAME_TOO_LARGE');
    }

    return new Promise<T>((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`RPC_TIMEOUT: ${method}`));
      }, timeoutMs);
      this.pending.set(id, {
        resolve: resolve as (value: unknown) => void,
        reject,
        timer,
      });
      child.stdin.write(frame, 'utf8', (error) => {
        if (!error) return;
        clearTimeout(timer);
        this.pending.delete(id);
        reject(new Error(`SERVICE_WRITE_FAILED: ${errorMessage(error)}`));
      });
    });
  }

  async stop(): Promise<void> {
    this.stopping = true;
    this.stopHeartbeat();
    this.clearRecoveryTimer();
    const child = this.child;
    if (!child) {
      this.updateStatus({ state: 'stopped' });
      return;
    }

    try {
      await this.request('system.shutdown', {}, 5_000);
    } catch {
      // The service may exit before flushing the shutdown response.
    }

    if (!(await waitForExit(child, 5_000))) {
      await killProcessTree(child);
    }
    this.child = null;
    this.exitHandled = true;
    this.rejectPending(new Error('SERVICE_STOPPED'));
    this.updateStatus({ state: 'stopped' });
  }

  private startHeartbeat(): void {
    this.stopHeartbeat();
    this.heartbeatTimer = setInterval(() => {
      void this.heartbeatTick();
    }, HEARTBEAT_INTERVAL_MS);
  }

  private stopHeartbeat(): void {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  private async heartbeatTick(): Promise<void> {
    if (!this.child || this.stopping) return;
    const startedAt = Date.now();
    try {
      const result = await this.request<PingResult>('system.ping', {}, HEARTBEAT_TIMEOUT_MS);
      this.updateStatus({
        state: 'connected',
        lastLatencyMs: Date.now() - startedAt,
        serviceInstanceId: result.service_instance_id ?? this.status.serviceInstanceId,
        consecutiveFailures: 0,
        error: undefined,
      });
    } catch (error) {
      const consecutiveFailures = this.status.consecutiveFailures + 1;
      this.updateStatus({
        consecutiveFailures,
        error: errorMessage(error),
        state: consecutiveFailures >= MAX_FAILED_HEARTBEATS ? 'disconnected' : this.status.state,
      });
      if (consecutiveFailures >= MAX_FAILED_HEARTBEATS) {
        this.stopHeartbeat();
        this.scheduleRecoveryProbe();
      }
    }
  }

  private scheduleRecoveryProbe(): void {
    if (this.recoveryTimer || !this.child || this.stopping) return;
    this.recoveryTimer = setTimeout(() => {
      this.recoveryTimer = null;
      void this.recoveryTick();
    }, RECOVERY_PROBE_INTERVAL_MS);
  }

  private async recoveryTick(): Promise<void> {
    if (!this.child || this.stopping) return;
    const startedAt = Date.now();
    try {
      await this.request<PingResult>('system.ping', {}, HEARTBEAT_TIMEOUT_MS);
      this.updateStatus({
        state: 'connected',
        lastLatencyMs: Date.now() - startedAt,
        consecutiveFailures: 0,
        error: undefined,
      });
      this.startHeartbeat();
    } catch {
      this.scheduleRecoveryProbe();
    }
  }

  private clearRecoveryTimer(): void {
    if (this.recoveryTimer) {
      clearTimeout(this.recoveryTimer);
      this.recoveryTimer = null;
    }
  }

  private handleProtocolFailure(error: unknown): void {
    const code = error instanceof FrameTooLargeError ? 'FRAME_TOO_LARGE' : 'PROTOCOL_ERROR';
    console.error('[workbench-service]', code);
    this.stopHeartbeat();
    this.clearRecoveryTimer();
    const child = this.child;
    if (child) void killProcessTree(child);
    this.finalizeExit(code);
  }

  private handleLine(line: string): void {
    const trimmed = line.trim();
    if (!trimmed) return;

    let message: Record<string, unknown>;
    try {
      const parsed: unknown = JSON.parse(trimmed);
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
        throw new Error('frame is not an object');
      }
      message = parsed as Record<string, unknown>;
    } catch {
      console.error('[workbench-service] 收到无法解析的协议帧');
      return;
    }

    const pendingId = typeof message.id === 'string' ? message.id : null;
    if (pendingId) {
      const pending = this.pending.get(pendingId);
      if (!pending) return;
      this.pending.delete(pendingId);
      clearTimeout(pending.timer);
      if (message.error) {
        pending.reject(new Error(readRpcError(message.error)));
      } else {
        pending.resolve(message.result);
      }
      return;
    }

    if (typeof message.method === 'string') {
      this.emit('rpc-event', message);
    }
  }

  private handleExit(reason: string): void {
    if (this.stopping) return;
    this.finalizeExit(reason);
  }

  private finalizeExit(reason: string): void {
    if (this.exitHandled) return;
    this.exitHandled = true;
    this.stopHeartbeat();
    this.clearRecoveryTimer();
    this.child = null;
    this.rejectPending(new Error('SERVICE_DISCONNECTED'));
    this.updateStatus({
      state: 'disconnected',
      consecutiveFailures: this.status.consecutiveFailures + 1,
      error: reason,
    });
  }

  private failStart(error: unknown): void {
    this.stopHeartbeat();
    this.clearRecoveryTimer();
    const child = this.child;
    if (child) void killProcessTree(child);
    this.child = null;
    this.exitHandled = true;
    this.rejectPending(new Error('SERVICE_START_FAILED'));
    this.updateStatus({
      state: 'disconnected',
      consecutiveFailures: this.status.consecutiveFailures + 1,
      error: errorMessage(error),
    });
  }

  private rejectPending(error: Error): void {
    for (const [id, pending] of this.pending) {
      clearTimeout(pending.timer);
      pending.reject(error);
      this.pending.delete(id);
    }
  }

  private updateStatus(patch: Partial<ServiceStatus>): void {
    this.status = { ...this.status, ...patch };
    this.emit('status', this.getStatus());
  }
}

function readRpcError(error: unknown): string {
  if (!error || typeof error !== 'object') return 'RPC_ERROR';
  const data = (error as Record<string, unknown>).data;
  if (!data || typeof data !== 'object') return 'RPC_ERROR';

  const record = data as Record<string, unknown>;
  if (typeof record.user_message === 'string') return record.user_message;
  if (typeof record.code === 'string') return record.code;
  return 'RPC_ERROR';
}

function resolveLaunchCommand(dataDir: string): LaunchCommand {
  const usePython = process.env.WORKBENCH_SERVICE_MODE === 'python' || !app.isPackaged;
  if (usePython) {
    const repoRoot =
      process.env.WORKBENCH_REPO_ROOT ?? path.resolve(app.getAppPath(), '..', '..');
    const venvRelative = process.platform === 'win32' ? ['Scripts', 'python.exe'] : ['bin', 'python'];
    const venvExists = fs.existsSync(path.join(repoRoot, '.venv', ...venvRelative));
    const python = resolvePythonCommand({
      repoRoot,
      platform: process.platform,
      venvExists,
      env: process.env,
    });
    return {
      command: python.command,
      args: [...python.args, '--data-dir', dataDir],
      cwd: path.join(repoRoot, 'services', 'workbench'),
      env: {
        ...process.env,
        PYTHONPATH: path.join(repoRoot, 'services', 'workbench', 'src'),
        PYTHONUTF8: '1',
        PYTHONIOENCODING: 'utf-8',
      },
    };
  }

  const executable =
    process.env.WORKBENCH_SERVICE_EXE ??
    path.join(process.resourcesPath, 'workbench-service', 'workbench-service.exe');
  if (!fs.existsSync(executable)) {
    throw new Error(`未找到本地服务可执行文件：${executable}`);
  }
  return {
    command: executable,
    args: ['--data-dir', dataDir],
    cwd: path.dirname(executable),
    env: { ...process.env },
  };
}

function waitForExit(child: ChildProcessWithoutNullStreams, timeoutMs: number): Promise<boolean> {
  if (child.exitCode !== null || child.signalCode !== null) return Promise.resolve(true);
  return new Promise((resolve) => {
    const timer = setTimeout(() => resolve(false), timeoutMs);
    child.once('exit', () => {
      clearTimeout(timer);
      resolve(true);
    });
  });
}

function killProcessTree(child: ChildProcessWithoutNullStreams): Promise<void> {
  return new Promise((resolve) => {
    if (!child.pid) {
      resolve();
      return;
    }
    if (process.platform !== 'win32') {
      try {
        child.kill('SIGKILL');
      } catch {
        // Process already exited.
      }
      resolve();
      return;
    }

    const killer = spawn('taskkill', ['/PID', String(child.pid), '/T', '/F'], {
      shell: false,
      windowsHide: true,
      stdio: 'ignore',
    });
    const timer = setTimeout(resolve, 3_000);
    killer.once('exit', () => {
      clearTimeout(timer);
      resolve();
    });
    killer.once('error', () => {
      clearTimeout(timer);
      try {
        child.kill();
      } catch {
        // Process already exited.
      }
      resolve();
    });
  });
}
