import {z} from 'zod';
import {deviceUuidSchema} from './deviceRegistration';

const ids=(maximum:number)=>z.array(z.string().regex(/^[1-9][0-9]{0,19}$(?![\s\S])/)).max(maximum)
 .refine(items=>new Set(items).size===items.length);
const query=z.string().min(1).refine(s=>Array.from(s).length<=80&&s===s.trim()&&!/[,\p{Cc}\p{Cf}\p{Cs}\p{Zl}\p{Zp}]/u.test(s));
const base=z.string().regex(/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$(?![\s\S])/).nullable();
const meta={query,revision:z.number().int().min(0).max(2147483647),base_batch_request_id:base};
const validBase=(s:{revision:number;base_batch_request_id:string|null})=>(s.revision===0)===(s.base_batch_request_id===null);
export const nativeCursorSchema=z.object({page:z.number().int().min(1).max(1000),consumed_ids:ids(20),refresh_next:z.boolean()}).strict();
type Cursor=z.infer<typeof nativeCursorSchema>;
export function advanceNativeCursor(raw:Cursor,rawPage:string[],rawProcessed:string[],rawMore:boolean):Cursor {
 const before=nativeCursorSchema.parse(raw),page=ids(20).parse(rawPage),processed=ids(5).parse(rawProcessed),more=z.boolean().parse(rawMore);
 const available=page.filter(id=>before.refresh_next||!before.consumed_ids.includes(id)).slice(0,5);
 if(!page.length&&more||available.length&&!processed.length||processed.some((id,i)=>id!==available[i]))throw new Error('INVALID_NATIVE_PROGRESS');
 if(before.refresh_next)return {...before,refresh_next:false};
 const consumed=page.filter(id=>before.consumed_ids.includes(id)||processed.includes(id));
 return consumed.length===page.length?{page:more&&before.page<1000?before.page+1:1,consumed_ids:[],refresh_next:true}
  :{page:before.page,consumed_ids:consumed,refresh_next:true};
}
export const nativeQueryStateSchema=z.object({...meta,cursor:nativeCursorSchema}).strict().refine(validBase);
export const nativeQueryDeltaSchema=z.object({...meta,before:nativeCursorSchema,after:nativeCursorSchema,
 page_ids:ids(20),processed_ids:ids(5),has_more:z.boolean(),comments_scope:z.literal('BOUNDED_SAMPLE')}).strict().refine(validBase).refine(d=>{
 try{return JSON.stringify(advanceNativeCursor(d.before,d.page_ids,d.processed_ids,d.has_more))===JSON.stringify(d.after);}catch{return false;}
});
const versions={schema_version:z.literal('native-search-progress-v1'),adapter_version:z.literal('bili-search-items-v1')};
const uniqueQueries=(queries:{query:string}[])=>new Set(queries.map(q=>q.query)).size===queries.length;
export const nativeProgressClaimSchema=z.object({...versions,plan_id:deviceUuidSchema,
 queries:z.array(nativeQueryStateSchema).min(1).max(20).refine(uniqueQueries)}).strict();
export const nativeProgressBatchSchema=z.object({...versions,claim_request_id:deviceUuidSchema,
 queries:z.array(nativeQueryDeltaSchema).min(1).max(20).refine(uniqueQueries)}).strict();
export type NativeProgressClaim=z.infer<typeof nativeProgressClaimSchema>;
export type NativeProgressBatch=z.infer<typeof nativeProgressBatchSchema>;
export function matchesNativeDelta(delta:z.infer<typeof nativeQueryDeltaSchema>,state:z.infer<typeof nativeQueryStateSchema>,budget=5):boolean {
 return delta.query===state.query&&delta.revision===state.revision&&delta.base_batch_request_id===state.base_batch_request_id&&
  JSON.stringify(delta.before)===JSON.stringify(state.cursor)&&delta.processed_ids.length<=Math.min(5,budget);
}
export function matchesNativeBatch(batch:NativeProgressBatch,claim:NativeProgressClaim,requestId:string):boolean {
 return batch.claim_request_id===requestId&&batch.queries.every((delta,index)=>{
  const state=claim.queries[index];return !!state&&matchesNativeDelta(delta,state);
 });
}
