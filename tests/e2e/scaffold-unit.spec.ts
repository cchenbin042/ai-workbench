import { expect, test } from '@playwright/test';

import { checkCallRequest, checkSender } from '../../apps/desktop/src/shared/ipc-policy';
import { FrameTooLargeError, JsonLineReader } from '../../apps/desktop/src/shared/json-line-reader';
import { resolvePythonCommand } from '../../apps/desktop/src/shared/service-launch';

const trustedOrigins = ['app://workbench'];
const sender = {
  senderIsMainWindow: true,
  frameIsMainFrame: true,
  frameUrl: 'app://workbench/index.html',
};

test('@unit validates IPC sender, origin, method and params', () => {
  expect(checkSender(sender, trustedOrigins)).toEqual({ ok: true });
  expect(
    checkSender({ ...sender, senderIsMainWindow: false }, trustedOrigins),
  ).toEqual({ ok: false, code: 'UNTRUSTED_SENDER' });
  expect(
    checkSender({ ...sender, frameIsMainFrame: false }, trustedOrigins),
  ).toEqual({ ok: false, code: 'UNTRUSTED_FRAME' });
  expect(
    checkSender({ ...sender, frameUrl: 'https://evil.example/index.html' }, trustedOrigins),
  ).toEqual({ ok: false, code: 'UNTRUSTED_ORIGIN' });
  expect(checkSender({ ...sender, frameUrl: null }, trustedOrigins)).toEqual({
    ok: false,
    code: 'UNTRUSTED_ORIGIN',
  });

  expect(
    checkCallRequest({ ...sender, method: 'system.ping', params: {} }, trustedOrigins),
  ).toEqual({ ok: true, method: 'system.ping', params: {} });
  expect(
    checkCallRequest({ ...sender, method: 'system.shutdown', params: {} }, trustedOrigins),
  ).toEqual({ ok: false, code: 'METHOD_NOT_ALLOWED' });
  expect(
    checkCallRequest({ ...sender, method: 'system.initialize', params: {} }, trustedOrigins),
  ).toEqual({ ok: false, code: 'METHOD_NOT_ALLOWED' });
  expect(
    checkCallRequest({ ...sender, method: 'system.ping', params: [] }, trustedOrigins),
  ).toEqual({ ok: false, code: 'INVALID_PARAMS' });
});

test('@unit enforces inbound frame limits and preserves split UTF-8', () => {
  const reader = new JsonLineReader(64);
  const wire = Buffer.from('{"note":"中文"}\n{"id":2}\n', 'utf8');
  const split = wire.indexOf(Buffer.from('中')[0]) + 1;

  expect(reader.feed(wire.subarray(0, split))).toEqual([]);
  expect(reader.feed(wire.subarray(split))).toEqual(['{"note":"中文"}', '{"id":2}']);

  const exact = new JsonLineReader(4);
  expect(exact.feed(Buffer.from('abcd\n'))).toEqual(['abcd']);

  const oversize = new JsonLineReader(4);
  expect(() => oversize.feed(Buffer.from('abcde\n'))).toThrow(FrameTooLargeError);
  const unbounded = new JsonLineReader(4);
  expect(() => unbounded.feed(Buffer.from('abcde'))).toThrow(FrameTooLargeError);
});

test('@unit prefers the project virtualenv when launching the service', () => {
  const venv = resolvePythonCommand({
    repoRoot: 'C:/repo',
    platform: 'win32',
    venvExists: true,
    env: {},
  });
  expect(venv.command).toContain('.venv');
  expect(venv.command.endsWith('python.exe')).toBe(true);
  expect(venv.args).toEqual(['-u', '-m', 'workbench']);

  expect(
    resolvePythonCommand({
      repoRoot: 'C:/repo',
      platform: 'win32',
      venvExists: false,
      env: {},
    }),
  ).toEqual({ command: 'py', args: ['-3.14', '-u', '-m', 'workbench'] });

  expect(
    resolvePythonCommand({
      repoRoot: 'C:/repo',
      platform: 'win32',
      venvExists: true,
      env: { WORKBENCH_PYTHON: 'python3', WORKBENCH_PYTHON_ARG: '-3.13' },
    }),
  ).toEqual({ command: 'python3', args: ['-3.13', '-u', '-m', 'workbench'] });
});
