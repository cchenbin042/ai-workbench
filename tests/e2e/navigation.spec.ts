import { expect, test } from '@playwright/test';

import { launchWorkbench } from './support/workbench-app';

test('@nav exposes the shared sidebar and updates the active page', async () => {
  const workbench = await launchWorkbench();
  try {
    const nav = workbench.page.getByRole('navigation', { name: '主导航' });
    for (const label of ['新建任务', '助理', '专家 · 技能 · 连接器', '定时任务', '资料库', '更多']) {
      await expect(nav.getByRole('button', { name: label, exact: true })).toBeVisible();
    }
    await expect(nav.getByRole('button', { name: '新建任务', exact: true })).toHaveAttribute(
      'aria-current',
      'page',
    );

    await nav.getByRole('button', { name: '资料库', exact: true }).click();

    await expect(workbench.page.getByRole('heading', { level: 1, name: '资料库' })).toBeVisible();
    await expect(nav.getByRole('button', { name: '资料库', exact: true })).toHaveAttribute(
      'aria-current',
      'page',
    );
    await expect(workbench.page.getByTestId('workspace-panel')).toBeVisible();
    await expect(workbench.page.getByTestId('workspace-panel')).toContainText('尚未创建空间');
  } finally {
    await workbench.close();
  }
});

test('@nav preserves the draft and scene across page switches', async () => {
  const workbench = await launchWorkbench();
  try {
    const composer = workbench.page.getByRole('textbox', { name: '任务描述' });
    const nav = workbench.page.getByRole('navigation', { name: '主导航' });

    await composer.fill('保留这段未提交草稿');
    await workbench.page.getByRole('button', { name: '开发', exact: true }).click();
    await nav.getByRole('button', { name: '资料库', exact: true }).click();
    await nav.getByRole('button', { name: '新建任务', exact: true }).click();

    await expect(composer).toHaveValue('保留这段未提交草稿');
    await expect(workbench.page.getByRole('button', { name: '开发', exact: true })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
  } finally {
    await workbench.close();
  }
});

test('@nav moves focus to the page heading and supports keyboard navigation', async () => {
  const workbench = await launchWorkbench();
  try {
    const nav = workbench.page.getByRole('navigation', { name: '主导航' });
    await nav.getByRole('button', { name: '资料库', exact: true }).click();
    await expect(workbench.page.getByRole('heading', { level: 1, name: '资料库' })).toBeFocused();

    const viewAllTasks = workbench.page.getByRole('button', { name: '查看全部任务' });
    await viewAllTasks.focus();
    await workbench.page.keyboard.press('Enter');
    await expect(workbench.page.getByRole('heading', { level: 1, name: '任务记录' })).toBeFocused();
  } finally {
    await workbench.close();
  }
});

test('@nav hubs and placeholders declare milestones without fake business data', async () => {
  const workbench = await launchWorkbench();
  try {
    const nav = workbench.page.getByRole('navigation', { name: '主导航' });
    await nav.getByRole('button', { name: '更多', exact: true }).click();

    for (const label of ['面试题库', 'AI 面试官', '面试记录', '复习清单']) {
      await expect(workbench.page.getByRole('button', { name: label, exact: true })).toBeVisible();
    }
    await workbench.page.getByRole('button', { name: '面试题库', exact: true }).click();

    await expect(workbench.page.getByRole('heading', { level: 1, name: '面试题库' })).toBeVisible();
    await expect(workbench.page.getByText('本页将在 M1 Task 06～07 接入')).toBeVisible();
    await expect(workbench.page.getByText('示例题目')).toHaveCount(0);
  } finally {
    await workbench.close();
  }
});

test('@nav keeps primary navigation reachable at 1024px without horizontal overflow', async () => {
  const workbench = await launchWorkbench();
  try {
    await workbench.page.setViewportSize({ width: 1024, height: 800 });
    const nav = workbench.page.getByRole('navigation', { name: '主导航' });
    await expect(nav.getByRole('button', { name: '资料库', exact: true })).toBeVisible();

    const fits = await workbench.page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth + 1,
    );
    expect(fits).toBe(true);
  } finally {
    await workbench.close();
  }
});
