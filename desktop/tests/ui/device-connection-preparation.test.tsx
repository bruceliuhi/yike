// @vitest-environment jsdom
import {StrictMode} from 'react';
import {afterEach, expect, it, vi} from 'vitest';
import {act, cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {AppProvider, useApp} from '../../src/renderer/app/context';
import {SettingsPage} from '../../src/renderer/pages/Settings';
import {ConnectionsPage} from '../../src/renderer/pages/Connections';
import {service as baseService} from '../../src/renderer/services/client';
import type {Session} from '../../src/renderer/domain/models';
const ready = {state:'READY',deviceId:'12345678-1234-1234-1234-123456789abc',credentialVersion:1};
const user:Session = {authenticated:true,userId:'user-a',accountScope:{id:'space-a',version:1}};
function deferred<T>() {let resolve!:(value:T)=>void; const promise=new Promise<T>(r=>{resolve=r;});return {promise,resolve};}
function fixture() {
  return {...baseService,session:vi.fn().mockResolvedValue(user),
    info:vi.fn().mockResolvedValue({version:'test',platform:'win32',serviceConfigured:true}),
    connections:vi.fn().mockResolvedValue([]),connect:vi.fn().mockResolvedValue(undefined),
    deviceIdentity:{getStatus:vi.fn().mockResolvedValue({state:'NOT_PREPARED'}),prepare:vi.fn().mockResolvedValue(ready)}};
}
function Probe(){const {refreshSession,session,sessionReady}=useApp();return <><button onClick={()=>void refreshSession()}>刷新会话</button><output>{sessionReady ? session.userId ?? 'guest' : 'checking'}</output><p>业务资料可访问</p></>;}
afterEach(()=>{cleanup();vi.useRealTimers();window.history.replaceState(null,'','/');});
it('only prepares after confirmed login, without identity or retry payload; hides success',async()=>{
  const service=fixture();const login=deferred<Session>();service.session.mockReturnValue(login.promise);
  render(<AppProvider service={service}><Probe/></AppProvider>);
  await act(async()=>{});expect(service.deviceIdentity.prepare).not.toHaveBeenCalled();
  await act(async()=>login.resolve(user));
  await waitFor(()=>expect(service.deviceIdentity.prepare).toHaveBeenCalledExactlyOnceWith({}));
  expect(screen.getByText('业务资料可访问')).toBeTruthy();
  expect(screen.queryByText(/正在准备连接/)).toBeNull();
  expect(document.body.textContent).not.toContain(ready.deviceId);
  expect(screen.queryByRole('checkbox')).toBeNull();
});
it('signed out does not read or prepare identity',async()=>{
  const service=fixture();service.session.mockResolvedValue({authenticated:false});
  render(<AppProvider service={service}><Probe/></AppProvider>);await screen.findByText('guest');
  expect(service.deviceIdentity.prepare).not.toHaveBeenCalled();expect(service.deviceIdentity.getStatus).not.toHaveBeenCalled();
});
it('StrictMode and restart restore through prepare, never a renderer READY cache',async()=>{
  const service=fixture();const tree=<StrictMode><AppProvider service={service}><Probe/></AppProvider></StrictMode>;
  const first=render(tree);await waitFor(()=>expect(service.deviceIdentity.prepare).toHaveBeenCalled());
  first.unmount();service.deviceIdentity.prepare.mockClear();render(tree);
  await waitFor(()=>expect(service.deviceIdentity.prepare).toHaveBeenCalled());
  expect(service.deviceIdentity.prepare.mock.calls.every(args=>JSON.stringify(args)==='[{}]')).toBe(true);
});
it.each(['FAILED','SERVICE_UNAVAILABLE','REGISTRATION_UNKNOWN','PROOF_UNKNOWN'])('%s exposes a single explicit safe retry',async state=>{
  const service=fixture();service.deviceIdentity.prepare.mockResolvedValueOnce({state});
  render(<AppProvider service={service}><Probe/></AppProvider>);
  fireEvent.click(await screen.findByRole('button',{name:'重试'}));
  await waitFor(()=>expect(service.deviceIdentity.prepare).toHaveBeenCalledTimes(2));
  expect(service.deviceIdentity.prepare.mock.calls).toEqual([[{}],[state==='REGISTRATION_UNKNOWN'?{retryRegistration:true}:state==='PROOF_UNKNOWN'?{retryProof:true}:{}]]);
  expect(screen.queryByRole('checkbox')).toBeNull();
  await waitFor(()=>expect(screen.queryByRole('button',{name:'重试'})).toBeNull());
});
it.each(['REVOKED','KEY_MISSING','KEY_MISMATCH'])('%s requires support and never auto rebinds',async state=>{
  const service=fixture();service.deviceIdentity.prepare.mockResolvedValue({state});
  render(<AppProvider service={service}><Probe/></AppProvider>);
  await screen.findByText('连接暂不可用，请联系支持。');
  expect(screen.queryByRole('button',{name:'重试'})).toBeNull();expect(service.deviceIdentity.prepare).toHaveBeenCalledExactlyOnceWith({});
});
it.each([
  {...user,userId:'user-b'}, {...user,accountScope:{id:'space-b',version:1}},
  {...user,accountScope:{id:'space-a',version:2}}, {authenticated:false},
])('ignores old completion after session change %j',async next=>{
  const service=fixture();const old=deferred<unknown>();service.deviceIdentity.prepare.mockReturnValueOnce(old.promise).mockResolvedValue({state:'REVOKED'});
  render(<AppProvider service={service}><Probe/></AppProvider>);
  await waitFor(()=>expect(service.deviceIdentity.prepare).toHaveBeenCalledOnce());
  service.session.mockResolvedValue(next);fireEvent.click(screen.getByRole('button',{name:'刷新会话'}));
  if(next.authenticated)await screen.findByText('连接暂不可用，请联系支持。');else await screen.findByText('guest');
  await act(async()=>old.resolve(ready));
  if(next.authenticated)expect(screen.getByText('连接暂不可用，请联系支持。')).toBeTruthy();
  expect(document.body.textContent).not.toContain(ready.deviceId);
});
it('service replacement is unconfirmed even with same identity bridge; ignores old session and preparation',async()=>{
  const service=fixture();const old=deferred<unknown>();service.deviceIdentity.prepare.mockReturnValueOnce(old.promise).mockResolvedValue({state:'REVOKED'});
  const view=render(<AppProvider service={service}><Probe/></AppProvider>);
  await waitFor(()=>expect(service.deviceIdentity.prepare).toHaveBeenCalledOnce());
  const login=deferred<Session>();const replacement={...service,session:vi.fn().mockReturnValue(login.promise)};
  view.rerender(<AppProvider service={replacement}><Probe/></AppProvider>);
  expect(screen.getByText('checking')).toBeTruthy();
  await act(async()=>old.resolve(ready));expect(service.deviceIdentity.prepare).toHaveBeenCalledOnce();
  await act(async()=>login.resolve(user));await screen.findByText('连接暂不可用，请联系支持。');
});
it('returning to a previous service still waits for a fresh session confirmation',async()=>{
  const service=fixture();const view=render(<AppProvider service={service}><Probe/></AppProvider>);
  await waitFor(()=>expect(service.deviceIdentity.prepare).toHaveBeenCalledOnce());
  const other={...service,session:vi.fn().mockReturnValue(new Promise(()=>{}))};
  view.rerender(<AppProvider service={other}><Probe/></AppProvider>);
  service.session.mockReturnValue(new Promise(()=>{}));
  view.rerender(<AppProvider service={service}><Probe/></AppProvider>);
  expect(screen.getByText('checking')).toBeTruthy();
  await act(async()=>{});expect(service.deviceIdentity.prepare).toHaveBeenCalledOnce();
});
it('an old service refresh callback cannot supersede the new service bootstrap',async()=>{
  let oldRefresh! :()=>Promise<Session>;
  function Capture(){const {refreshSession}=useApp();oldRefresh ??= refreshSession;return <Probe/>;}
  const service=fixture();const view=render(<AppProvider service={service}><Capture/></AppProvider>);
  await screen.findByText('user-a');
  const login=deferred<Session>();const replacement={...service,session:vi.fn().mockReturnValue(login.promise)};
  view.rerender(<AppProvider service={replacement}><Probe/></AppProvider>);
  await act(async()=>{});
  await act(async()=>{await oldRefresh();});await act(async()=>login.resolve({...user,userId:'new-user'}));
  expect(screen.getByText('new-user')).toBeTruthy();
});
it('BUSY waits are finite and never add retry flags',async()=>{
  vi.useFakeTimers();const service=fixture();service.deviceIdentity.prepare.mockResolvedValue({state:'BUSY'});
  render(<AppProvider service={service}><Probe/></AppProvider>);await act(async()=>{});
  expect(screen.getByText('正在准备连接…')).toBeTruthy();
  await act(async()=>vi.advanceTimersByTimeAsync(5000));
  expect(screen.getByRole('button',{name:'重试'})).toBeTruthy();
  expect(service.deviceIdentity.prepare).toHaveBeenCalledTimes(3);
  await act(async()=>vi.advanceTimersByTimeAsync(180000));expect(service.deviceIdentity.prepare).toHaveBeenCalledTimes(3);
  expect(service.deviceIdentity.prepare.mock.calls).toEqual([[{}],[{}],[{}]]);
});
it.each(['REGISTRATION_UNKNOWN','PROOF_UNKNOWN'])('keeps the explicit %s retry during BUSY but stops on another UNKNOWN',async state=>{
  vi.useFakeTimers();const service=fixture();
  service.deviceIdentity.prepare.mockResolvedValueOnce({state}).mockResolvedValueOnce({state:'BUSY'}).mockResolvedValueOnce(ready);
  render(<AppProvider service={service}><Probe/></AppProvider>);await act(async()=>{});
  fireEvent.click(screen.getByRole('button',{name:'重试'}));await act(async()=>vi.advanceTimersByTimeAsync(1000));
  const options=state==='REGISTRATION_UNKNOWN'?{retryRegistration:true}:{retryProof:true};
  expect(service.deviceIdentity.prepare.mock.calls).toEqual([[{}],[options],[options]]);
  expect(screen.queryByRole('button',{name:'重试'})).toBeNull();
  cleanup();service.deviceIdentity.prepare.mockClear().mockResolvedValueOnce({state}).mockResolvedValueOnce({state:'BUSY'}).mockResolvedValue({state});
  render(<AppProvider service={service}><Probe/></AppProvider>);await act(async()=>{});
  fireEvent.click(screen.getByRole('button',{name:'重试'}));await act(async()=>vi.advanceTimersByTimeAsync(180000));
  expect(service.deviceIdentity.prepare.mock.calls).toEqual([[{}],[options],[options]]);
  expect(screen.getByRole('button',{name:'重试'})).toBeTruthy();
});
it('timeout releases UI without claiming IPC cancellation; late READY cannot overwrite failure',async()=>{
  vi.useFakeTimers();const service=fixture();const pending=deferred<unknown>();service.deviceIdentity.prepare.mockReturnValue(pending.promise);
  render(<AppProvider service={service}><Probe/></AppProvider>);await act(async()=>{});
  await act(async()=>vi.advanceTimersByTimeAsync(90000));expect(screen.getByRole('button',{name:'重试'})).toBeTruthy();
  await act(async()=>pending.resolve(ready));expect(screen.getByRole('button',{name:'重试'})).toBeTruthy();
  expect(service.deviceIdentity.prepare).toHaveBeenCalledOnce();
});
it('bad DTO or exception never echoes sensitive content',async()=>{
  const service=fixture();service.deviceIdentity.prepare.mockResolvedValueOnce({...ready,privateKey:'secret-key'}).mockRejectedValueOnce(new Error('secret-key'));
  render(<AppProvider service={service}><Probe/></AppProvider>);
  fireEvent.click(await screen.findByRole('button',{name:'重试'}));await waitFor(()=>expect(service.deviceIdentity.prepare).toHaveBeenCalledTimes(2));
  expect(document.body.textContent).not.toContain('secret-key');expect(document.body.textContent).not.toContain(ready.deviceId);
});
it('settings hides manual identity and diagnostic JSON, copying only safe state code from support',async()=>{
  const service={...fixture(),copy:vi.fn().mockResolvedValue(undefined)};render(<AppProvider service={service}><SettingsPage/></AppProvider>);
  await waitFor(()=>expect(service.deviceIdentity.prepare).toHaveBeenCalledOnce());
  expect(screen.queryByRole('button',{name:/核验本机/})).toBeNull();expect(screen.queryByText('本机身份')).toBeNull();
  fireEvent.click(screen.getByRole('button',{name:'联系支持'}));
  expect(screen.queryByLabelText('脱敏诊断内容')).toBeNull();
  fireEvent.click(screen.getByRole('button',{name:'复制诊断信息'}));
  await waitFor(()=>expect(service.copy).toHaveBeenCalledOnce());
  const diagnostic=service.copy.mock.calls[0][0] as string;
  expect(JSON.parse(diagnostic).connectionPreparation).toBe('READY');expect(diagnostic).not.toContain(ready.deviceId);
  expect(diagnostic).not.toContain('user-a');
});
it('blocks device-dependent login until prepared but keeps normal navigation accessible',async()=>{
  window.history.replaceState(null,'','#/connections?connect=xhs');
  const service=fixture();const pending=deferred<unknown>();service.deviceIdentity.prepare.mockReturnValue(pending.promise);
  render(<AppProvider service={service}><ConnectionsPage/><Probe/></AppProvider>);
  await waitFor(()=>expect(service.deviceIdentity.prepare).toHaveBeenCalledOnce());
  const button=screen.getByRole('button',{name:'打开登录窗口'}) as HTMLButtonElement;
  expect(button.disabled).toBe(true);fireEvent.click(button);expect(service.connect).not.toHaveBeenCalled();
  expect(screen.getByText('业务资料可访问')).toBeTruthy();
  await act(async()=>pending.resolve(ready));expect(button.disabled).toBe(false);
});
it.each(['FAILED','REGISTRATION_UNKNOWN','PROOF_UNKNOWN'])('platform modal exposes pending and accessible %s retry through the single shared runner',async state=>{
  window.history.replaceState(null,'','#/connections?connect=xhs');
  const service=fixture();const pending=deferred<unknown>();service.deviceIdentity.prepare.mockReturnValueOnce(pending.promise).mockResolvedValue(ready);
  render(<AppProvider service={service}><ConnectionsPage/></AppProvider>);
  await waitFor(()=>expect(service.deviceIdentity.prepare).toHaveBeenCalledOnce());
  const dialog=within(screen.getByRole('dialog',{name:'连接小红书'}));
  expect(dialog.getByText('正在准备连接…')).toBeTruthy();
  expect(dialog.queryByText(/点击下方按钮打开平台登录窗口/)).toBeNull();
  await act(async()=>pending.resolve({state}));
  fireEvent.click(dialog.getByRole('button',{name:'重试'}));
  await waitFor(()=>expect((dialog.getByRole('button',{name:'打开登录窗口'}) as HTMLButtonElement).disabled).toBe(false));
  const options=state==='REGISTRATION_UNKNOWN'?{retryRegistration:true}:state==='PROOF_UNKNOWN'?{retryProof:true}:{};
  expect(service.deviceIdentity.prepare.mock.calls).toEqual([[{}],[options]]);
  expect(service.connect).not.toHaveBeenCalled();
});
