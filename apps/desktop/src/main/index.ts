import fs from 'node:fs';
import path from 'node:path';

import { app, BrowserWindow, protocol, session } from 'electron';

import { originOf } from '../shared/ipc-policy';
import { registerBridge } from './bridge';
import { WorkbenchService, type ServiceOptions } from './service-process';

declare const MAIN_WINDOW_VITE_DEV_SERVER_URL: string | undefined;

app.setName('ZhixuWorkbench');

const APP_SCHEME = 'app';
const APP_HOST = 'workbench';
const APP_ORIGIN = `${APP_SCHEME}://${APP_HOST}`;
const RENDERER_DIR = path.join(__dirname, '..', 'renderer', 'main_window');

const productionCsp = [
  "default-src 'self'",
  "script-src 'self'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data:",
  "font-src 'self' data:",
  "media-src 'self' blob:",
  "connect-src 'self'",
  "object-src 'none'",
  "base-uri 'none'",
  "form-action 'none'",
  "frame-src 'none'",
].join('; ');

const developmentCsp = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data:",
  "font-src 'self' data:",
  "media-src 'self' blob:",
  "connect-src 'self' ws://localhost:* http://localhost:*",
  "object-src 'none'",
  "base-uri 'none'",
  "form-action 'none'",
  "frame-src 'none'",
].join('; ');

const mimeTypes: Record<string, string> = {
  '.css': 'text/css; charset=utf-8',
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
  '.woff2': 'font/woff2',
};

let mainWindow: BrowserWindow | null = null;
let service: WorkbenchService | null = null;
let disposeBridge: (() => void) | null = null;
let quitting = false;

protocol.registerSchemesAsPrivileged([
  {
    scheme: APP_SCHEME,
    privileges: {
      standard: true,
      secure: true,
      supportFetchAPI: true,
      corsEnabled: true,
    },
  },
]);

function resolveDataDir(): string {
  return process.env.WORKBENCH_DATA_DIR ?? app.getPath('userData');
}

function trustedOrigins(): string[] {
  if (!MAIN_WINDOW_VITE_DEV_SERVER_URL) return [APP_ORIGIN];
  return [new URL(MAIN_WINDOW_VITE_DEV_SERVER_URL).origin];
}

function isTrustedUrl(target: string): boolean {
  const origin = originOf(target);
  return origin !== null && trustedOrigins().includes(origin);
}

async function serveRendererFile(request: Request): Promise<Response> {
  const url = new URL(request.url);
  if (url.host !== APP_HOST) {
    return new Response('Not Found', { status: 404 });
  }

  let requestedPath: string;
  try {
    requestedPath = decodeURIComponent(url.pathname === '/' ? '/index.html' : url.pathname);
  } catch {
    return new Response('Bad Request', { status: 400 });
  }
  const filePath = path.normalize(path.join(RENDERER_DIR, requestedPath));
  const relative = path.relative(RENDERER_DIR, filePath);
  if (relative.startsWith('..') || path.isAbsolute(relative)) {
    return new Response('Forbidden', { status: 403 });
  }

  try {
    const body = await fs.promises.readFile(filePath);
    return new Response(body, {
      headers: {
        'Content-Type': mimeTypes[path.extname(filePath).toLowerCase()] ?? 'application/octet-stream',
        'Content-Security-Policy': productionCsp,
        'X-Content-Type-Options': 'nosniff',
      },
    });
  } catch {
    return new Response('Not Found', { status: 404 });
  }
}

function applySessionSecurity(): void {
  session.defaultSession.setPermissionRequestHandler((_contents, _permission, callback) => {
    callback(false);
  });
  session.defaultSession.setPermissionCheckHandler(() => false);

  if (MAIN_WINDOW_VITE_DEV_SERVER_URL) {
    session.defaultSession.webRequest.onHeadersReceived((details, callback) => {
      if (!isTrustedUrl(details.url)) {
        callback({ responseHeaders: details.responseHeaders });
        return;
      }
      callback({
        responseHeaders: {
          ...details.responseHeaders,
          'Content-Security-Policy': [developmentCsp],
          'X-Content-Type-Options': ['nosniff'],
        },
      });
    });
  }

  app.on('web-contents-created', (_event, contents) => {
    contents.setWindowOpenHandler(() => ({ action: 'deny' }));
    contents.on('will-attach-webview', (event) => event.preventDefault());
    contents.on('will-navigate', (event, url) => {
      if (!isTrustedUrl(url)) event.preventDefault();
    });
  });
}

function createWindow(): BrowserWindow {
  const window = new BrowserWindow({
    width: 1536,
    height: 1000,
    minWidth: 1024,
    minHeight: 700,
    backgroundColor: '#151515',
    show: false,
    title: '知序 · 个人 AI 工作台',
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true,
    },
  });

  window.once('ready-to-show', () => window.show());
  window.on('closed', () => {
    if (mainWindow === window) mainWindow = null;
  });

  if (MAIN_WINDOW_VITE_DEV_SERVER_URL) {
    void window.loadURL(MAIN_WINDOW_VITE_DEV_SERVER_URL);
  } else {
    void window.loadURL(`${APP_ORIGIN}/index.html`);
  }

  return window;
}

async function startService(window: BrowserWindow): Promise<void> {
  const options: ServiceOptions = { dataDir: resolveDataDir() };
  service = new WorkbenchService(options);
  disposeBridge = registerBridge({
    window,
    service,
    trustedOrigins: trustedOrigins(),
  });

  try {
    await service.start();
  } catch (error) {
    console.error('[workbench] 本地服务启动失败：', error);
  }
}

async function shutdown(): Promise<void> {
  disposeBridge?.();
  disposeBridge = null;
  await service?.stop();
  service = null;
}

const gotSingleInstanceLock = app.requestSingleInstanceLock();
if (!gotSingleInstanceLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (!mainWindow) return;
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.focus();
  });

  app.whenReady().then(async () => {
    if (!MAIN_WINDOW_VITE_DEV_SERVER_URL) {
      protocol.handle(APP_SCHEME, (request) => serveRendererFile(request));
    }
    applySessionSecurity();

    mainWindow = createWindow();
    void startService(mainWindow);

    app.on('activate', () => {
      if (mainWindow) {
        mainWindow.focus();
        return;
      }
      mainWindow = createWindow();
      if (!service) {
        void startService(mainWindow);
        return;
      }
      disposeBridge?.();
      disposeBridge = registerBridge({
        window: mainWindow,
        service,
        trustedOrigins: trustedOrigins(),
      });
    });
  });

  app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') app.quit();
  });

  app.on('before-quit', (event) => {
    if (quitting) return;
    event.preventDefault();
    quitting = true;
    void shutdown().finally(() => app.quit());
  });
}
