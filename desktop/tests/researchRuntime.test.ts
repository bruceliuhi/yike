import {describe,expect,it,vi} from 'vitest';
import {validatedOperation} from '../src/main/servicePolicy';
import {researchRuntimeCapabilitySchema,researchRuntimeStatusSchema,researchAllowsSource} from '../src/shared/researchRuntime';
import {desktopExecution} from '../src/renderer/services/desktopExecution';
import type {YikeDesktopApi} from '../src/shared/contracts';

const id=(n:number)=>`10000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
const status=()=>({contractVersion:1,taskId:id(1),runId:id(2),phase:'RUNNING',sourceScope:'V2EX_LATEST_INDEX',
  sourceLabel:'V2EX最新主题 · 公开单源研究',acceptedOriginals:2,analyzedOriginals:1,skippedOriginals:0,candidateIds:[id(3)],
  canAdvance:true,stopCode:null,newActionsBlocked:false,effectsPending:false,usage:{
    sourceReads:{issued:1,pending:0,succeeded:1,failed:0,unknown:0},modelCalls:{issued:1,pending:0,succeeded:1,failed:0,unknown:0},
    actualSoubei:null,settlementState:'PENDING'}});

describe('strict research runtime wire contract',()=>{
  it('negotiates only the exact fixed catalog and binds node status to its version and label',()=>{
    const catalog={contractVersion:2,sourceScope:'V2EX_SELECTED_INDEX',sourceLabel:'V2EX定向板块 · 单源索引研究',
      sourceIds:['v2ex-latest-v1','v2ex-qna-v1','v2ex-outsourcing-authors-v1'],maxFreshEffectsPerAdvance:1,settlementState:'PENDING'};
    expect(researchRuntimeCapabilitySchema.parse(catalog)).toEqual(catalog);
    expect(researchAllowsSource(catalog,'v2ex-qna-v1')).toBe(true);
    expect(researchAllowsSource({...catalog,sourceIds:['v2ex-qna-v1','v2ex-qna-v1']},'v2ex-qna-v1')).toBe(false);
    const legacy={contractVersion:1,sourceScope:status().sourceScope,sourceLabel:status().sourceLabel,maxFreshEffectsPerAdvance:1,settlementState:'PENDING'};
    expect(researchAllowsSource(legacy,'v2ex-qna-v1')).toBe(false);
    expect(researchAllowsSource(legacy,'v2ex-latest-v1')).toBe(true);
    for(const [sourceScope,sourceLabel] of [
      ['V2EX_QNA_INDEX','V2EX问与答 · 单源索引研究（未读评论）'],
      ['V2EX_OUTSOURCING_INDEX','V2EX项目外包 · 单源索引研究（未读作者回复）'],
    ]){
      const node={...status(),contractVersion:2,sourceScope,sourceLabel};
      expect(researchRuntimeStatusSchema.parse(node)).toEqual(node);
      expect(researchRuntimeStatusSchema.safeParse({...node,contractVersion:1}).success).toBe(false);
      expect(researchRuntimeStatusSchema.safeParse({...node,sourceLabel:status().sourceLabel}).success).toBe(false);
    }
    expect(researchRuntimeStatusSchema.safeParse({...status(),contractVersion:2}).success).toBe(false);
  });
  it('routes explicit catalog negotiation without widening IPC authority',()=>{
    expect(validatedOperation({operation:'researchRuntime.capability',payload:{sourceCatalogVersion:1}})).toEqual({
      path:'/api/ui/research-execution/capability?source_catalog_version=1',method:'GET',logout:false});
    for(const payload of [{sourceCatalogVersion:2},{sourceCatalogVersion:'1'},{sourceCatalogVersion:null},{sourceCatalogVersion:1,tenantId:id(1)}])
      expect(validatedOperation({operation:'researchRuntime.capability',payload})).toBeNull();
  });
  it('accepts nonfinancial resource snapshots and rejects false closure',()=>{
    const closeout={state:'OPEN',overduePermits:0,asOf:'2026-09-11T14:00:00.000Z'};
    const running={...status(),usage:{...status().usage,resourceCloseout:closeout}};
    expect(researchRuntimeStatusSchema.safeParse(running).success).toBe(true);
    expect(researchRuntimeStatusSchema.safeParse({...running,usage:{...running.usage,
      resourceCloseout:{...closeout,state:'RECORDED'}}}).success).toBe(false);
    expect(researchRuntimeStatusSchema.safeParse({...running,usage:{...running.usage,
      resourceCloseout:{...closeout,overduePermits:1}}}).success).toBe(false);
    expect(researchRuntimeStatusSchema.safeParse({...running,usage:{...running.usage,
      resourceCloseout:{...closeout,state:'UNCERTAIN'}}}).success).toBe(false);
    expect(researchRuntimeStatusSchema.safeParse({...running,usage:{...running.usage,
      resourceCloseout:{...closeout,asOf:'invalid'}}}).success).toBe(false);
    const done={...running,phase:'COMPLETED',canAdvance:false,newActionsBlocked:true,
      usage:{...running.usage,resourceCloseout:{...closeout,state:'RECORDED'}}};
    expect(researchRuntimeStatusSchema.safeParse(done).success).toBe(true);
    expect(researchRuntimeStatusSchema.safeParse({...done,usage:{...done.usage,
      modelCalls:{issued:1,pending:1,succeeded:0,failed:0,unknown:0}}}).success).toBe(false);
  });
  it('accepts only the fixed capability and coherent status DTO',()=>{
    expect(researchRuntimeCapabilitySchema.parse({contractVersion:1,sourceScope:'V2EX_LATEST_INDEX',
      sourceLabel:'V2EX最新主题 · 公开单源研究',maxFreshEffectsPerAdvance:1,settlementState:'PENDING'})).toBeTruthy();
    expect(researchRuntimeStatusSchema.parse(status())).toEqual(status());
    expect(researchRuntimeStatusSchema.safeParse({...status(),candidateIds:[id(3),id(3)]}).success).toBe(false);
    expect(researchRuntimeStatusSchema.safeParse({...status(),usage:{...status().usage,actualSoubei:0}}).success).toBe(false);
    expect(researchRuntimeStatusSchema.safeParse({...status(),analyzedOriginals:3}).success).toBe(false);
  });
  it('routes exact identity-free requests',()=>{
    expect(validatedOperation({operation:'researchRuntime.capability'})).toEqual({path:'/api/ui/research-execution/capability',method:'GET',logout:false});
    expect(validatedOperation({operation:'researchRuntime.status',payload:{taskId:id(1)}})).toEqual({path:`/api/ui/research-execution/tasks/${id(1)}`,method:'GET',logout:false});
    expect(validatedOperation({operation:'researchRuntime.advance',payload:{taskId:id(1),runId:id(2)}})).toEqual({
      path:`/api/ui/research-execution/tasks/${id(1)}/advance`,method:'POST',body:JSON.stringify({runId:id(2)}),logout:false,timeoutMs:75_000});
    expect(validatedOperation({operation:'researchRuntime.advance',payload:{taskId:id(1),runId:id(2),tenantId:id(3)}})).toBeNull();
  });
  it('exposes native protocol version separately from server capability',()=>{
    const service=desktopExecution({executionCommand:vi.fn(),requestApi:vi.fn()} as unknown as YikeDesktopApi)!;
    expect(service.researchContractVersion).toBe(1);
  });
});
