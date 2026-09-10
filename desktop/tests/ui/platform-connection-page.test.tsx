// @vitest-environment jsdom
import {afterEach, beforeEach, expect, it, vi} from 'vitest';
import {act, cleanup, fireEvent, render, screen} from '@testing-library/react';
import type {AppContextValue} from '../../src/renderer/app/context';
import {ConnectionsPage} from '../../src/renderer/pages/Connections';
import {parseRoute} from '../../src/renderer/domain/routes';
import type {YikeService} from '../../src/renderer/services/contracts';
import {ServiceError} from '../../src/renderer/services/contracts';
let context: AppContextValue;
vi.mock('../../src/renderer/app/context', () => ({useApp: () => context}));
beforeEach(() => {
  localStorage.clear(); sessionStorage.clear();
  context = {session: {authenticated: true, userId: 'user', accountScope: {id: 'space', version: 1}},
    route: parseRoute('#/connections?connect=xhs'), navigate: vi.fn(), notify: vi.fn(), refreshSession: vi.fn(),
    service: {connections: vi.fn().mockResolvedValue([]), connect: vi.fn().mockResolvedValue(undefined),
      checkConnection: vi.fn().mockResolvedValue({platform: 'xhs', status: 'UNVERIFIED', capabilities: []}),
      cancelConnection: vi.fn().mockResolvedValue(undefined)} as unknown as YikeService};
});
afterEach(cleanup);
it('passes a pending-open abort signal and cancels the native flow on modal close', async () => {
  const view = render(<ConnectionsPage />); await act(async () => {});
  fireEvent.click(screen.getByRole('button', {name: '打开登录窗口'}));
  await screen.findByText('等待登录');
  expect(context.service.connect).toHaveBeenCalledWith('xhs', expect.any(AbortSignal));
  fireEvent.click(screen.getByRole('button', {name: '取消'}));
  expect(context.service.cancelConnection).toHaveBeenCalledWith('xhs');
  view.unmount();
});
it('checking the opened flow does not call explicit native cancellation', async () => {
  render(<ConnectionsPage />); await act(async () => {});
  fireEvent.click(screen.getByRole('button', {name: '打开登录窗口'}));
  await screen.findByText('等待登录');
  vi.mocked(context.service.cancelConnection!).mockClear();
  fireEvent.click(screen.getByRole('button', {name: '我已完成登录，检查连接'}));
  await act(async () => {});
  expect(context.service.checkConnection).toHaveBeenCalledWith('xhs');
  expect(context.service.cancelConnection).not.toHaveBeenCalled();
});
it('workspace generation changes cancel the original flow and discard late OPEN', async () => {
  let finish!: () => void;
  vi.mocked(context.service.connect).mockImplementation(() => new Promise(resolve => {finish = resolve;}));
  const view = render(<ConnectionsPage />); await act(async () => {});
  fireEvent.click(screen.getByRole('button', {name: '打开登录窗口'})); await act(async () => {});
  context = {...context, session: {...context.session, accountScope: {id: 'space', version: 2}}};
  view.rerender(<ConnectionsPage />);
  expect(context.service.cancelConnection).toHaveBeenCalledWith('xhs');
  await act(async () => finish());
  expect(screen.queryByText('等待登录')).toBeNull();
});
it('unmount cancels the opened flow', async () => {
  const view = render(<ConnectionsPage />); await act(async () => {});
  fireEvent.click(screen.getByRole('button', {name: '打开登录窗口'})); await screen.findByText('等待登录');
  vi.mocked(context.service.cancelConnection!).mockClear();
  view.unmount();
  expect(context.service.cancelConnection).toHaveBeenCalledWith('xhs');
});
it('unknown OPEN outcome keeps explicit original-flow CHECK available without claiming a window or connection', async () => {
  vi.mocked(context.service.connect).mockRejectedValue(new ServiceError('UNKNOWN', '连接结果尚未确认，请再次检查原请求。'));
  render(<ConnectionsPage />); await act(async () => {});
  fireEvent.click(screen.getByRole('button', {name: '打开登录窗口'}));
  await screen.findByText('连接结果尚未确认，请再次检查原请求。');
  expect((screen.getByRole('button', {name: '我已完成登录，检查连接'}) as HTMLButtonElement).disabled).toBe(false);
  expect(screen.queryByText('账号已连接')).toBeNull();
});
