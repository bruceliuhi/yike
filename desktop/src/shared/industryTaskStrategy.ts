import {z} from 'zod';

export const industrySourceTypes=['SOCIAL_POST','COMMENT','PROCUREMENT','COMPANY_UPDATE','INDUSTRY_SITE'] as const;
export const industrySourceLabels:Record<typeof industrySourceTypes[number],string>={
  SOCIAL_POST:'需求主帖',COMMENT:'讨论评论',PROCUREMENT:'采购公告',COMPANY_UPDATE:'企业公开动态',INDUSTRY_SITE:'行业网站',
};
const signal=z.string().refine(value=>value.trim().length>0&&Array.from(value).length<=160&&
  !/[\p{Cc}\p{Cf}\p{Cs}\p{Zl}\p{Zp}]/u.test(value));
const signals=(minimum:number)=>z.array(signal).min(minimum).max(5).refine(values=>
  new Set(values.map(value=>value.trim().replace(/\s+/gu,' ').toLowerCase())).size===values.length);
export const industryTaskStrategySchema=z.strictObject({
  version:z.literal('industry-task-strategy-v1'),
  sourceTypes:z.array(z.enum(industrySourceTypes)).min(1).max(5).refine(values=>new Set(values).size===values.length),
  intentSignals:signals(1),counterSignals:signals(0),
});
export type IndustryTaskStrategy=z.infer<typeof industryTaskStrategySchema>;
