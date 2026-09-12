import {z} from 'zod';
import {DEFAULT_PUBLIC_SOURCE,publicSourceIdSchema,PUBLIC_SOURCES,type PublicSourceId} from './publicSources';

export const researchSourcePlanSchema=z.object({version:z.literal(1),
  sources:z.array(publicSourceIdSchema).min(2).max(3).refine(sources=>new Set(sources).size===sources.length),
}).strict();
export type ResearchSourcePlan=z.infer<typeof researchSourcePlanSchema>;
export const RESEARCH_PLAN_SCOPE='V2EX_INDEX_PLAN' as const;
export const RESEARCH_PLAN_LABEL='V2EX多板块 · 有界来源计划' as const;
export function researchIndexLabel(source:PublicSourceId){
  return source==='v2ex-outsourcing-authors-v1'?'V2EX项目外包':PUBLIC_SOURCES[source].label;
}
export function researchSources(source:PublicSourceId=DEFAULT_PUBLIC_SOURCE,plan?:ResearchSourcePlan):PublicSourceId[]{
  return plan ? [...researchSourcePlanSchema.parse(plan).sources] : [source];
}
/** Frozen, fair allotment; empty sources never transfer their unused quota. */
export function researchRecordAllotments(maxRecords:number,sources:readonly PublicSourceId[]){
  if(!Number.isInteger(maxRecords)||maxRecords<sources.length||maxRecords>100||!sources.length)return [];
  const share=Math.floor(maxRecords/sources.length),remainder=maxRecords%sources.length;
  return sources.map((sourceId,index)=>({sourceId,recordLimit:share+Number(index<remainder)}));
}
