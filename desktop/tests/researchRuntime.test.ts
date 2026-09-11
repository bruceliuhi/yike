import {describe,expect,it,vi} from 'vitest';
import {validatedOperation} from '../src/main/servicePolicy';
import {researchRuntimeCapabilitySchema,researchRuntimeStatusSchema} from '../src/shared/researchRuntime';
import {desktopExecution} from '../src/renderer/services/desktopExecution';
import type {YikeDesktopApi} from '../src/shared/contracts';

const id=(n:number)=>`10000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
const status=()=>({contractVersion:1,taskId:id(1),runId:id(2),phase:'RUNNING',sourceScope:'V2EX_LATEST_INDEX',
  sourceLabel:'V2EX最新主题 · 公开单源研究',acceptedOriginals:2,analyzedOriginals:1,skippedOriginals:0,candidateIds:[id(3)],
  canAdvance:true,stopCode:null,newActionsBlocked:false,effectsPending:false,usage:{
    sourceReads:{issued:1,pending:0,succeeded:1,failed:0,unknown:0},modelCalls:{issued:1,pending:0,succeeded:1,failed:0,unknown:0},
    actualSoubei:null,settlementState:'PENDING'}});

describe('strict research runtime wire contract',()=>{
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
