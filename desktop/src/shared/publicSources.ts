import {z} from 'zod';

export const DEFAULT_PUBLIC_SOURCE='v2ex-latest-v1' as const;
export const publicSourceIdSchema=z.enum([DEFAULT_PUBLIC_SOURCE,'v2ex-qna-v1']);
export type PublicSourceId=z.infer<typeof publicSourceIdSchema>;
export const publicSourceIdsSchema=z.array(publicSourceIdSchema).min(1).max(2)
  .refine(ids=>new Set(ids).size===ids.length);
export const PUBLIC_SOURCES={
  'v2ex-latest-v1':{label:'V2EX最新主题',endpoint:'https://www.v2ex.com/api/topics/latest.json'},
  'v2ex-qna-v1':{label:'V2EX问与答',endpoint:'https://www.v2ex.com/api/topics/show.json?node_name=qna'},
} as const;
export function validPublicSourceCatalog(defaultId:PublicSourceId|undefined,ids:PublicSourceId[]|undefined){
  return ids===undefined || defaultId!==undefined && ids.includes(defaultId);
}
/** Callers validate capability schemas before using this membership check. */
export function allowsPublicSource(source:unknown,defaultId:PublicSourceId|undefined,ids?:PublicSourceId[]){
  const parsed=publicSourceIdSchema.safeParse(source);
  return parsed.success && defaultId!==undefined && (ids??[defaultId]).includes(parsed.data);
}
export function publicSourceScope(source:PublicSourceId=DEFAULT_PUBLIC_SOURCE){
  return `${PUBLIC_SOURCES[source].label} · 近期主题有界抽样，不覆盖历史/全站/评论`;
}
