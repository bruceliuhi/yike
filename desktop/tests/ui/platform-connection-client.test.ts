// @vitest-environment jsdom
import {afterEach, expect, it, vi} from 'vitest';
import {service} from '../../src/renderer/services/client';
import type {YikeDesktopApi} from '../../src/shared/contracts';
const host = window as unknown as {yikeDesktop?: YikeDesktopApi};
const flowId = '00000000-0000-4000-8000-000000000001';
const row = {connection_id: flowId, device_id: 'device-1', account_public_id: '66c01234abcdef0123456789',
  platform: 'XIAOHONGSHU', status: 'CONNECTED', connection_version: 1,
  connected_at: '2026-09-10T00:00:00Z', disconnected_at: null};
afterEach(async () => {await service.cancelConnection?.('xhs').catch(() => {}); delete host.yikeDesktop; vi.unstubAllGlobals();});
it('real client routes platform login through only the fixed native command, never requestApi writes', async () => {
  const invoke = vi.fn().mockResolvedValueOnce({state: 'OPENED', flowId})
    .mockResolvedValueOnce({state: 'CONNECTED', flowId, connection: row})
    .mockResolvedValue({state: 'CANCELLED', flowId});
  const requestApi = vi.fn();
  host.yikeDesktop = {platformConnectionCommand: invoke, requestApi} as unknown as YikeDesktopApi;
  await service.connect('xhs');
  expect(await service.checkConnection('xhs')).toMatchObject({status: 'CONNECTED', accountId: row.account_public_id, capabilities: []});
  expect(invoke).toHaveBeenCalledWith({action: 'OPEN', platform: 'XIAOHONGSHU'});
  expect(requestApi).not.toHaveBeenCalled();
});
it('real client no-flow check uses only current registration GET and preserves UNVERIFIED', async () => {
  const requestApi = vi.fn().mockResolvedValue({ok: true, status: 200, data: {items: [{...row, status: 'UNVERIFIED'}]}});
  host.yikeDesktop = {requestApi} as unknown as YikeDesktopApi;
  expect((await service.checkConnection('xhs')).status).toBe('UNVERIFIED');
  expect(requestApi).toHaveBeenCalledExactlyOnceWith({operation: 'connections.list', payload: undefined});
});
it.each(['xhs','douyin','bilibili','zhihu'])('missing %s native capability never falls through into browser login or service mutation', async (platform) => {
  const fetch = vi.fn(); vi.stubGlobal('fetch', fetch);
  const requestApi = vi.fn();
  host.yikeDesktop = {requestApi} as unknown as YikeDesktopApi;
  await expect(service.connect(platform)).rejects.toMatchObject({code: 'SERVICE_UNAVAILABLE'});
  expect(fetch).not.toHaveBeenCalled();
  expect(requestApi).not.toHaveBeenCalled();
});
it('real client connects read-only login STATUS without falling through to requestApi',async()=>{
 const invoke=vi.fn().mockResolvedValueOnce({state:'OPENED',flowId})
  .mockResolvedValueOnce({state:'LOGIN_READY',flowId}).mockResolvedValue({state:'CANCELLED',flowId});
 const requestApi=vi.fn();host.yikeDesktop={platformConnectionCommand:invoke,requestApi} as unknown as YikeDesktopApi;
 await service.connect('xhs');expect(await service.connectionLoginStatus!('xhs')).toBe('LOGIN_READY');
 expect(invoke).toHaveBeenLastCalledWith({action:'STATUS',platform:'XIAOHONGSHU',flowId});
 expect(requestApi).not.toHaveBeenCalled();
});
