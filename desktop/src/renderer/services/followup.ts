import type {
  FollowupSnapshot,
  LinkedReply,
  FollowupMutation,
  FollowupBinding,
  FollowupReceipt,
} from "../domain/followup";
import { ServiceError } from "./contracts";
/** Authenticated structured service; older facades may retain the manual fallback. */
export interface FollowupService {
  list(): Promise<FollowupSnapshot>;
  replies(opportunityId?: string): Promise<LinkedReply[]>;
  mutate(input: FollowupMutation): Promise<FollowupReceipt>;
  operation(binding: FollowupBinding): Promise<FollowupReceipt>;
}
export function requireFollowup(value?: FollowupService) {
  if (!value)
    throw new ServiceError(
      "CAPABILITY_UNAVAILABLE",
      "结构化跟进与回复服务尚未接通。",
      501,
    );
  return value;
}
