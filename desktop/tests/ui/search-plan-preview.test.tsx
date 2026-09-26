// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { SearchPlanPreview } from '../../src/renderer/pages/tasks/SearchPlanPreview';
import type { AppContextValue } from '../../src/renderer/app/context';
import { newTaskDraft } from '../../src/renderer/domain/models';

let context: AppContextValue;
const preview = vi.fn();
vi.mock('../../src/renderer/app/context', () => ({ useApp: () => context }));
const plan = {
  version: 'radar-search-directions-v1',
  strategies: [
    { id: 'quick', name: '快速搜索', purpose: '直接需求', queries: ['工业水泵 询价'] },
    { id: 'condition', name: '条件核验', purpose: '按当前条件核验', queries: ['工业水泵 询价 -招聘'] },
    { id: 'broad', name: '扩展搜索', purpose: '补查相关表达', queries: ['工业水泵'] },
  ],
  queries: ['工业水泵 询价', '工业水泵 询价 -招聘', '工业水泵'],
};
function draft() {
  return { ...newTaskDraft(), profileId: 'profile-1', profileVersion: 1,
    terms: [{ id: 't1', value: '工业水泵', origin: 'manual' as const, edited: true }] };
}
beforeEach(() => {
  preview.mockReset().mockResolvedValue(plan);
  context = { service: { researchPlan: { preview } },
    session: { authenticated: true, userId: 'user-1', accountScope: { id: 'tenant-1', version: 1 } },
  } as unknown as AppContextValue;
});
afterEach(cleanup);
it('keeps the plan collapsed, loads explicitly and exposes directions without starting a task', async () => {
  const view = render(<SearchPlanPreview draft={draft()} />);
  expect(preview).not.toHaveBeenCalled();
  const details = view.container.querySelector('details')!;
  details.open = true;
  fireEvent(details, new Event('toggle'));
  expect(await screen.findByText('快速搜索')).toBeVisible();
  expect(screen.getByText('查看全部 3 条检索式')).toBeVisible();
  expect(preview).toHaveBeenCalledTimes(1);
  expect(preview.mock.calls[0][0]).toMatchObject({ querySeeds: ['工业水泵'], region: '' });
  expect(screen.queryByRole('button', { name: /开始|执行/ })).toBeNull();
});
it('removes old plans immediately on condition changes and ignores a late response', async () => {
  let resolve!: (value: unknown) => void;
  preview.mockImplementationOnce(() => new Promise(done => { resolve = done; }));
  const original = draft();
  const view = render(<SearchPlanPreview draft={original} />);
  const details = view.container.querySelector('details')!;
  details.open = true;
  fireEvent(details, new Event('toggle'));
  expect(preview).toHaveBeenCalledTimes(1);
  view.rerender(<SearchPlanPreview draft={{ ...original, terms: [] }} />);
  expect(screen.getByText('先完善上方搜索条件，再查看计划')).toBeVisible();
  await act(async () => { resolve(plan); });
  expect(screen.queryByText('快速搜索')).toBeNull();
});
it('does not send business conditions while signed out', () => {
  context = { ...context, session: { authenticated: false, userId: '' } };
  const view = render(<SearchPlanPreview draft={draft()} />);
  const details = view.container.querySelector('details')!;
  details.open = true;
  fireEvent(details, new Event('toggle'));
  expect(screen.getByText('登录后查看搜索计划')).toBeVisible();
  expect(preview).not.toHaveBeenCalled();
});
it('does not replace an invalid industry strategy with a different plan', () => {
  const value = draft();
  value.industryStrategy = { profileId: 'old-profile', configuration: {
    version: 'industry-task-strategy-v1', sourceTypes: ['PROCUREMENT'], intentSignals: ['询价'], counterSignals: [],
  } };
  const view = render(<SearchPlanPreview draft={value} />);
  const details = view.container.querySelector('details')!;
  details.open = true;
  fireEvent(details, new Event('toggle'));
  expect(screen.getByText(/行业策略沿用旧画像/)).toBeVisible();
  expect(preview).not.toHaveBeenCalled();
});
