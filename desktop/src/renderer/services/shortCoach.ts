import type {
  CoachInput,
  CoachSuggestion,
  DraftSaveBinding,
  DraftSaveInput,
  DraftSaveReceipt,
} from "../domain/shortCoach";

/** Optional authenticated structured service. No adapter to the legacy string
 * generator: evidence anchors and request identity must come from the service.
 * This bounded first implementation consumes the opportunity's public excerpt;
 * internal material text is not sent. Authorized material citations require a
 * separately verified material snapshot before extending this input contract.
 */
export interface ShortCoachService {
  generate(input: CoachInput, signal?: AbortSignal): Promise<CoachSuggestion>;
}
/** The server must authorize the opportunity, compare source/profile/draft
 * versions and persist the original request id atomically with the saved draft.
 * FAILED means confirmed not saved; timeouts and missing receipts are UNKNOWN.
 * It must revalidate every field/hash; client input is not authorization.
 */
export interface ContactDraftService {
  save(input: DraftSaveInput): Promise<DraftSaveReceipt>;
  operation(binding: DraftSaveBinding): Promise<DraftSaveReceipt>;
  latest?(opportunityId: string, channel: "comment" | "dm", signal?: AbortSignal): Promise<DraftSaveReceipt | null>;
}
