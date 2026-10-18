import { PUBLIC_RPC_METHODS, type PublicRpcMethod } from './bridge';

const allowedMethods = new Set<string>(PUBLIC_RPC_METHODS);

export interface SenderRequest {
  senderIsMainWindow: boolean;
  frameIsMainFrame: boolean;
  frameUrl: string | null;
}

export type SenderCheck =
  | { ok: true }
  | { ok: false; code: 'UNTRUSTED_SENDER' | 'UNTRUSTED_FRAME' | 'UNTRUSTED_ORIGIN' };

export interface CallRequest extends SenderRequest {
  method: unknown;
  params: unknown;
}

export type CallPolicy =
  | { ok: true; method: PublicRpcMethod; params: Record<string, unknown> }
  | {
      ok: false;
      code:
        | 'UNTRUSTED_SENDER'
        | 'UNTRUSTED_FRAME'
        | 'UNTRUSTED_ORIGIN'
        | 'METHOD_NOT_ALLOWED'
        | 'INVALID_PARAMS';
    };

export function originOf(target: string): string | null {
  try {
    const parsed = new URL(target);
    if (parsed.protocol === 'app:') return `app://${parsed.host}`;
    return parsed.origin === 'null' ? null : parsed.origin;
  } catch {
    return null;
  }
}

export function checkSender(
  request: SenderRequest,
  trustedOrigins: string[],
): SenderCheck {
  if (!request.senderIsMainWindow) return { ok: false, code: 'UNTRUSTED_SENDER' };
  if (!request.frameIsMainFrame) return { ok: false, code: 'UNTRUSTED_FRAME' };
  if (!request.frameUrl) return { ok: false, code: 'UNTRUSTED_ORIGIN' };

  const origin = originOf(request.frameUrl);
  if (!origin || !trustedOrigins.includes(origin)) {
    return { ok: false, code: 'UNTRUSTED_ORIGIN' };
  }

  return { ok: true };
}

export function checkCallRequest(
  request: CallRequest,
  trustedOrigins: string[],
): CallPolicy {
  const senderCheck = checkSender(request, trustedOrigins);
  if (!senderCheck.ok) return senderCheck;

  if (typeof request.method !== 'string' || !allowedMethods.has(request.method)) {
    return { ok: false, code: 'METHOD_NOT_ALLOWED' };
  }

  const params = request.params ?? {};
  if (params === null || typeof params !== 'object' || Array.isArray(params)) {
    return { ok: false, code: 'INVALID_PARAMS' };
  }

  return {
    ok: true,
    method: request.method as PublicRpcMethod,
    params: params as Record<string, unknown>,
  };
}
