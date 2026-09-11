import {it,expect,vi} from 'vitest';
import {createStructuredFollowupService} from '../src/renderer/services/structuredFollowup';
import {readFollowupWorkspace} from '../src/renderer/domain/followup';
import {validatedOperation} from '../src/main/servicePolicy';
const id=(n:number)=>`00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
const session=()=>Promise.resolve({authenticated:true,userId:id(1),accountScope:{id:id(2),version:1}});
const binding={opportunityId:id(3),profileVersionId:id(4),action:'create' as const,targetId:'',targetRevision:0,requestId:id(5)};
const values={status:'CONTACTED' as const,note:'已经讨论需求',occurredAt:'2026-09-01T01:00:00.000Z',nextStep:'准备报价',nextFollowupAt:'2026-09-12T01:00:00.000Z',ownerId:id(1)};
const record={...values,id:id(6),opportunityId:id(3),profileVersionId:id(4),revision:1,title:'项目',createdAt:'2026-09-01T01:00:00.000Z',kind:'manual' as const,ownerName:'成员',state:'ACTIVE' as const,sample:false};
it('uses fixed strict routes and retains original bindings and complete fields',async()=>{
 const receipt={binding,status:'SUCCEEDED',confirmed:true,record},transport=vi.fn().mockResolvedValue(receipt),api=createStructuredFollowupService(transport,session);
 expect(await api.mutate({binding,values})).toEqual(receipt);
 expect(transport.mock.calls[0]).toEqual(['followup.mutate','/followup-workspace/mutate','POST',{binding,values}]);
 expect(await api.operation(binding)).toEqual(receipt);
 expect(validatedOperation({operation:'followup.mutate',payload:{binding,values}})?.path).toBe('/api/ui/followup-workspace/mutate');
 expect(validatedOperation({operation:'followup.replies',payload:{opportunityId:id(3)}})?.path).toBe(`/api/ui/followup-workspace/replies?opportunityId=${id(3)}`);
 expect(validatedOperation({operation:'followup.mutate',payload:{binding,values,tenantId:id(2)}})).toBeNull();
 expect(validatedOperation({operation:'followup.mutate',payload:{binding:{...binding,action:'void'},values}})).toBeNull();
});
it('preserves legacy history without inventing structured fields or allowing correction',()=>{
 const legacy={id:id(9),opportunityId:id(3),title:'旧项目',status:'CONTACTED',note:'历史备注',createdAt:'2026-09-01T00:00:00.000Z',kind:'manual'};
 const rows=readFollowupWorkspace({records:[record],members:[{id:id(1),name:'成员'}],legacyRecords:[legacy]}).records;
 expect(rows).toHaveLength(2);expect(rows[1]).toMatchObject({legacy:true,profileVersionId:'',revision:0,ownerName:'未提供'});
 expect(()=>readFollowupWorkspace({records:[record],members:[],legacyRecords:[{...legacy,id:record.id}]})).toThrow();
});
it('rejects mismatched results and late account changes without turning missing receipts into failures',async()=>{
 const transport=vi.fn().mockResolvedValue({binding:{...binding,requestId:id(8)},status:'SUCCEEDED',confirmed:true,record}),api=createStructuredFollowupService(transport,session);
 await expect(api.mutate({binding,values})).rejects.toThrow();
 transport.mockRejectedValue(new Error('not found'));await expect(api.operation(binding)).rejects.toThrow('not found');
 let current=await session();transport.mockImplementation(async()=>{current={...current,userId:id(8)};return {records:[record],members:[],legacyRecords:[]};});
 await expect(createStructuredFollowupService(transport,async()=>current).list()).rejects.toThrow();
});
