import {expect,it} from 'vitest';
import {nativeProgressClaimSchema,nativeProgressBatchSchema,advanceNativeCursor} from '../src/shared/nativeSearchProgress';
import {executionOperationSchema} from '../src/shared/executionOperation';
import {validatedExecutionOperation} from '../src/main/executionServicePolicy';
const id=(n:number)=>`00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
export const nativeState={query:'设备',revision:0,base_batch_request_id:null,cursor:{page:1,consumed_ids:[],refresh_next:false}};
export const nativeClaim={schema_version:'native-search-progress-v1',adapter_version:'bili-search-items-v1',plan_id:id(80),queries:[nativeState]};
export function nativeDelta(query='设备'){return {query,revision:0,base_batch_request_id:null,before:nativeState.cursor,
 after:{page:1,consumed_ids:['1','2'],refresh_next:true},page_ids:['1','2','3'],processed_ids:['1','2'],has_more:true,comments_scope:'BOUNDED_SAMPLE'};}
it('strict schemas preserve a partial page and reject forged advancement',()=>{
 expect(nativeProgressClaimSchema.parse(nativeClaim)).toEqual(nativeClaim);
 const delta=nativeDelta();expect(advanceNativeCursor(delta.before,delta.page_ids,delta.processed_ids,true)).toEqual(delta.after);
 const batch={schema_version:nativeClaim.schema_version,adapter_version:nativeClaim.adapter_version,claim_request_id:id(1),queries:[delta]};
 expect(nativeProgressBatchSchema.parse(batch)).toEqual(batch);
 for(const bad of [{...delta,after:{...delta.after,page:2}},{...delta,processed_ids:['2']},{...delta,has_more:1},{...delta,revision:true},
   {...delta,page_ids:['1\n']},{...delta,revision:1,base_batch_request_id:'batch\n'}]){
  expect(nativeProgressBatchSchema.safeParse({...batch,queries:[bad]}).success).toBe(false);
 }
 expect(nativeProgressClaimSchema.safeParse({...nativeClaim,queries:[nativeState,nativeState]}).success).toBe(false);
});
it('Xiaohongshu progress keeps the platform search id across a resumed page',()=>{
 const cursor={page:2,search_id:'search-1',consumed_ids:[],refresh_next:false};
 const claim={schema_version:'native-search-progress-v1',adapter_version:'xhs-search-items-v1',plan_id:id(81),queries:[{query:'设备',revision:0,base_batch_request_id:null,cursor}]};
 expect(nativeProgressClaimSchema.parse(claim)).toEqual(claim);
 const delta={query:'设备',revision:0,base_batch_request_id:null,before:cursor,
  after:{page:2,search_id:'search-1',consumed_ids:['note-1'],refresh_next:true},page_ids:['note-1','note-2'],processed_ids:['note-1'],has_more:true,comments_scope:'BOUNDED_SAMPLE'};
 const batch={schema_version:claim.schema_version,adapter_version:claim.adapter_version,claim_request_id:id(2),queries:[delta]};
 expect(nativeProgressBatchSchema.parse(batch)).toEqual(batch);
 expect(nativeProgressBatchSchema.safeParse({...batch,queries:[{...delta,after:{...delta.after,search_id:'other'}}]}).success).toBe(false);
 expect(advanceNativeCursor(cursor,delta.page_ids,delta.processed_ids,true)).toEqual(delta.after);
});
it('CLAIM-only exact opt-in, mutually exclusive, old requests remain unchanged',()=>{
 const raw={schema_version:'execution-runtime-v1',request_id:id(1),operation:'CLAIM',device_id:id(2),credential_version:1,task_id:id(3),platform_run_id:id(4)};
 const legacy=executionOperationSchema.parse(raw);expect(legacy).not.toHaveProperty('native_progress_version');
 expect(executionOperationSchema.parse({...raw,native_progress_version:1})).toHaveProperty('native_progress_version',1);
 for(const extra of [{native_progress_version:true},{native_progress_version:null},{native_progress_version:1,public_sampling_version:1}])
  expect(executionOperationSchema.safeParse({...raw,...extra}).success).toBe(false);
 expect(executionOperationSchema.safeParse({...raw,operation:'RENEW',lease_id:id(5),execution_generation:1,native_progress_version:1}).success).toBe(false);
});
it('private capability negotiates one fixed query without renderer parameters',()=>{
 expect(validatedExecutionOperation({operation:'execution.support',progressVersion:1})?.path).toBe('/api/ui/execution-support?native_progress_version=1');
 expect(validatedExecutionOperation({operation:'execution.support',progressVersion:1,samplingVersion:1})).toBeNull();
 expect(validatedExecutionOperation({operation:'execution.support'})?.path).toBe('/api/ui/execution-support');
});
