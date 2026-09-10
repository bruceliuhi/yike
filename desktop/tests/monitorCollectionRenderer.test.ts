// @vitest-environment jsdom
import {describe,it,expect,vi} from 'vitest';
import {monitorCollection} from '../src/renderer/services/monitorCollection';
import type {YikeDesktopApi} from '../src/shared/contracts';
const id='11111111-1111-4111-8111-111111111111';
const other='22222222-2222-4222-8222-222222222222';
const target={platform:'BILIBILI' as const,access_mode:'PLATFORM_ACCOUNT' as const,connection_id:id,connection_version:1};
const command={action:'CREATE' as const,requestId:id,profileVersionId:id,strategyVersionId:id,targets:[target],humanConfirmed:true as const};
const plan={planId:id,profileVersionId:id,strategyVersionId:id,configurationSha256:'a'.repeat(64),state:'ACTIVE',revision:1,
 schedule:{kind:'interval',times:[],interval:30,start:'09:00',end:'18:00',timezone:'Asia/Shanghai',policyVersion:1},
 nextDueAt:'2026-09-11T09:00:00Z',localState:'ATTACHED',taskId:null,lastError:null};
describe('native monitor renderer boundary',()=>{
 it('uses only native IPC and correlates original responses',async()=>{
  expect(monitorCollection(undefined)).toBeUndefined();
  const invoke=vi.fn().mockResolvedValue({state:'RECORDED',requestId:id,plan});
  const bridge={monitorCollectionCommand:invoke} as unknown as YikeDesktopApi;
  const api=monitorCollection(bridge)!;
  expect(monitorCollection(bridge)).toBe(api);
  expect((await api.execute(command)).state).toBe('RECORDED');
  invoke.mockResolvedValue({state:'RECORDED',requestId:id,plan:{...plan,strategyVersionId:other}});
  await expect(api.execute(command)).rejects.toThrow('监控响应未核实');
  invoke.mockResolvedValue({state:'UNKNOWN',requestId:other});
  await expect(api.execute({action:'RECEIPT',command})).rejects.toThrow('监控响应未核实');
  invoke.mockRejectedValue(new Error('cookie secret'));
  await expect(api.execute({action:'LIST'})).rejects.toThrow('监控响应未核实');
 });
 it('rejects stale state receipts and duplicate plans',async()=>{
  const invoke=vi.fn().mockResolvedValue({state:'RECORDED',requestId:other,plan});
  const api=monitorCollection({monitorCollectionCommand:invoke} as unknown as YikeDesktopApi)!;
  await expect(api.execute({action:'SET_STATE',requestId:other,planId:id,expectedRevision:1,state:'PAUSED',humanConfirmed:true})).rejects.toThrow();
  invoke.mockResolvedValue({state:'LIST',plans:[plan,plan],serverTime:null,supported:true});
  await expect(api.execute({action:'LIST'})).rejects.toThrow();
 });
});
