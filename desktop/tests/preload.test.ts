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
    expect(Object.keys(api).sort()).toEqual(['copyText','executionCommand','foregroundCollectionCommand','getClientInfo','getDeviceIdentityStatus','getPortableRuntimeStatus','getRuntimeStatus','nativeOutreachCommand','openExternal','platformConnectionCommand','prepareDeviceIdentity','requestApi','saveExport']);
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
    await api.executionCommand!({action:'LIST'});
    expect(mocks.invoke).toHaveBeenCalledWith('desktop:execution-command', {action:'LIST'});
    await api.platformConnectionCommand!({action:'OPEN', platform:'XIAOHONGSHU'});
    expect(mocks.invoke).toHaveBeenCalledWith('desktop:platform-connection-command', {action:'OPEN', platform:'XIAOHONGSHU'});
    await api.foregroundCollectionCommand!({action:'CAPABILITIES'});
    expect(mocks.invoke).toHaveBeenCalledWith('desktop:foreground-collection',{action:'CAPABILITIES'});
    const cancel={action:'CANCEL' as const,flowId:'00000000-0000-4000-8000-000000000001'};
    await api.nativeOutreachCommand!(cancel);
    expect(mocks.invoke).toHaveBeenCalledWith('desktop:native-outreach',cancel);
    expect(api).not.toHaveProperty('requestOutreach');
    await api.getPortableRuntimeStatus!();
    expect(mocks.invoke).toHaveBeenCalledWith('desktop:portable-runtime-status');
  });
});
