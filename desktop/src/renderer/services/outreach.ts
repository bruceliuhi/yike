import type { ContactDraft } from "../domain/models";
import type { OutreachQueue, OutreachQueuePage, SendReceipt, SendRequestBinding } from "../domain/outreach";
import { ServiceError } from "./contracts";

/** Optional authenticated adapter. No production endpoint or fixture is implied. */
export interface OutreachService {
  /** Complete queue snapshot, scoped by the server to the authenticated tenant. */
  queue(queue: OutreachQueue): Promise<OutreachQueuePage>;
  /** Persist this ID before submission; retries of an ID must be idempotent. */
  send(draft: ContactDraft, request: { requestId: string; confirmationToken: string }): Promise<SendReceipt>;
  /** Read-only lookup. Missing, unavailable or UNKNOWN never proves failure. */
  reconcile(request: SendRequestBinding): Promise<SendReceipt>;
}
export function requireOutreach(value?: OutreachService): OutreachService {
  if (!value) throw new ServiceError("CAPABILITY_UNAVAILABLE", "触达队列与发送结果核对服务尚未接通。", 501);
  return value;
}
