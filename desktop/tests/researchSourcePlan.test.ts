import {expect,it} from 'vitest';
import {researchRuntimeCapabilitySchema,researchRuntimeStatusSchema,researchAllowsSelection} from '../src/shared/researchRuntime';
import {researchRecordAllotments} from '../src/shared/researchSourcePlan';
import {researchDraftSchema,defaultResearchSettings} from '../src/renderer/domain/researchUsage';
import {strategyPrepareRequest} from '../src/renderer/domain/researchStrategies';
import {newTaskDraft,type TaskDraft} from '../src/renderer/domain/models';
import {validatedOperation} from '../src/main/servicePolicy';

export const plan={version:1 as const,sources:['v2ex-qna-v1','v2ex-outsourcing-authors-v1'] as const};
export const capability={contractVersion:3,sourceScope:'V2EX_INDEX_PLAN',sourceLabel:'V2EX多板块 · 有界来源计划',
  sourceIds:['v2ex-latest-v1','v2ex-qna-v1','v2ex-outsourcing-authors-v1'],maxPlannedSources:3,maxFreshEffectsPerAdvance:1,settlementState:'PENDING'};
const counts={issued:0,pending:0,succeeded:0,failed:0,unknown:0};
function status(){return {contractVersion:3,taskId:'10000000-0000-4000-8000-000000000001',runId:'10000000-0000-4000-8000-000000000002',
  phase:'RUNNING',sourceScope:capability.sourceScope,sourceLabel:capability.sourceLabel,acceptedOriginals:null,
  analyzedOriginals:0,skippedOriginals:0,candidateIds:[],canAdvance:true,stopCode:null,newActionsBlocked:false,effectsPending:false,
  usage:{sourceReads:counts,modelCalls:counts,actualSoubei:null,settlementState:'PENDING'},
  sourceProgress:plan.sources.map(sourceId=>({sourceId,phase:'NOT_STARTED',acceptedOriginals:null as number|null,recordLimit:5}))};}
it('retains a strict optional plan through draft and strategy, without changing legacy fields',()=>{
  const base={...defaultResearchSettings(),maxSoubei:20};
  expect(JSON.stringify(researchDraftSchema.parse(base))).toBe(JSON.stringify(base));
  expect(researchDraftSchema.parse({...base,sourcePlan:plan}).sourcePlan).toEqual(plan);
  const draft:TaskDraft={...newTaskDraft(),profileId:'10000000-0000-4000-8000-000000000003',name:'TEST',platforms:['web' as const],
    publicSource:plan.sources[0],terms:[{id:'term',value:'采购',origin:'manual' as const,edited:false}],research:{...base,sourcePlan:{...plan,sources:[...plan.sources]}}};
  const prepare=()=>strategyPrepareRequest(draft,'10000000-0000-4000-8000-000000000004',{max_records:10,max_runtime_seconds:60});
  expect(prepare().configuration.research?.sourcePlan).toEqual(plan);
  expect(()=>strategyPrepareRequest(draft,'10000000-0000-4000-8000-000000000004',{max_records:1,max_runtime_seconds:60})).toThrow();
  expect(()=>strategyPrepareRequest(draft,'10000000-0000-4000-8000-000000000004',{max_records:101,max_runtime_seconds:60})).toThrow();
  for(const changed of [{...draft,platforms:['web','bilibili']},{...draft,mode:'monitor'},{...draft,platforms:['bilibili']}])
    expect(()=>strategyPrepareRequest(changed as TaskDraft,'10000000-0000-4000-8000-000000000004',{max_records:10,max_runtime_seconds:60})).toThrow();
  for(const invalid of [null,{...plan,sources:[plan.sources[0],plan.sources[0]]},{...plan,extra:true},{...plan,version:2}])
    expect(researchDraftSchema.safeParse({...base,sourcePlan:invalid}).success).toBe(false);
  draft.research!.limits.sources=1;expect(prepare).toThrow();
  draft.research!.limits.sources=2;draft.publicSource='v2ex-outsourcing-authors-v1';expect(prepare).toThrow();
});
it('allots frozen fair shares and only permits a plan on capability v3',()=>{
  expect(researchRecordAllotments(5,plan.sources).map(row=>row.recordLimit)).toEqual([3,2]);
  expect(researchRecordAllotments(1,plan.sources)).toEqual([]);
  const selection={...plan,sources:[...plan.sources]};
  expect(researchAllowsSelection(capability,plan.sources[0],selection)).toBe(true);
  expect(researchAllowsSelection(capability,plan.sources[1],selection)).toBe(false);
  const {maxPlannedSources,...rest}=capability;
  expect(researchAllowsSelection({...rest,contractVersion:2,sourceScope:'V2EX_SELECTED_INDEX',sourceLabel:'V2EX定向板块 · 单源索引研究'},plan.sources[0],selection)).toBe(false);
});
it('negotiates the exact v3 plan capability through the allowlisted IPC query',()=>{
  expect(researchRuntimeCapabilitySchema.safeParse(capability).success).toBe(true);
  expect(validatedOperation({operation:'researchRuntime.capability',payload:{sourcePlanVersion:1}})?.path)
    .toBe('/api/ui/research-execution/capability?source_plan_version=1');
  for(const payload of [{sourcePlanVersion:2},{sourcePlanVersion:1,sourceCatalogVersion:1},{sourcePlanVersion:'1'}])
    expect(validatedOperation({operation:'researchRuntime.capability',payload})).toBeNull();
});
it('requires every source receipt before aggregate counts or completion',()=>{
  const value=status();expect(researchRuntimeStatusSchema.safeParse(value).success).toBe(true);
  value.sourceProgress[0]={...value.sourceProgress[0],phase:'SUCCEEDED',acceptedOriginals:2};
  expect(researchRuntimeStatusSchema.safeParse(value).success).toBe(true);
  expect(researchRuntimeStatusSchema.safeParse({...value,acceptedOriginals:2}).success).toBe(false);
  expect(researchRuntimeStatusSchema.safeParse({...value,phase:'COMPLETED'}).success).toBe(false);
  value.sourceProgress[1]={...value.sourceProgress[1],phase:'SUCCEEDED',acceptedOriginals:1};
  const done={...value,phase:'COMPLETED',acceptedOriginals:3,analyzedOriginals:3,canAdvance:false,newActionsBlocked:true};
  expect(researchRuntimeStatusSchema.safeParse(done).success).toBe(true);
  for(const bad of [{...done,analyzedOriginals:2},{...done,acceptedOriginals:4},
    {...done,sourceProgress:[done.sourceProgress[0],done.sourceProgress[0]]},
    {...done,sourceProgress:done.sourceProgress.map(s=>({...s,recordLimit:51}))},
    {...done,sourceProgress:done.sourceProgress.map(s=>({...s,acceptedOriginals:6}))},
    {...done,contractVersion:2},{...done,sourceProgress:undefined}])
    expect(researchRuntimeStatusSchema.safeParse(bad).success).toBe(false);
});
