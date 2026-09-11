import type {TaskDraft,Term} from './models';
import {platformQueriesSchema,type StrategyConfiguration} from '../../shared/researchStrategies';

export const queryPlatforms = {xhs:'XIAOHONGSHU',douyin:'DOUYIN',bilibili:'BILIBILI',zhihu:'ZHIHU'} as const;
export type QueryPlatform = keyof typeof queryPlatforms;
export type PlatformTerms = Partial<Record<QueryPlatform,Term[]>>;

export function platformQueries(draft:TaskDraft): StrategyConfiguration['platformQueries'] {
  if(draft.platformTerms===undefined) return undefined;
  const keys=Object.keys(draft.platformTerms);
  if(keys.some(key=>!(key in queryPlatforms) || !draft.platforms.includes(key as QueryPlatform)) ||
    draft.source!=='search' || draft.links.trim() || draft.research!==undefined) throw new Error('平台搜索词仅适用于已选择平台的普通关键词采集。');
  const value=platformQueriesSchema.parse({version:'platform-queries-v1',items:keys.map(key=>({
    platform:queryPlatforms[key as QueryPlatform],keywords:draft.platformTerms![key as QueryPlatform]!.map(term=>term.value),
  }))});
  const fold=(word:string)=>word.trim().replace(/\s+/gu,' ').toLowerCase();
  if(value.items.some(item=>item.keywords.some(word=>draft.exclusions.some(exclusion=>fold(word).includes(fold(exclusion.value))))))
    throw new Error('排除词与平台搜索词冲突。');
  return value;
}

export function platformTermsError(draft:TaskDraft): string | null {
  try {platformQueries(draft);return null;}
  catch {return '请检查平台词：仅限已选平台的普通关键词采集，每个平台1–20个不重复词，不得与排除词冲突；不使用时恢复通用词。';}
}
