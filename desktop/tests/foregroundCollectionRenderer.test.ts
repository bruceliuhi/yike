// @vitest-environment jsdom
import {afterEach, describe, expect, it, vi} from 'vitest';
import {foregroundCollection, attachForegroundBinding} from '../src/renderer/services/foregroundCollection';
import {service} from '../src/renderer/services/client';
import {startBlockers} from '../src/renderer/domain/task';
import {newTaskDraft, EMPTY_PROFILE, type PlatformConnection} from '../src/renderer/domain/models';
import type {YikeDesktopApi} from '../src/shared/contracts';

const id = '11111111-1111-4111-8111-111111111111';
const other = '22222222-2222-4222-8222-222222222222';
const binding = {mode:'xhs-foreground-v1' as const, platform:'XIAOHONGSHU' as const,
  connectionId:id, connectionVersion:2, deviceId:id, accountPublicId:'account01'};
function row(): PlatformConnection { return {platform:'xhs', status:'CONNECTED', accountId:'account01', capabilities:[],
  registration:{connectionId:id, deviceId:id, version:2, connectedAt:'2026-09-10T00:00:00Z', disconnectedAt:null}}; }
afterEach(() => { delete (window as any).yikeDesktop; });

describe('foreground renderer boundary', () => {
  it('is optional and uses only the fixed bridge with strict task correlation', async () => {
    expect(foregroundCollection(undefined)).toBeUndefined();
    const invoke = vi.fn().mockResolvedValue({state:'AVAILABLE', bindings:[binding]});
    const bridge = {foregroundCollectionCommand:invoke} as unknown as YikeDesktopApi;
    const api = foregroundCollection(bridge)!;
    expect(foregroundCollection(bridge)).toBe(api);
    expect(await api.execute({action:'CAPABILITIES'})).toEqual({state:'AVAILABLE', bindings:[binding]});
    await expect(api.execute({action:'STATUS', taskId:id})).rejects.toThrow('采集响应未核实');
    invoke.mockResolvedValue({state:'STATUS', taskId:other, localState:'COMPLETED', serverStatus:'SUCCEEDED', stopConfirmed:true, recordsUsed:0, recoverable:false});
    await expect(api.execute({action:'STATUS', taskId:id})).rejects.toThrow('采集响应未核实');
    invoke.mockRejectedValue(new Error('private raw cookie'));
    await expect(api.execute({action:'CAPABILITIES'})).rejects.toThrow('采集响应未核实');
  });
  it('attaches three-platform bindings only to their exact platform rows', () => {
    const xhs=row();
    const douyin={...row(),platform:'douyin' as const,accountId:'douyin.account-1',registration:{...row().registration!,connectionId:other}};
    const videoBinding={mode:'three-platform-foreground-v1' as const,platform:'DOUYIN' as const,connectionId:other,
      connectionVersion:2,deviceId:id,accountPublicId:'douyin.account-1'};
    const rows=attachForegroundBinding([xhs,douyin],{state:'AVAILABLE',bindings:[binding,videoBinding]});
    expect(rows[0].foregroundBinding).toEqual(binding);
    expect(rows[1].foregroundBinding).toEqual(videoBinding);
  });
  it('rejects duplicate platform bindings from the native boundary', async () => {
    const bridge={foregroundCollectionCommand:vi.fn().mockResolvedValue({state:'AVAILABLE',bindings:[binding,binding]})} as unknown as YikeDesktopApi;
    await expect(foregroundCollection(bridge)!.execute({action:'CAPABILITIES'})).rejects.toThrow('采集响应未核实');
  });
  it('adds only search to one exact registered row without discarding registration', () => {
    const original = row();
    const rows = attachForegroundBinding([original], {state:'AVAILABLE', bindings:[binding]});
    expect(rows[0]).toEqual({...original, foregroundBinding:binding, capabilities:['search'], reason:expect.any(String)});
    expect(original.capabilities).toEqual([]);
    expect(attachForegroundBinding([original], {state:'UNAVAILABLE'})).toEqual([original]);
    expect(attachForegroundBinding([original, original], {state:'AVAILABLE', bindings:[binding]})).toEqual([original,original]);
  });
  it.each(['connection','version','device','account','platform','status','disconnected','unregistered'])(
    'does not authorize a mismatched %s row', field => {
      const value = row();
      if (field==='connection') value.registration!.connectionId=other;
      if (field==='version') value.registration!.version=3;
      if (field==='device') value.registration!.deviceId=other;
      if (field==='account') value.accountId='account02';
      if (field==='platform') value.platform='bilibili';
      if (field==='status') value.status='EXPIRED';
      if (field==='disconnected') value.registration!.disconnectedAt='2026-09-10T00:00:00Z';
      if (field==='unregistered') delete value.registration;
      expect(attachForegroundBinding([value], {state:'AVAILABLE', bindings:[binding]})).toEqual([value]);
    });
  it('client reads exact capabilities and reports device ready without changing sidecar status', async () => {
    const runtime = {state:'NOT_READY'};
    const command = vi.fn().mockResolvedValue({state:'AVAILABLE', bindings:[binding]});
    (window as any).yikeDesktop = {foregroundCollectionCommand:command,
      getClientInfo:vi.fn().mockResolvedValue({version:'test', platform:'win32', serviceConfigured:true}),
      getRuntimeStatus:vi.fn().mockResolvedValue(runtime), requestApi:vi.fn().mockResolvedValue({ok:true,status:200,data:{items:[{
        connection_id:id, device_id:id, account_public_id:'account01', platform:'XIAOHONGSHU', status:'CONNECTED',
        connection_version:2, connected_at:'2026-09-10T00:00:00Z', disconnected_at:null}]}})};
    const [info, rows] = await Promise.all([service.info(), service.connections()]);
    expect(info.deviceReady).toBe(true);
    expect(runtime.state).toBe('NOT_READY');
    expect(rows[0].registration?.connectionId).toBe(id);
    expect(rows[0].foregroundBinding).toEqual(binding);
    command.mockResolvedValue({state:'UNAVAILABLE'});
    expect((await service.info()).deviceReady).toBe(false);
    expect((await service.connections())[0].capabilities).toEqual([]);
  });
});

