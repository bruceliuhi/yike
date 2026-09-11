import type { TaskDraft } from "../domain/models";
import {parseUsageQuote, type UsageQuote, type UsageQuoteRequest} from "../domain/researchUsage";
import {researchUsageRequestSchema, researchUsageResponseSchema} from '../../shared/researchUsage';
import type {ApiOperation} from '../../shared/contracts';
import {ServiceError} from './contracts';

/** Read-only estimate. Quoting never reserves, settles, releases, or charges usage. */
export interface ResearchUsageService {
  readonly requiresConfirmedStrategy?: true;
  quote(input: UsageQuoteRequest, draft: TaskDraft, signal?: AbortSignal): Promise<UsageQuote>;
}

type Transport = (operation: ApiOperation, path: string, method: string, payload: unknown, signal?: AbortSignal) => Promise<unknown>;
export function createResearchUsageService(request: Transport): ResearchUsageService {
  return {requiresConfirmedStrategy: true, async quote(input, _draft, signal) {
    const parsed = researchUsageRequestSchema.safeParse(input);
    if (!parsed.success) throw new ServiceError('invalid_request', '请先确认当前研究策略，再估算用量。', 422);
    const raw = await request('researchUsage.quote', '/research-usage/quote', 'POST', parsed.data, signal);
    const result = researchUsageResponseSchema.safeParse(raw);
    if (!result.success) throw new ServiceError('INVALID_SERVICE_RESPONSE', '用量估算缺少确认版本或计量依据，请重新核对。');
    return parseUsageQuote(result.data, parsed.data);
  }};
}
