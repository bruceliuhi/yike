// @vitest-environment jsdom
import {afterEach, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {DeviceIdentityPanel, type DeviceIdentityApi} from '../../src/renderer/pages/settings/DeviceIdentityPanel';
import type {DeviceIdentityStatus} from '../../src/shared/deviceIdentity';

afterEach(cleanup);
const ready = {state:'READY' as const, deviceId:'12345678-1234-1234-1234-123456789abc',credentialVersion:1};
function setup(status: any = {state:'NOT_PREPARED'}) {
  const api = {getStatus:vi.fn().mockResolvedValue(status),prepare:vi.fn().mockResolvedValue(ready)};
  const view = render(<DeviceIdentityPanel api={api} scope="user-a" />);
  return {api,...view};
}
it('requires explicit confirmation and sends no identity or signing payload', async () => {
  const {api} = setup();
  const button = await screen.findByRole('button',{name:'核验本机设备'});
  expect(api.prepare).not.toHaveBeenCalled();
  expect((button as HTMLButtonElement).disabled).toBe(true);
  await waitFor(()=>expect((screen.getByRole('checkbox') as HTMLInputElement).disabled).toBe(false));
  fireEvent.click(screen.getByRole('checkbox',{name:'确认在当前账号下核验本机设备'}));
  fireEvent.click(button);
  await screen.findByText('上次身份核验通过');
  expect(api.prepare).toHaveBeenCalledExactlyOnceWith({});
  expect(screen.getByText(/不代表平台已连接或使用授权已激活/)).toBeTruthy();
  expect(document.body.textContent).not.toContain(ready.deviceId);
  expect(screen.queryByText(/本机编号|最近一次观察|执行前仍需服务端授权/)).toBeNull();
});
it.each(['REGISTRATION_UNKNOWN','PROOF_UNKNOWN'] as const)('checks %s without retry flags, retries only after a separate confirmation', async state => {
  const {api} = setup({state});
  api.prepare.mockResolvedValue({state});
  fireEvent.click(await screen.findByRole('button',{name:'核对原请求'}));
  expect(screen.queryByText(/设备证明/)).toBeNull();
  await waitFor(()=>expect(api.prepare).toHaveBeenCalledExactlyOnceWith({}));
  const retry = screen.getByRole('button',{name:'确认后重试原请求'});
  expect((retry as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(screen.getByRole('checkbox',{name:'确认重试同一原请求，不创建新的设备身份'}));
  fireEvent.click(retry);
  await waitFor(()=>expect(api.prepare).toHaveBeenLastCalledWith(state === 'REGISTRATION_UNKNOWN' ? {retryRegistration:true} : {retryProof:true}));
});
it.each(['KEY_MISSING','KEY_MISMATCH','REVOKED'] as const)('does not offer rebinding or retry for %s', async state => {
  const {api} = setup({state});
  await waitFor(()=>expect(api.getStatus).toHaveBeenCalled());
  await screen.findByText(/请联系支持/);
  expect(screen.queryByText(/密钥/)).toBeNull();
  expect(screen.queryByRole('checkbox')).toBeNull();
  expect(api.prepare).not.toHaveBeenCalled();
});
it('ignores a late preparation after changing accounts', async () => {
  let resolve!: (value:any)=>void;
  const api: DeviceIdentityApi = {getStatus:vi.fn().mockResolvedValue({state:'NOT_PREPARED'}),prepare:vi.fn(()=>new Promise<DeviceIdentityStatus>(r=>resolve=r))};
  const view = render(<DeviceIdentityPanel api={api} scope="a"/>);
  await screen.findByRole('button',{name:'核验本机设备'});
  await waitFor(()=>expect((screen.getByRole('checkbox') as HTMLInputElement).disabled).toBe(false));
  fireEvent.click(screen.getByRole('checkbox'));
  fireEvent.click(screen.getByRole('button',{name:'核验本机设备'}));
  await waitFor(()=>expect(api.prepare).toHaveBeenCalledOnce());
  view.rerender(<DeviceIdentityPanel api={api} scope="b"/>);
  resolve(ready);
  await screen.findByText('尚未核验本机身份');
  expect(screen.queryByText('上次身份核验通过')).toBeNull();
});
it('shows fixed failure for malformed status or IPC errors without echoing secrets', async () => {
  const {api} = setup({...ready,privateKey:'secret'});
  await screen.findByText(/核验结果尚未确认/);
  expect(screen.queryByText(/secret/)).toBeNull();
  api.prepare.mockRejectedValue(new Error('secret path'));
  fireEvent.click(screen.getByRole('checkbox'));
  fireEvent.click(screen.getByRole('button',{name:'核验本机设备'}));
  await screen.findByText(/核验结果尚未确认/);
  expect(screen.queryByText(/secret path/)).toBeNull();
});
