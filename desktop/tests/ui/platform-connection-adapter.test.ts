import {expect, it, vi} from 'vitest';
import {existsSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import type {PlatformConnectionResult} from '../../src/shared/platformConnection';

const flow = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`;
const row = {connection_id: flow(1), device_id: 'device-1', account_public_id: '66c01234abcdef0123456789',
  platform: 'XIAOHONGSHU' as const, status: 'CONNECTED' as const, connection_version: 1,
  connected_at: '2026-09-10T00:00:00Z', disconnected_at: null};
async function fixture() {
  expect(existsSync(fileURLToPath(new URL('../../src/renderer/services/platformConnection.ts', import.meta.url)))).toBe(true);
  const {createPlatformConnectionService} = await import('../../src/renderer/services/platformConnection');
  const invoke = vi.fn<(command: unknown) => Promise<PlatformConnectionResult>>();
  const read = vi.fn().mockResolvedValue([]);
  return {invoke, read, api: createPlatformConnectionService(() => ({platformConnectionCommand: invoke}), read)};
}
it('OPEN then repeated CHECK uses one flow and never grants source capabilities', async () => {
  const {api, invoke} = await fixture();
  invoke.mockResolvedValueOnce({state: 'OPENED', flowId: flow(1)})
    .mockResolvedValueOnce({state: 'WAITING_LOGIN', flowId: flow(1)})
    .mockResolvedValueOnce({state: 'CONNECTED', flowId: flow(1), connection: row});
  await api.connect('xhs');
  await expect(api.checkConnection('xhs')).rejects.toThrow('登录尚未完成');
  const result = await api.checkConnection('xhs');
  expect(result).toMatchObject({platform: 'xhs', accountId: row.account_public_id, status: 'CONNECTED', capabilities: []});
  expect(invoke.mock.calls.map(([command]) => command)).toEqual([
    {action: 'OPEN', platform: 'XIAOHONGSHU'},
    {action: 'CHECK', platform: 'XIAOHONGSHU', flowId: flow(1)},
    {action: 'CHECK', platform: 'XIAOHONGSHU', flowId: flow(1)},
  ]);
});
it.each([
  ['douyin', 'DOUYIN', 'owner.handle-1'],
  ['bilibili', 'BILIBILI', '1234567890'],
  ['zhihu', 'ZHIHU', 'zhihu-owner'],
] as const)('keeps the selected %s platform on OPEN, CHECK and CANCEL', async (platform, native, accountId) => {
  const {api, invoke} = await fixture();
  const nativeRow = {...row, platform: native, account_public_id: accountId};
  invoke.mockResolvedValueOnce({state:'OPENED',flowId:flow(1)})
    .mockResolvedValueOnce({state:'CONNECTED',flowId:flow(1),connection:nativeRow as never})
    .mockResolvedValueOnce({state:'CANCELLED',flowId:flow(1)});
  await api.connect(platform);
  expect((await api.checkConnection(platform)).accountId).toBe(accountId);
  await api.cancelConnection(platform);
  expect(invoke.mock.calls.map(([command]) => command)).toEqual([
    {action:'OPEN',platform:native},
    {action:'CHECK',platform:native,flowId:flow(1)},
    {action:'CANCEL',platform:native,flowId:flow(1)},
  ]);
});

it('a late older platform OPEN is cancelled with its captured platform', async () => {
  const {api, invoke} = await fixture(); let finish!:(value:PlatformConnectionResult)=>void;
  invoke.mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;}))
    .mockResolvedValueOnce({state:'OPENED',flowId:flow(2)})
    .mockResolvedValue({state:'CANCELLED',flowId:flow(1)});
  const old=api.connect('douyin').catch(error=>error.name);
  await vi.waitFor(()=>expect(invoke).toHaveBeenCalledTimes(1));
  await api.connect('bilibili'); finish({state:'OPENED',flowId:flow(1)});
  expect(await old).toBe('AbortError');
  expect(invoke).toHaveBeenLastCalledWith({action:'CANCEL',platform:'DOUYIN',flowId:flow(1)});
});
it('aborting a pending OPEN cancels its late flow without touching a newer flow', async () => {
  const {api, invoke} = await fixture();
  let finish!: (value: PlatformConnectionResult) => void;
  invoke.mockImplementationOnce(() => new Promise(resolve => {finish = resolve;}))
    .mockResolvedValueOnce({state: 'OPENED', flowId: flow(2)})
    .mockResolvedValue({state: 'CANCELLED', flowId: flow(1)});
  const abort = new AbortController();
  const old = api.connect('xhs', abort.signal).catch(error => error.name);
  await vi.waitFor(() => expect(invoke).toHaveBeenCalledTimes(1));
  abort.abort();
  await api.connect('xhs');
  finish({state: 'OPENED', flowId: flow(1)});
  expect(await old).toBe('AbortError');
  expect(invoke).toHaveBeenLastCalledWith({action: 'CANCEL', platform: 'XIAOHONGSHU', flowId: flow(1)});
  invoke.mockResolvedValueOnce({state: 'CONNECTED', flowId: flow(2), connection: row});
  expect((await api.checkConnection('xhs')).accountId).toBe(row.account_public_id);
  expect(invoke).toHaveBeenLastCalledWith({action: 'CHECK', platform: 'XIAOHONGSHU', flowId: flow(2)});
});
it('explicit modal/session cancellation also invalidates a not-yet-returned OPEN', async () => {
  const {api, invoke} = await fixture();
  let finish!: (value: PlatformConnectionResult) => void;
  invoke.mockImplementationOnce(() => new Promise(resolve => {finish = resolve;}))
    .mockResolvedValue({state: 'CANCELLED', flowId: flow(1)});
  const pending = api.connect('xhs').catch(error => error.name);
  await vi.waitFor(() => expect(invoke).toHaveBeenCalledTimes(1));
  await api.cancelConnection('xhs');
  finish({state: 'OPENED', flowId: flow(1)});
  expect(await pending).toBe('AbortError');
  expect(invoke).toHaveBeenLastCalledWith({action: 'CANCEL', platform: 'XIAOHONGSHU', flowId: flow(1)});
});
it('aborting the old UI request after OPENED does not cancel the established flow', async () => {
  const {api, invoke} = await fixture();
  const abort = new AbortController();
  invoke.mockResolvedValueOnce({state: 'OPENED', flowId: flow(1)})
    .mockResolvedValueOnce({state: 'CONNECTED', flowId: flow(1), connection: row});
  await api.connect('xhs', abort.signal);
  abort.abort();
  expect((await api.checkConnection('xhs')).status).toBe('CONNECTED');
  expect(invoke.mock.calls.some(([command]) => (command as {action: string}).action === 'CANCEL')).toBe(false);
});
it('without a flow check is strictly a current registry read, not OPEN or VERIFY', async () => {
  const {api, invoke, read} = await fixture();
  const existing = {platform: 'xhs', accountId: row.account_public_id, status: 'UNVERIFIED', capabilities: []};
  read.mockResolvedValue([existing]);
  expect(await api.checkConnection('xhs')).toBe(existing);
  expect(invoke).not.toHaveBeenCalled();
  read.mockResolvedValue([existing, {...existing, accountId: 'other'}]);
  await expect(api.checkConnection('xhs')).rejects.toThrow('唯一');
});
it('unsupported or missing native service and malformed responses stay unavailable', async () => {
  const {api, invoke} = await fixture();
  await expect(api.connect('unregistered-platform')).rejects.toMatchObject({code: 'CAPABILITY_UNAVAILABLE'});
  expect(invoke).not.toHaveBeenCalled();
  invoke.mockResolvedValueOnce({state: 'SERVICE_UNAVAILABLE'});
  await expect(api.connect('xhs')).rejects.toThrow('未配置');
  invoke.mockResolvedValueOnce({state: 'OPENED', flowId: flow(1), cookie: 'private'} as never);
  await expect(api.connect('xhs')).rejects.toThrow('连接响应尚未确认');
});
