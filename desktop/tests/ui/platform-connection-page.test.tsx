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
afterEach(()=>{cleanup();vi.useRealTimers();});
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
it('shows terminal login failure promptly without automatic CHECK',async()=>{
 context.service.connectionLoginStatus=vi.fn().mockRejectedValue(new ServiceError('PLATFORM_RESPONSE_CHANGED','平台页面响应已变化，请重试。'));
 render(<ConnectionsPage />);await act(async()=>{});
 fireEvent.click(screen.getByRole('button',{name:'打开登录窗口'}));await act(async()=>{});
 expect(screen.getByText('平台页面响应已变化，请重试。')).toBeTruthy();
 expect(screen.queryByText('等待登录')).toBeNull();
 expect((screen.getByRole('button',{name:'我已完成登录，检查连接'}) as HTMLButtonElement).disabled).toBe(true);
 expect(context.service.checkConnection).not.toHaveBeenCalled();
});
it('LOGIN_READY is only a prompt for explicit CHECK, never connection success',async()=>{
 context.service.connectionLoginStatus=vi.fn().mockResolvedValue('LOGIN_READY');
 render(<ConnectionsPage />);await act(async()=>{});
 fireEvent.click(screen.getByRole('button',{name:'打开登录窗口'}));await act(async()=>{});
 expect(screen.getByText('登录已完成，待检查连接')).toBeTruthy();
 expect(screen.queryByText('账号已连接')).toBeNull();expect(context.service.checkConnection).not.toHaveBeenCalled();
 fireEvent.click(screen.getByRole('button',{name:'我已完成登录，检查连接'}));await act(async()=>{});
 expect(context.service.checkConnection).toHaveBeenCalledTimes(1);
});
it('expired CHECK clears stale login readiness until an explicit new OPEN',async()=>{
 context.service.connectionLoginStatus=vi.fn().mockResolvedValue('LOGIN_READY');
 vi.mocked(context.service.checkConnection).mockRejectedValue(new ServiceError('LOGIN_EXPIRED','登录等待已过期，请重新打开平台登录窗口。'));
 render(<ConnectionsPage />);await act(async()=>{});
 fireEvent.click(screen.getByRole('button',{name:'打开登录窗口'}));await screen.findByText('登录已完成，待检查连接');
 fireEvent.click(screen.getByRole('button',{name:'我已完成登录，检查连接'}));
 await screen.findByText('登录等待已过期，请重新打开平台登录窗口。');
 expect((screen.getByRole('button',{name:'我已完成登录，检查连接'}) as HTMLButtonElement).disabled).toBe(true);
 expect(screen.queryByText('请本人点击“我已完成登录，检查连接”，完成当前账号连接核验。')).toBeNull();
 expect(context.service.connect).toHaveBeenCalledTimes(1);
 fireEvent.click(screen.getByRole('button',{name:'打开登录窗口'}));await screen.findByText('登录已完成，待检查连接');
 expect((screen.getByRole('button',{name:'我已完成登录，检查连接'}) as HTMLButtonElement).disabled).toBe(false);
 expect(context.service.checkConnection).toHaveBeenCalledTimes(1);
});
it('bounds a hanging status without overlapping requests and ignores its late success',async()=>{
 vi.useFakeTimers();let finish!:(value:'LOGIN_READY')=>void;
 context.service.connectionLoginStatus=vi.fn(()=>new Promise<'LOGIN_READY'>(resolve=>{finish=resolve;}));
 render(<ConnectionsPage />);await act(async()=>{});
 fireEvent.click(screen.getByRole('button',{name:'打开登录窗口'}));await act(async()=>{});
 await act(async()=>{await vi.advanceTimersByTimeAsync(4999);});expect(context.service.connectionLoginStatus).toHaveBeenCalledTimes(1);
 await act(async()=>{await vi.advanceTimersByTimeAsync(1);});
 expect(screen.getByText('登录状态读取超时，请核对原生窗口后重新打开。')).toBeTruthy();
 await act(async()=>finish('LOGIN_READY'));expect(screen.queryByText('登录已完成，待检查连接')).toBeNull();
 await act(async()=>{await vi.advanceTimersByTimeAsync(10000);});expect(context.service.connectionLoginStatus).toHaveBeenCalledTimes(1);
});
it.each(['cancel','workspace','account','platform','check','reopen','unmount'] as const)('ignores a late failed STATUS after %s',async(action)=>{
 let fail!:(e:unknown)=>void;
 context.service.connectionLoginStatus=vi.fn().mockImplementationOnce(()=>new Promise((_resolve,reject)=>{fail=reject;})).mockResolvedValue('WAITING_LOGIN');
 const view=render(<ConnectionsPage />);await act(async()=>{});
 fireEvent.click(screen.getByRole('button',{name:'打开登录窗口'}));await act(async()=>{});
 expect(context.service.connectionLoginStatus).toHaveBeenCalledTimes(1);
 if(action==='cancel')fireEvent.click(screen.getByRole('button',{name:'取消'}));
 if(action==='workspace'){context={...context,session:{...context.session,accountScope:{id:'space',version:2}}};view.rerender(<ConnectionsPage />);}
 if(action==='account'){context={...context,session:{...context.session,userId:'another'}};view.rerender(<ConnectionsPage />);}
 if(action==='platform'){context={...context,route:parseRoute('#/connections?connect=douyin')};view.rerender(<ConnectionsPage />);}
 if(action==='check')fireEvent.click(screen.getByRole('button',{name:'我已完成登录，检查连接'}));
 if(action==='reopen')fireEvent.click(screen.getByRole('button',{name:'打开登录窗口'}));
 if(action==='unmount')view.unmount();
 await act(async()=>{});await act(async()=>fail(new ServiceError('PLATFORM_RESPONSE_CHANGED','stale terminal error')));
 expect(screen.queryByText('stale terminal error')).toBeNull();
});
it('polls once per second and surfaces a later terminal failure without another OPEN',async()=>{
 vi.useFakeTimers();context.service.connectionLoginStatus=vi.fn().mockResolvedValueOnce('WAITING_LOGIN')
  .mockRejectedValueOnce(new ServiceError('PLATFORM_RESPONSE_CHANGED','terminal failure'));
 render(<ConnectionsPage />);await act(async()=>{});fireEvent.click(screen.getByRole('button',{name:'打开登录窗口'}));await act(async()=>{});
 expect(screen.getByText('等待登录')).toBeTruthy();
 await act(async()=>{await vi.advanceTimersByTimeAsync(999);});expect(context.service.connectionLoginStatus).toHaveBeenCalledTimes(1);
 await act(async()=>{await vi.advanceTimersByTimeAsync(1);});expect(screen.getByText('操作未完成，请查看当前状态后再继续。')).toBeTruthy();
 expect(screen.queryByText('terminal failure')).toBeNull();
 expect(context.service.connect).toHaveBeenCalledTimes(1);expect(context.service.checkConnection).not.toHaveBeenCalled();
});
it('LOGIN_READY observation ends at 120 seconds without claiming login failure or automatic CHECK',async()=>{
 vi.useFakeTimers();context.service.connectionLoginStatus=vi.fn().mockResolvedValue('LOGIN_READY');
 render(<ConnectionsPage />);await act(async()=>{});fireEvent.click(screen.getByRole('button',{name:'打开登录窗口'}));await act(async()=>{});
 await act(async()=>{await vi.advanceTimersByTimeAsync(119999);});expect(screen.getByText('登录已完成，待检查连接')).toBeTruthy();
 await act(async()=>{await vi.advanceTimersByTimeAsync(1);});expect(screen.getByText('登录已识别，待检查连接')).toBeTruthy();
 expect(screen.queryByText('等待超时')).toBeNull();
 expect(screen.queryByText(/等待登录已超时/)).toBeNull();
 expect(screen.getByText('自动观察已结束，尚未确认连接。请点击“我已完成登录，检查连接”核对当前状态；若检查提示未登录，再重新打开登录窗口。')).toBeTruthy();
 expect((screen.getByRole('button',{name:'我已完成登录，检查连接'}) as HTMLButtonElement).disabled).toBe(false);
 expect(screen.queryByText('账号已连接')).toBeNull();
 const count=vi.mocked(context.service.connectionLoginStatus).mock.calls.length;
 await act(async()=>{await vi.advanceTimersByTimeAsync(5000);});expect(context.service.connectionLoginStatus).toHaveBeenCalledTimes(count);
 expect(context.service.checkConnection).not.toHaveBeenCalled();
});
it('an expired observation without LOGIN_READY does not claim that login was recognized',async()=>{
 vi.useFakeTimers();context.service.connectionLoginStatus=vi.fn().mockResolvedValue('WAITING_LOGIN');
 render(<ConnectionsPage />);await act(async()=>{});fireEvent.click(screen.getByRole('button',{name:'打开登录窗口'}));await act(async()=>{});
 await act(async()=>{await vi.advanceTimersByTimeAsync(120000);});
 expect(screen.getByText('等待登录已结束')).toBeTruthy();
 expect(screen.queryByText('登录已识别，待检查连接')).toBeNull();
 const count=vi.mocked(context.service.connectionLoginStatus).mock.calls.length;
 await act(async()=>{await vi.advanceTimersByTimeAsync(5000);});expect(context.service.connectionLoginStatus).toHaveBeenCalledTimes(count);
 expect(context.service.checkConnection).not.toHaveBeenCalled();
});
