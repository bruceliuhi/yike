import type { YikeService } from "../../src/renderer/services/contracts";
import { ServiceError } from "../../src/renderer/services/contracts";
import type { OpportunityBriefSnapshot } from "../../src/renderer/domain/opportunityBrief";
import {
  followups,
  monitor,
  opportunity,
  profile,
  TEST_USER,
} from "./fixtures";
import type { VisualState } from "./service";

/** Pure TEST snapshot. No network, generated buyer, outgoing message or write. */
export function configureBriefVisual(service: YikeService, state: VisualState) {
  service.opportunityBrief = {
    query: async (request) => {
      const session = await service.session();
      if (
        !session.authenticated ||
        session.userId !== TEST_USER ||
        !session.accountScope ||
        request.userId !== session.userId ||
        request.accountScopeId !== session.accountScope.id ||
        request.scopeVersion !== session.accountScope.version ||
        request.profileId !== profile.id ||
        request.profileVersion !== profile.version
      )
        throw new ServiceError(
          "FORBIDDEN",
          "TEST 简报仅支持当前隔离账户与固定测试画像。",
          403,
        );
      if (state === "error")
        throw new ServiceError(
          "TEST_READ_FAILED",
          "TEST 简报读取失败，请重试；没有真实客户结果。",
        );
      if (state === "loading")
        return new Promise<OpportunityBriefSnapshot>(() => {});
      const now = new Date().toISOString();
      const basis = {
        recordId: opportunity.id,
        version: opportunity.sourceEvidenceVersion!,
        excerpt: "TEST 本段仅用于简报证据布局，不代表真实客户或回复。",
        verifiedAt: now,
      };
      const item = {
        id: "TEST-brief-contact",
        opportunityId: opportunity.id,
        opportunityVersion: opportunity.sourceEvidenceVersion!,
        title: opportunity.title,
        reason: "TEST 已核验需求的布局示意；没有实际联系人或外发。",
        profileId: profile.id,
        profileVersion: profile.version,
        sample: false as const,
        validity: "VALID" as const,
      };
      return {
        ...request,
        snapshotId: "TEST-opportunity-brief",
        audience: "CUSTOMER",
        generatedAt: now,
        expiresAt: new Date(Date.now() + 900_000).toISOString(),
        coverage: state === "empty" ? "NOT_CHECKED" : "PARTIAL",
        lastCompletedCheckAt: state === "empty" ? null : now,
        checkedScope: state === "empty" ? [] : ["TEST 本机内存中的公开方向"],
        uncheckedScope: ["TEST 其余平台未进行真实搜索"],
        runs:
          state === "empty"
            ? []
            : [
                {
                  taskId: monitor.id,
                  runId: "TEST-brief-run",
                  windowId: "TEST-brief-window",
                },
              ],
        groups:
          state === "empty"
            ? {
                contact: { items: [], total: 0 },
                changes: { items: [], total: 0 },
                followup: { items: [], total: 0 },
              }
            : {
                contact: {
                  total: 1,
                  items: [
                    { ...item, basis: { ...basis, kind: "REVIEWED_DEMAND" } },
                  ],
                },
                changes: {
                  total: 1,
                  items: [
                    {
                      ...item,
                      id: "TEST-brief-change",
                      title: "TEST 同来源版本变化示意",
                      reason:
                        "TEST 合成变化用于查看原文入口，不声称采购或截止实际改变。",
                      basis: { ...basis, kind: "VERIFIED_CHANGE" },
                    },
                  ],
                },
                followup: {
                  total: 1,
                  items: [
                    {
                      ...item,
                      id: "TEST-brief-followup",
                      title: "TEST 待核对资料事项",
                      reason:
                        "TEST 已有人工作业记录，查看该商机跟进；没有真实联系。",
                      basis: {
                        ...basis,
                        recordId: followups[0].id,
                        excerpt: followups[0].note,
                        kind: "MANUAL_FOLLOWUP",
                      },
                    },
                  ],
                },
              },
      };
    },
  };
}
