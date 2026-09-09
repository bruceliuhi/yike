import type {
  ResearchBinding,
  ResearchCollection,
  ResearchTimeline,
  SimilarResearchPlan,
} from "../domain/opportunityResearch";
import {
  hasResearchScope,
  parseResearchCollection,
} from "../domain/opportunityResearch";
import type { Session } from "../domain/models";
/** Optional, authenticated R4 research reads. No production adapter is implied.
 * The server derives tenant identity and verifies profile/source versions.
 * These methods never import, classify, execute research, send, or charge.
 * Similar suggestions are a preview; applying creates only a local draft. */
export interface OpportunityResearchService {
  list(signal?: AbortSignal): Promise<ResearchCollection>;
  timeline(
    binding: ResearchBinding,
    signal?: AbortSignal,
  ): Promise<ResearchTimeline>;
  similar(
    binding: ResearchBinding,
    requestId: string,
    signal?: AbortSignal,
  ): Promise<SimilarResearchPlan>;
}
export async function readResearchRecord(
  service: OpportunityResearchService,
  session: Session,
  id: string,
  signal?: AbortSignal,
) {
  if (!session.authenticated || !session.userId || id === "sample")
    throw new Error("请登录后读取客户研究记录。");
  if (!hasResearchScope(session.accountScope))
    throw new Error("当前账户空间尚未核验，研究服务暂不可用。");
  const snapshot = parseResearchCollection(
    await service.list(signal),
    session.userId,
    Date.now(),
    session.accountScope,
  );
  const row = snapshot.records.find((item) => item.opportunity.id === id);
  if (!row) throw new Error("当前授权研究集合中未找到该记录，请返回列表刷新。");
  return row;
}
