import {z} from 'zod';
import {deviceUuidSchema} from './deviceRegistration';

const ids=(maximum:number,pattern=/^[1-9][0-9]{0,19}$(?![\s\S])/)=>z.array(z.string().regex(pattern)).max(maximum)
 .refine(items=>new Set(items).size===items.length);
const xhsIds=(maximum:number)=>ids(maximum,/^[A-Za-z0-9_-]{1,64}$(?![\s\S])/);
const query=z.string().min(1).refine(s=>Array.from(s).length<=80&&s===s.trim()&&!/[,\p{Cc}\p{Cf}\p{Cs}\p{Zl}\p{Zp}]/u.test(s));
const base=z.string().regex(/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$(?![\s\S])/).nullable();
const meta={query,revision:z.number().int().min(0).max(2147483647),base_batch_request_id:base};
const validBase=(s:{revision:number;base_batch_request_id:string|null})=>(s.revision===0)===(s.base_batch_request_id===null);
const biliCursorSchema=z.object({page:z.number().int().min(1).max(1000),consumed_ids:ids(20),refresh_next:z.boolean()}).strict();
const xhsCursorSchema=z.object({page:z.number().int().min(1).max(1000),search_id:z.string().regex(/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$(?![\s\S])/),consumed_ids:xhsIds(20),refresh_next:z.boolean()}).strict();
export const nativeCursorSchema=z.union([biliCursorSchema,xhsCursorSchema]);
type Cursor=z.infer<typeof nativeCursorSchema>;
const isXhsCursor=(cursor:Cursor):cursor is z.infer<typeof xhsCursorSchema>=>'search_id' in cursor;
export function advanceNativeCursor(raw:Cursor,rawPage:string[],rawProcessed:string[],rawMore:boolean):Cursor {
 const before=nativeCursorSchema.parse(raw),pageIds=isXhsCursor(before)?xhsIds(20).parse(rawPage):ids(20).parse(rawPage),processed=isXhsCursor(before)?xhsIds(5).parse(rawProcessed):ids(5).parse(rawProcessed),more=z.boolean().parse(rawMore);
 const available=pageIds.filter(id=>before.refresh_next||!before.consumed_ids.includes(id)).slice(0,5);
 if(!pageIds.length&&more||available.length&&!processed.length||processed.some((id,i)=>id!==available[i]))throw new Error('INVALID_NATIVE_PROGRESS');
 if(before.refresh_next)return {...before,refresh_next:false};
 const consumed=pageIds.filter(id=>before.consumed_ids.includes(id)||processed.includes(id));
 const next=consumed.length===pageIds.length
  ? {page:more&&before.page<1000?before.page+1:1,consumed_ids:[],refresh_next:true}
  : {page:before.page,consumed_ids:consumed,refresh_next:true};
 return isXhsCursor(before)?{page:next.page,search_id:before.search_id,consumed_ids:next.consumed_ids,refresh_next:next.refresh_next}:next;
}
export const nativeQueryStateSchema=z.object({...meta,cursor:nativeCursorSchema}).strict().refine(validBase);
export const nativeQueryDeltaSchema=z.object({...meta,before:nativeCursorSchema,after:nativeCursorSchema,
 page_ids:z.union([ids(20),xhsIds(20)]),processed_ids:z.union([ids(5),xhsIds(5)]),has_more:z.boolean(),comments_scope:z.literal('BOUNDED_SAMPLE')}).strict().refine(validBase).refine(d=>{
 try{return JSON.stringify(advanceNativeCursor(d.before,d.page_ids,d.processed_ids,d.has_more))===JSON.stringify(d.after);}catch{return false;}
});
const versions={schema_version:z.literal('native-search-progress-v1'),adapter_version:z.union([z.literal('bili-search-items-v1'),z.literal('xhs-search-items-v1')])};
const uniqueQueries=(queries:{query:string}[])=>new Set(queries.map(q=>q.query)).size===queries.length;
export const nativeProgressClaimSchema=z.object({...versions,plan_id:deviceUuidSchema,
 queries:z.array(nativeQueryStateSchema).min(1).max(20).refine(uniqueQueries)}).strict().refine(value=>value.queries.every(item=>isXhsCursor(item.cursor)===(value.adapter_version==='xhs-search-items-v1')));
export const nativeProgressBatchSchema=z.object({...versions,claim_request_id:deviceUuidSchema,
 queries:z.array(nativeQueryDeltaSchema).min(1).max(20).refine(uniqueQueries)}).strict().refine(value=>value.queries.every(item=>isXhsCursor(item.before)===(value.adapter_version==='xhs-search-items-v1')));
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
