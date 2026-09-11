import {expect,it,vi} from 'vitest';
import {createOpportunityBriefService} from '../src/renderer/services/opportunityBriefClient';
import {validatedOperation} from '../src/main/servicePolicy';
import {briefBusinessDay} from '../src/renderer/domain/opportunityBrief';
const id=(n:number)=>`00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
const current={authenticated:true,userId:id(1),accountScope:{id:id(2),version:1}};
const query={contractVersion:1 as const,requestId:id(3),userId:id(1),accountScopeId:id(2),scopeVersion:1,profileId:id(4),profileVersion:1,businessDate:briefBusinessDay(Date.now(),'Asia/Shanghai'),timezone:'Asia/Shanghai'};
const snapshot=()=>({...query,snapshotId:'brief:1',audience:'CUSTOMER',generatedAt:new Date(Date.now()-1000).toISOString(),expiresAt:new Date(Date.now()+60000).toISOString(),coverage:'NOT_CHECKED',lastCompletedCheckAt:null,checkedScope:[],uncheckedScope:['尚未完成检查'],runs:[],groups:{contact:{items:[],total:0},changes:{items:[],total:0},followup:{items:[],total:0}}});
it('reads the exact snapshot through a fixed bounded route',async()=>{
 const transport=vi.fn().mockResolvedValue(snapshot()),api=createOpportunityBriefService(transport,async()=>current),abort=new AbortController();
 expect((await api.query(query,abort.signal)).businessDate).toBe(query.businessDate);
 expect(transport.mock.calls[0]).toEqual(['opportunityBrief.query','/opportunity-brief/query','POST',query,abort.signal]);
 expect(validatedOperation({operation:'opportunityBrief.query',payload:query})?.path).toBe('/api/ui/opportunity-brief/query');
 expect(validatedOperation({operation:'opportunityBrief.query',payload:{...query,tenantId:id(9)}})).toBeNull();
 expect(validatedOperation({operation:'opportunityBrief.query',payload:{...query,profileId:'sample:1'}})).toBeNull();
});
it('rejects another date/account response and preserves unavailable errors',async()=>{
 const transport=vi.fn().mockResolvedValue({...snapshot(),businessDate:'2000-01-01'}),api=createOpportunityBriefService(transport,async()=>current);
 await expect(api.query(query)).rejects.toThrow();
 transport.mockResolvedValue({...snapshot(),accountScopeId:id(8)});await expect(api.query(query)).rejects.toThrow();
 transport.mockRejectedValue(new Error('501 unavailable'));await expect(api.query(query)).rejects.toThrow('501 unavailable');
});
it('discards late account and cancellation results without retry',async()=>{
 let user=current;const abort=new AbortController(),transport=vi.fn().mockImplementation(async()=>{user={...current,userId:id(7)};return snapshot();});
 const api=createOpportunityBriefService(transport,async()=>user);await expect(api.query(query)).rejects.toThrow();expect(transport).toHaveBeenCalledTimes(1);
 user=current;transport.mockImplementation(async()=>{abort.abort();return snapshot();});
 await expect(api.query(query,abort.signal)).rejects.toMatchObject({name:'AbortError'});
 transport.mockClear();await expect(api.query(query,abort.signal)).rejects.toThrow();expect(transport).not.toHaveBeenCalled();
});
