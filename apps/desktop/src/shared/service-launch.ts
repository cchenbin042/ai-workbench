import path from 'node:path';

export interface PythonLaunch {
  command: string;
  args: string[];
}

export interface PythonLaunchOptions {
  repoRoot: string;
  platform: NodeJS.Platform;
  venvExists: boolean;
  env: NodeJS.ProcessEnv;
}

export function resolvePythonCommand(options: PythonLaunchOptions): PythonLaunch {
  const { repoRoot, platform, venvExists, env } = options;

  if (env.WORKBENCH_PYTHON) {
    return {
      command: env.WORKBENCH_PYTHON,
      args: [env.WORKBENCH_PYTHON_ARG ?? '-3.14', '-u', '-m', 'workbench'],
    };
  }

  if (venvExists) {
    const relative = platform === 'win32' ? ['Scripts', 'python.exe'] : ['bin', 'python'];
    return {
      command: path.join(repoRoot, '.venv', ...relative),
      args: ['-u', '-m', 'workbench'],
    };
  }

  return { command: 'py', args: ['-3.14', '-u', '-m', 'workbench'] };
}
