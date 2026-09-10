import {describe, expect, it, vi} from 'vitest';
const mocks = vi.hoisted(() => ({expose: vi.fn(), invoke: vi.fn().mockResolvedValue({status: 'cancelled'})}));
vi.mock('electron', () => ({contextBridge: {exposeInMainWorld: mocks.expose}, ipcRenderer: {invoke: mocks.invoke}}));
import '../src/preload/index';
import {SAVE_EXPORT_CHANNEL, type YikeDesktopApi} from '../src/shared/contracts';

describe('preload export bridge', () => {
  it('exposes a frozen fixed API and forwards only the export payload to its fixed channel', async () => {
    expect(mocks.expose).toHaveBeenCalledOnce();
    const [name, api] = mocks.expose.mock.calls[0] as [string, YikeDesktopApi];
    expect(name).toBe('yikeDesktop'); expect(Object.isFrozen(api)).toBe(true);
    expect(Object.keys(api).sort()).toEqual(['copyText','getClientInfo','getDeviceIdentityStatus','getRuntimeStatus','openExternal','prepareDeviceIdentity','requestApi','saveExport']);
    const request = {format: 'csv' as const, name: 'TEST.csv', content: 'TEST'};
    expect(await api.saveExport(request)).toEqual({status: 'cancelled'});
    expect(mocks.invoke).toHaveBeenCalledWith(SAVE_EXPORT_CHANNEL, request);
    expect(api).not.toHaveProperty('writeFile'); expect(api).not.toHaveProperty('invoke');
    expect(api).not.toHaveProperty('requestDevice'); expect(api).not.toHaveProperty('sign');
    await api.getDeviceIdentityStatus!();
    expect(mocks.invoke).toHaveBeenCalledWith('desktop:get-device-identity-status');
    const retry = {retryProof:true};
    await api.prepareDeviceIdentity!(retry);
    expect(mocks.invoke).toHaveBeenCalledWith('desktop:prepare-device-identity', retry);
  });
});
