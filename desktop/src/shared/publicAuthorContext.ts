import {z} from 'zod';

export const authorUpdateBodySchema=z.string().refine(value=>Array.from(value).length<=20000 &&
 !/^[\p{White_Space}\u001c-\u001f]*$/u.test(value) && !/[\uD800-\uDFFF]/u.test(value) &&
 !/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]/.test(value));
const id=z.string().regex(/^[1-9][0-9]{0,15}$/).refine(value=>Number.isSafeInteger(Number(value)));
const time=z.string().regex(/^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$/).refine(value=>{
 const parsed=new Date(value);return !value.startsWith('0000')&&Number.isFinite(parsed.getTime())&&parsed.toISOString().replace('.000Z','Z')===value;
});
export const sourceContextSchema=z.object({schema_version:z.literal('v2ex-author-context-v1'),
 replies_expected:z.number().int().min(0).max(2147483647).nullable(),replies_read:z.number().int().min(0).max(100),
 replies_complete:z.boolean(),supplements_read:z.literal(false),
 author_replies:z.array(z.object({id,body:authorUpdateBodySchema,published_at:time}).strict()).max(100),
}).strict().refine(c=>c.replies_complete===(c.replies_expected!==null&&c.replies_expected===c.replies_read)&&
 c.author_replies.length<=c.replies_read&&new Set(c.author_replies.map(r=>r.id)).size===c.author_replies.length&&
 c.author_replies.reduce((n,r)=>n+Array.from(r.body).length,0)<=20000);
export type SourceContext=z.infer<typeof sourceContextSchema>;
export function validAuthorTimes(context:SourceContext|undefined,published:string|null,observed:string){
 return !context||context.author_replies.every(r=>Date.parse(r.published_at)<=Date.parse(observed)&&
  (published===null||Date.parse(r.published_at)>=Date.parse(published)));
}
