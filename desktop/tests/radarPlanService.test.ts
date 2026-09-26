import {describe,expect,it,vi} from 'vitest';
import {createRadarPlanService} from '../src/renderer/services/radarPlan';
import {radarPlanInputSchema,type RadarPlanInput} from '../src/shared/radarPlan';
import {validatedOperation} from '../src/main/servicePolicy';
import type {Session} from '../src/renderer/domain/models';

const account='11111111-1111-4111-8111-111111111111';
const requestId='22222222-2222-4222-8222-222222222222';
const session:Session={authenticated:true,userId:'test-user',accountScope:{id:account,version:1}};
const input:RadarPlanInput={querySeeds:['展台搭建'],intentSignals:['询价'],exclusions:['招聘'],region:'深圳',demandTypes:['INQUIRY']};
const plan=()=>({version:'radar-search-directions-v1',strategies:[
  {id:'quick',name:'快速搜索',purpose:'先查找直接表达需求的内容',queries:['深圳 展台搭建 询价']},
  {id:'condition',name:'条件核验',purpose:'结合已确认条件减少无关结果',queries:['深圳 展台搭建 询价 -招聘']},
  {id:'broad',name:'扩展搜索',purpose:'用相关表达补查可能遗漏的需求',queries:['深圳 展台搭建']},
],queries:['深圳 展台搭建 询价','深圳 展台搭建 询价 -招聘','深圳 展台搭建']});
const response=(request:{requestId:string})=>({contractVersion:1,requestId:request.requestId,userId:session.userId,accountScope:session.accountScope,plan:plan()});

describe('authenticated pure search plan preview',()=>{
  it('uses an explicit fixed POST route and strictly bound response',async()=>{
    const transport=vi.fn(async(_operation,_path,_method,payload,_signal?:AbortSignal)=>response(payload));
    expect(await createRadarPlanService(transport).preview(input,session)).toEqual(plan());
    const [operation,path,method,payload,signal]=transport.mock.calls[0];
    expect({operation,path,method}).toEqual({operation:'researchPlan.preview',path:'/research-plan/preview',method:'POST'});
    expect(payload).toEqual({...input,contractVersion:1,requestId:expect.any(String)});
    expect(signal).toBeUndefined();
    const ipc=validatedOperation({operation,payload});
    expect(ipc).toMatchObject({path:'/api/ui/research-plan/preview',method:'POST',logout:false});
    expect(JSON.parse(ipc!.body!)).toEqual(payload);
    for(const extra of [{tenant_id:'other'},{url:'/admin'},{path:'/session'},{userId:'other'}])
      expect(validatedOperation({operation,payload:{...payload,...extra}})).toBeNull();
  });
  it.each([
    {authenticated:false,userId:'test-user',accountScope:session.accountScope},
    {authenticated:true,userId:'',accountScope:session.accountScope},
    {authenticated:true,userId:'test-user'},
  ])('does not dispatch without a customer session %#',async(invalid)=>{
    const transport=vi.fn();
    await expect(createRadarPlanService(transport).preview(input,invalid)).rejects.toThrow('请登录');
    expect(transport).not.toHaveBeenCalled();
  });
  it.each([
    {requestId}, {userId:'different'}, {accountScope:{id:requestId,version:1}},
    {accountScope:{id:account,version:2}}, {contractVersion:2}, {extra:'unexpected'},
  ])('rejects stale or mismatched responses %#',async(patch)=>{
    const transport=vi.fn(async(_operation,_path,_method,payload)=>({...response(payload),...patch}));
    await expect(createRadarPlanService(transport).preview(input,session)).rejects.toThrow('搜索计划未能核对');
  });
  it('rejects unknown groups and direction lists that differ from the complete plan',async()=>{
    for(const invalidPlan of [
      {...plan(),queries:['无关查询']},
      {...plan(),queries:[...plan().queries,plan().queries[0]]},
      {...plan(),strategies:plan().strategies.map(group=>({...group,queries:group.queries.map(()=>plan().queries[0])}))},
      {...plan(),strategies:plan().strategies.map(group=>({...group,id:'other'}))},
    ]){
      const transport=vi.fn(async(_operation,_path,_method,payload)=>({...response(payload),plan:invalidPlan}));
      await expect(createRadarPlanService(transport).preview(input,session)).rejects.toThrow('搜索计划未能核对');
    }
  });
  it('does not adopt an aborted late response or dispatch an already cancelled request',async()=>{
    const transport=vi.fn();
    const service=createRadarPlanService(transport),before=new AbortController();before.abort();
    await expect(service.preview(input,session,before.signal)).rejects.toThrow();
    expect(transport).not.toHaveBeenCalled();
    const during=new AbortController();
    transport.mockImplementation(async(_operation,_path,_method,payload)=>{during.abort();return response(payload);});
    await expect(service.preview(input,session,during.signal)).rejects.toThrow();
    expect(transport).toHaveBeenCalledTimes(1);
  });
  it('retains transport failure without retrying or fabricating a local success',async()=>{
    const error=new Error('session was revoked'),transport=vi.fn().mockRejectedValue(error);
    await expect(createRadarPlanService(transport).preview(input,session)).rejects.toBe(error);
    expect(transport).toHaveBeenCalledTimes(1);
  });
  it.each([
    {querySeeds:[]},{querySeeds:Array(21).fill('产品')},{querySeeds:['x'.repeat(161)]},
    {intentSignals:Array(21).fill('询价')},{exclusions:Array(26).fill('招聘')},
    {exclusions:null},{region:'地'.repeat(81)},{demandTypes:['INQUIRY','INQUIRY']},
    {demandTypes:['UNKNOWN']},{tenant_id:'other'},
  ])('rejects input above the contract bounds before transport %#',async(patch)=>{
    const transport=vi.fn();
    await expect(createRadarPlanService(transport).preview({...input,...patch} as RadarPlanInput,session)).rejects.toThrow();
    expect(transport).not.toHaveBeenCalled();
  });
  it.each(['x\u0001','x\u200b','x\ud800','x\ny'])('rejects non-text controls consistently with the server',value=>{
    expect(radarPlanInputSchema.safeParse({...input,querySeeds:[value]}).success).toBe(false);
    expect(validatedOperation({operation:'researchPlan.preview',payload:{...input,querySeeds:[value],contractVersion:1,requestId}})).toBeNull();
  });
});
