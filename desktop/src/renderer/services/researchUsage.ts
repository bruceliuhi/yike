import type { TaskDraft } from "../domain/models";
import type { UsageQuote, UsageQuoteRequest } from "../domain/researchUsage";

/** Read-only estimate. Quoting never reserves, settles, releases, or charges usage. */
export interface ResearchUsageService {
  quote(input: UsageQuoteRequest, draft: TaskDraft, signal?: AbortSignal): Promise<UsageQuote>;
}
