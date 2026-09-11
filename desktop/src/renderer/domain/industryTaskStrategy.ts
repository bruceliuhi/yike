import {z} from 'zod';
import {industrySourceTypes,industryTaskStrategySchema} from '../../shared/industryTaskStrategy';
import type {SuggestionReceipt} from '../../shared/searchSuggestions';
import type {TaskDraft} from './models';

// Drafts deliberately preserve unfinished edits; only the strict wire schema can be prepared.
export const industryStrategyDraftSchema=z.strictObject({
  profileId:z.string(),configuration:z.strictObject({
    version:z.literal('industry-task-strategy-v1'),sourceTypes:z.array(z.enum(industrySourceTypes)),
    intentSignals:z.array(z.string()),counterSignals:z.array(z.string()),
  }),
});
export type IndustryStrategyDraft=z.infer<typeof industryStrategyDraftSchema>;
export function industryStrategyError(draft:TaskDraft):string|null {
  if(draft.industryStrategy===undefined)return null;
  if(!draft.industryStrategy||draft.industryStrategy.profileId!==draft.profileId)
    return '行业策略沿用旧画像，请按当前画像核对确认或移除。';
  if(!industryTaskStrategySchema.safeParse(draft.industryStrategy.configuration).success)
    return '请选择至少一种内容方向；购买信号1–5条，反例最多5条，每条1–160字且不能重复。';
  return null;
}
export function adoptIndustryTaskStrategy(draft:TaskDraft,receipt:SuggestionReceipt):TaskDraft {
  const suggested=receipt.result?.strategy;
  if(draft.industryStrategy||!suggested||receipt.state!=='SUCCEEDED'||!receipt.profile_current||
    receipt.profile_version_id!==draft.profileId||receipt.draft_id!==draft.id)return draft;
  const parsed=industryTaskStrategySchema.safeParse({version:'industry-task-strategy-v1',
    sourceTypes:suggested.sourceTypes,intentSignals:suggested.intentSignals,counterSignals:suggested.counterSignals});
  if(!parsed.success)return draft;
  return {...draft,revision:draft.revision+1,savedAt:null,
    industryStrategy:{profileId:draft.profileId,configuration:parsed.data}};
}
