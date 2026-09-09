import type {
  BriefQuery,
  OpportunityBriefSnapshot,
} from "../domain/opportunityBrief";

/** Authenticated read-only snapshot. Expected scope is an equality guard, never
 * an account selector. No generation, collection, marking-contacted or sending.
 * Targets are existing customer opportunities; followup opens that opportunity's
 * records, not an invented record-specific route. */
export interface OpportunityBriefService {
  query(
    request: BriefQuery,
    signal?: AbortSignal,
  ): Promise<OpportunityBriefSnapshot>;
}
