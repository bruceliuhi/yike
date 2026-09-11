// @vitest-environment jsdom
import {describe,it,expect} from 'vitest';
import {createHash} from 'node:crypto';
import {foregroundCollectionResultSchema} from '../src/shared/foregroundCollection';
import {attachForegroundBinding} from '../src/renderer/services/foregroundCollection';
import {newTaskDraft,EMPTY_PROFILE} from '../src/renderer/domain/models';
import {startBlockers} from '../src/renderer/domain/task';
import {strategyPrepareRequest} from '../src/renderer/domain/researchStrategies';
import {desktopStartCommand} from '../src/renderer/pages/tasks/useDesktopExecution';
import {taskDraftSchema} from '../src/renderer/app/taskDraft';
import {draftFromTemplate,templateFromDraft} from '../src/renderer/pages/tasks/localTemplates';
const id='11111111-1111-4111-8111-111111111111',other='22222222-2222-4222-8222-222222222222';
const publicBinding={sourceId:'v2ex-latest-v1',deviceId:id} as const;
const native={mode:'four-platform-foreground-v1',platform:'XIAOHONGSHU',connectionId:id,connectionVersion:1,deviceId:id,accountPublicId:'account01'} as const;
const draft=()=>({...newTaskDraft(),name:'公开采样',profileId:id,profileVersion:1,platforms:['web' as const],accounts:{},terms:[{id:'term',value:'采购',origin:'manual' as const,edited:false}],executionLimits:{max_records:10,max_runtime_seconds:60}});
const profiles=[{id,version:1,status:'CONFIRMED' as const,description:'',fields:EMPTY_PROFILE}];
function receipt(value:ReturnType<typeof draft>){
 const request=strategyPrepareRequest(value,id,value.executionLimits);
 return {schema_version:'strategy-confirmation-v1',operation:'PREPARE',request_id:id,strategy_version_id:other,
  draft_id:value.id,draft_revision:value.revision,profile_version_id:id,profile_sha256:'a'.repeat(64),configuration_sha256:'b'.repeat(64),
  state:'DRAFT',recorded_at:'2026-09-10T00:00:00Z',snapshot:{strategy_version_id:other,profile_version_id:id,
   configuration:request.configuration,platforms:request.platforms,...value.executionLimits}} as const;
}
describe('bounded public source renderer contract',()=>{
 it.each(['v2ex-qna-v1','v2ex-outsourcing-authors-v1'] as const)('preserves %s in drafts/templates and requires a matching live source catalog',source=>{
  const value={...draft(),publicSource:source};
  const expanded={...publicBinding,sourceIds:['v2ex-latest-v1',source]};
  const capability=foregroundCollectionResultSchema.parse({state:'AVAILABLE',bindings:[],publicBinding:expanded});
  const rows=attachForegroundBinding([],capability);
  expect(taskDraftSchema.parse(value)).toHaveProperty('publicSource',source);
  expect(draftFromTemplate(templateFromDraft(value,value.name))).toHaveProperty('publicSource',source);
  expect(strategyPrepareRequest(value,id,value.executionLimits).configuration.publicSource).toBe(source);
  expect(startBlockers(value,profiles,rows,true)).toEqual([]);
  expect(startBlockers(value,profiles,attachForegroundBinding([],{state:'AVAILABLE',bindings:[],publicBinding}),true)).toContain('所选公开板块当前不可用，请重新核对来源；不会自动切换板块。');
  expect(()=>desktopStartCommand(value,receipt(draft()),rows,other)).toThrow();
 });
 it.each([[],['v2ex-qna-v1'],['v2ex-latest-v1','v2ex-latest-v1'],['v2ex-latest-v1','other']].map(sourceIds=>({sourceIds})))('rejects inconsistent source catalog %j',({sourceIds})=>{
  expect(foregroundCollectionResultSchema.safeParse({state:'AVAILABLE',bindings:[],publicBinding:{...publicBinding,sourceIds}}).success).toBe(false);
 });
 it('accepts public-only and same-device mixed bindings',()=>{
  expect(foregroundCollectionResultSchema.safeParse({state:'AVAILABLE',bindings:[],publicBinding}).success).toBe(true);
  expect(foregroundCollectionResultSchema.safeParse({state:'AVAILABLE',bindings:[native],publicBinding}).success).toBe(true);
  expect(foregroundCollectionResultSchema.safeParse({state:'AVAILABLE',bindings:[],publicBinding:{...publicBinding,monitorSupported:true}}).success).toBe(true);
 });
 it.each([undefined,{...publicBinding,sourceId:'other'},{...publicBinding,accountId:'fake'},{...publicBinding,connectionId:id}])('rejects missing or widened public scope %j',value=>{
  expect(foregroundCollectionResultSchema.safeParse({state:'AVAILABLE',bindings:[],...(value?{publicBinding:value}:{})}).success).toBe(false);
 });
 it('rejects cross-device mixed binding',()=>expect(foregroundCollectionResultSchema.safeParse({state:'AVAILABLE',bindings:[native],publicBinding:{...publicBinding,deviceId:other}}).success).toBe(false));
 it('builds an anonymous row and requires its trusted scope before starting',()=>{
  const rows=attachForegroundBinding([],{state:'AVAILABLE',bindings:[],publicBinding} as any);
  expect(rows).toEqual([{platform:'web',status:'CONNECTED',capabilities:['search'],publicBinding,reason:expect.stringContaining('V2EX近期主题')}]);
  expect(startBlockers(draft(),profiles,rows,true)).toEqual([]);
  expect(startBlockers(draft(),profiles,[{platform:'web',status:'CONNECTED',capabilities:['search']}],true).length).toBeGreaterThan(0);
  for(const patch of [{mode:'monitor'},{links:'https://v2ex.com'},{executionLimits:{max_records:101,max_runtime_seconds:60}},{executionLimits:undefined}])
   expect(startBlockers({...draft(),...patch} as any,profiles,rows,true).length).toBeGreaterThan(0);
 });
 it('builds existing anonymous targets, blocks missing source and cross-device mixed START',()=>{
  const rows=attachForegroundBinding([],{state:'AVAILABLE',bindings:[],publicBinding});
  const value=draft(),prepared=receipt(value);
  expect(desktopStartCommand(value,prepared,rows,other).targets).toEqual([{platform:'PUBLIC_WEB',access_mode:'PUBLIC_ANONYMOUS',connection_id:null,connection_version:null}]);
  expect(()=>desktopStartCommand(value,prepared,[],other)).toThrow();
  const unbound=structuredClone(prepared);delete unbound.snapshot.configuration.publicSource;
  expect(()=>desktopStartCommand(value,unbound,rows,other)).toThrow();
  const mixed={...value,platforms:['xhs','web'],accounts:{xhs:'account01'}} as any;
  const nativeRow={platform:'xhs' as const,status:'CONNECTED' as const,accountId:'account01',capabilities:['search'],foregroundBinding:native,
   registration:{connectionId:id,version:1,deviceId:id,connectedAt:'2026-09-10T00:00:00Z',disconnectedAt:null}};
  expect(startBlockers(mixed,profiles,[nativeRow,...rows],true)).toEqual([]);
  expect(desktopStartCommand(mixed,receipt(mixed),[nativeRow,...rows],other).targets).toHaveLength(2);
  const changed=[nativeRow,{...rows[0],publicBinding:{...publicBinding,deviceId:other}}];
  expect(()=>desktopStartCommand(mixed,receipt(mixed),changed,other)).toThrow();
  expect(startBlockers(mixed,profiles,changed,true).length).toBeGreaterThan(0);
 });
 it('binds source into the snapshot digest, normalizes new once snapshots and preserves monitor schedule',()=>{
  const value=draft(),web=strategyPrepareRequest(value,id,value.executionLimits).configuration;
  expect(web.publicSource).toBe('v2ex-latest-v1');expect(web.schedule).toBe(null);
  const legacy=strategyPrepareRequest({...value,platforms:['xhs']},id,value.executionLimits).configuration;
  expect(legacy).not.toHaveProperty('publicSource');expect(legacy.schedule).toBe(null);
  expect(strategyPrepareRequest({...value,platforms:['xhs'],mode:'monitor'},id,value.executionLimits).configuration.schedule).toEqual(value.schedule);
  const sha=(x:unknown)=>createHash('sha256').update(JSON.stringify(x)).digest('hex');
  const {publicSource,...without}=web;expect(sha(web)).not.toBe(sha(without));
 });
 it('may prepare research intent but cannot use the ordinary public driver to execute it',()=>{
  const value={...draft(),research:{version:1 as const,demandTypes:['INQUIRY' as const],maxSoubei:100,
   limits:{sources:10,minutes:5,modelCalls:5},stopAtAnyLimit:true as const,evidenceOrder:'SOURCE_MATCH_CONTEXT' as const}};
  const rows=attachForegroundBinding([],{state:'AVAILABLE',bindings:[],publicBinding});
  expect(receipt(value).snapshot.configuration.research).toEqual(value.research);
  expect(()=>desktopStartCommand(value,receipt(value),rows,other)).toThrow();
  expect(startBlockers(value,profiles,rows,true).length).toBeGreaterThan(0);
 });
});
