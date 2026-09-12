import {z} from 'zod';
import {publicSourceIdSchema,publicSourceScope,type PublicSourceId} from './publicSources';

export const DYNAMIC_RESEARCH_SOURCE='public-web-agent-v1' as const;
export const DYNAMIC_RESEARCH_LABEL='公开网页自主研究' as const;
export const researchSelectionSchema=z.union([publicSourceIdSchema,z.literal(DYNAMIC_RESEARCH_SOURCE)]);
export type ResearchSelection=z.infer<typeof researchSelectionSchema>;
export const dynamicScopeSchema=z.object({version:z.literal(1),maxAgeDays:z.number().int().min(1).max(365),
  timezone:z.string().min(1).max(128).refine(value=>{
    if(/[\p{Cc}\p{Cf}\p{Cs}\p{Zl}\p{Zp}]/u.test(value))return false;
    try{new Intl.DateTimeFormat('en',{timeZone:value}).format(0);return true;}catch{return false;}
  })}).strict();
export function researchSelectionScope(source:ResearchSelection= 'v2ex-latest-v1'){
  return source===DYNAMIC_RESEARCH_SOURCE?DYNAMIC_RESEARCH_LABEL:publicSourceScope(source as PublicSourceId);
}
export function dynamicLimitsValid(value:{sources:number;minutes:number;modelCalls:number}){
  return Number.isInteger(value.sources)&&value.sources>=2&&value.sources<=100&&
    Number.isInteger(value.minutes)&&value.minutes>=1&&value.minutes<=30&&
    Number.isInteger(value.modelCalls)&&value.modelCalls>=2&&value.modelCalls<=20;
}
