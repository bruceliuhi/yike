import {expect,it} from 'vitest';
import {researchRuntimeCapabilitySchema,researchRuntimeStatusSchema,researchAllowsSelection} from '../src/shared/researchRuntime';
import {strategyConfigurationSchema,prepareStrategySchema} from '../src/shared/researchStrategies';
import {validatedOperation} from '../src/main/servicePolicy';
import {dynamicCapability,dynamicStatus,counts,id} from './fixtures/dynamicResearch';
import {newTaskDraft,type TaskDraft,type Profile} from '../src/renderer/domain/models';
import {defaultResearchSettings} from '../src/renderer/domain/researchUsage';
import {startBlockers} from '../src/renderer/domain/task';
import {taskDraftSchema} from '../src/renderer/app/taskDraft';

const configuration=()=>({schema_version:'research-strategy-v1',name:'合成动态研究',source:'search',keywords:['课程接入'],exclusions:[],
  links:[],mode:'once',schedule:null,publicSource:'public-web-agent-v1',research:{version:1,demandTypes:['INQUIRY'],maxSoubei:20,
    limits:{sources:20,minutes:15,modelCalls:20},stopAtAnyLimit:true,evidenceOrder:'SOURCE_MATCH_CONTEXT',
    dynamicScope:{version:1,maxAgeDays:60,timezone:'Asia/Shanghai'}}});

it('negotiates v4 explicitly without advertising an effect-per-click contract',()=>{
  expect(researchRuntimeCapabilitySchema.parse(dynamicCapability)).toEqual(dynamicCapability);
  expect(researchAllowsSelection(dynamicCapability,'public-web-agent-v1')).toBe(true);
  expect(researchAllowsSelection(dynamicCapability,'v2ex-qna-v1')).toBe(true);
  expect(researchAllowsSelection(dynamicCapability,'v2ex-latest-v1',{version:1,sources:['v2ex-latest-v1','v2ex-qna-v1']})).toBe(true);
  expect(researchRuntimeCapabilitySchema.safeParse({...dynamicCapability,maxFreshEffectsPerAdvance:1}).success).toBe(false);
  expect(validatedOperation({operation:'researchRuntime.capability',payload:{dynamicResearchVersion:1}})?.path)
    .toBe('/api/ui/research-execution/capability?dynamic_research_version=1');
  expect(validatedOperation({operation:'researchRuntime.capability',payload:{dynamicResearchVersion:1,sourcePlanVersion:1}})).toBeNull();
});
it('validates persisted dynamic progress without treating searches as originals',()=>{
  expect(researchRuntimeStatusSchema.parse(dynamicStatus())).toEqual(dynamicStatus());
  const value={...dynamicStatus(),phase:'RUNNING',canAdvance:false,newActionsBlocked:true,
    acceptedOriginals:1,candidateIds:[id(3)],discovery:{searches:counts(2),reads:counts(1),unpublishedOriginals:0},
    usage:{...dynamicStatus().usage,sourceReads:counts(3)}};
  expect(researchRuntimeStatusSchema.parse(value)).toEqual(value);
  for(const change of [{acceptedOriginals:2},{discovery:{...value.discovery,unpublishedOriginals:1}},
    {canAdvance:true},{contractVersion:3},{sourceProgress:[]},{usage:{...value.usage,sourceReads:counts(2)}}])
    expect(researchRuntimeStatusSchema.safeParse({...value,...change}).success).toBe(false);
});
it('couples confirmed dynamic time scope to dynamic-only task semantics',()=>{
  const c=configuration();expect(strategyConfigurationSchema.parse(c)).toEqual(c);
  const scope={schema_version:'strategy-confirmation-v1',request_id:id(4),draft_id:id(5),draft_revision:1,
    profile_version_id:id(6),configuration:c,platforms:['PUBLIC_WEB'],max_records:20,max_runtime_seconds:1800};
  expect(prepareStrategySchema.parse(scope)).toEqual(scope);
  for(const platforms of [['BILIBILI'],['PUBLIC_WEB','BILIBILI']])
    expect(prepareStrategySchema.safeParse({...scope,platforms}).success).toBe(false);
  for(const change of [{publicSource:'v2ex-latest-v1'},{mode:'monitor'},{links:['https://example.com/need']},
    {research:{...c.research,dynamicScope:undefined}},{research:{...c.research,sourcePlan:{version:1,sources:['v2ex-latest-v1','v2ex-qna-v1']}}},
    {research:{...c.research,dynamicScope:{...c.research.dynamicScope,maxAgeDays:0}}},
    {research:{...c.research,dynamicScope:{...c.research.dynamicScope,timezone:'bad-zone'}}}])
    expect(strategyConfigurationSchema.safeParse({...c,...change}).success).toBe(false);
});
it('requires dynamic authority and preserves incomplete editable time scope on disk',()=>{
  const draft:TaskDraft={...newTaskDraft(),name:'研究测试',profileId:id(6),profileVersion:1,platforms:['web'],publicSource:'public-web-agent-v1',
    terms:[{id:id(7),value:'课程接入',origin:'manual',edited:false}],source:'search',mode:'once',accounts:{},
    executionLimits:{max_records:20,max_runtime_seconds:1800},research:{...defaultResearchSettings(),maxSoubei:20,
      limits:{sources:20,minutes:15,modelCalls:20},dynamicScope:{version:1,maxAgeDays:60,timezone:'Asia/Shanghai'}}};
  const profile:Profile={id:id(6),version:1,status:'CONFIRMED',description:'课程接入开发',fields:{service:'课程接入',customer:'机构',regions:'全国',preference:'',exclusions:''}};
  expect(startBlockers(draft,[profile],[],true,false,true)).toEqual([]);
  expect(startBlockers(draft,[profile],[],true,false,false).length).toBeGreaterThan(0);
  expect(startBlockers(draft,[profile],[],false,false,true)).toContain('执行设备尚未绑定或当前不可用。');
  const incomplete=structuredClone(draft);incomplete.research!.dynamicScope!.maxAgeDays=0;
  expect(taskDraftSchema.parse(incomplete).research?.dynamicScope?.maxAgeDays).toBe(0);
  expect(startBlockers(incomplete,[profile],[],true,false,true).length).toBeGreaterThan(0);
});
