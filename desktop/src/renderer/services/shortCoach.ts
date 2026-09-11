import type {
  CoachInput,
  CoachSuggestion,
  DraftSaveBinding,
  DraftSaveInput,
  DraftSaveReceipt,
} from "../domain/shortCoach";
import type {CoachPreview,CoachDisclosure} from '../../shared/shortCoach';
export type {CoachPreview,CoachDisclosure} from '../../shared/shortCoach';

/** Optional authenticated structured service. No adapter to the legacy string
 * generator: evidence anchors and request identity must come from the service.
 * Selected material excerpts require server qualification and explicit model
 * disclosure. Other library text is not sent; output references bind only the
 * excerpts actually used, and must be requalified before adoption.
 */
export interface ShortCoachService {
  preview?(input: CoachInput, signal?: AbortSignal): Promise<CoachPreview>;
  generate(input: CoachInput & {disclosure?:CoachDisclosure}, signal?: AbortSignal): Promise<CoachSuggestion>;
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