describe('bounded foreground start prerequisites', () => {
  const draft = {...newTaskDraft(), name:'test', profileId:id, profileVersion:1, platforms:['xhs'] as const,
    accounts:{xhs:'account01'}, terms:[{id:'term',value:'采购',origin:'manual' as const,edited:false}]};
  const profiles = [{id,version:1,status:'CONFIRMED' as const,description:'',fields:EMPTY_PROFILE}];
  it('allows only the matched registered foreground search binding', () => {
    const ready = attachForegroundBinding([row()], {state:'AVAILABLE',bindings:[binding]});
    expect(startBlockers({...draft,platforms:[...draft.platforms]}, profiles, ready, true)).toEqual([]);
    expect(startBlockers({...draft,platforms:[...draft.platforms]}, profiles, [row()], true).length).toBeGreaterThan(0);
  });
  it('allows one exact video-platform foreground search binding',()=>{
    const videoDraft={...draft,platforms:['douyin'] as const,accounts:{douyin:'douyin.account-1'}} as any;
    const videoRow={...row(),platform:'douyin' as const,accountId:'douyin.account-1'};
    const videoBinding={...binding,mode:'three-platform-foreground-v1' as const,platform:'DOUYIN' as const,accountPublicId:'douyin.account-1'};
    const ready=attachForegroundBinding([videoRow],{state:'AVAILABLE',bindings:[videoBinding]});
    expect(startBlockers(videoDraft,profiles,ready,true)).toEqual([]);
  });
  it.each(['links','exclusions','research','monitor','otherplatform','bindingchanged'])(
    'blocks unsupported foreground scope %s', field => {
      const current = structuredClone({...draft,platforms:[...draft.platforms]});
      const ready = attachForegroundBinding([row()], {state:'AVAILABLE',bindings:[binding]});
      if (field==='links') current.links='https://example.com';
      if (field==='exclusions') current.exclusions=[{id:'exclude',value:'别的',origin:'manual',edited:false}];
      if (field==='research') (current as any).research={};
      if (field==='monitor') current.mode='monitor';
      if (field==='otherplatform') current.platforms.push('web' as 'xhs');
      if (field==='bindingchanged') ready[0].registration!.version=3;
      expect(startBlockers(current, profiles, ready, true).length).toBeGreaterThan(0);
    });
  it.each([{max_records:101,max_runtime_seconds:600},{max_records:50,max_runtime_seconds:901}])(
    'explains the bounded source limit %j', limits => {
      const ready=attachForegroundBinding([row()],{state:'AVAILABLE',bindings:[binding]});
      expect(startBlockers({...draft,platforms:[...draft.platforms],executionLimits:limits},profiles,ready,true).join(' '))
        .toMatch(/100.*900/);
    });
});
