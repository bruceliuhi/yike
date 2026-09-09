import { useApp } from "../../app/context";
import { useResource } from "../../app/hooks";
import { boundedRequest } from "../../app/boundedRequest";
import { readReplies } from "../../domain/followup";
import { isSample } from "../Opportunities";

/** An absent target explicitly requests unmatched replies, never a failed lookup. */
export function useRelatedReplies(opportunityId?: string) {
  const { service, session } = useApp();
  const identity = [service, service.followup, session.authenticated, session.userId,
    session.accountScope?.id, session.accountScope?.version, opportunityId];
  const target = useResource(async (signal) => {
    if (!session.authenticated || !opportunityId) return undefined;
    if (opportunityId === "sample")
      throw new Error("公开样例不可关联客户回复。");
    const opportunity = await boundedRequest(
      () => service.opportunity(opportunityId),
      { signal, timeoutMessage: "关联商机读取超时，请重试。" },
    );
    if (signal?.aborted) return undefined;
    if (!opportunity || opportunity.id !== opportunityId)
      throw new Error("商机与请求不匹配，请重新选择后核对。");
    if (isSample(opportunity))
      throw new Error("公开样例不可关联客户回复。");
    return opportunity;
  }, identity);
  const replies = useResource(async (signal) => {
    if (!session.authenticated || !service.followup ||
      (opportunityId && !target.data)) return undefined;
    return readReplies(
      await boundedRequest(
        () => service.followup!.replies(opportunityId),
        { signal, timeoutMessage: "回复读取超时，请重试。" },
      ), opportunityId,
    );
  }, [...identity, target.data]);
  return { target, replies };
}
