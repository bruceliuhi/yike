import type {
  BriefQuery,
  OpportunityBriefSnapshot,
} from "../../src/renderer/domain/opportunityBrief";
import type { Profile } from "../../src/renderer/domain/models";
export const briefProfile: Profile = {
  id: "TEST-profile",
  version: 1,
  status: "CONFIRMED",
  description: "TEST 业务",
  fields: {
    service: "TEST 行业服务",
    customer: "TEST 客户",
    regions: "TEST 地区",
    preference: "",
    exclusions: "",
  },
};
export const briefQuery: BriefQuery = {
  contractVersion: 1,
  requestId: "TEST-request",
  userId: "TEST-user",
  accountScopeId: "TEST-account",
  scopeVersion: 1,
  profileId: briefProfile.id,
  profileVersion: 1,
  businessDate: "2026-09-09",
  timezone: "Asia/Shanghai",
};
export function briefFixture(
  query: BriefQuery = briefQuery,
): OpportunityBriefSnapshot {
  const now = new Date().toISOString();
  const item = {
    id: "TEST-item",
    opportunityId: "TEST-opportunity",
    opportunityVersion: "TEST-o-v1",
    title: "TEST 客户机会",
    reason: "TEST 有原文依据且经过人工核对",
    profileId: query.profileId,
    profileVersion: query.profileVersion,
    sample: false as const,
    validity: "VALID" as const,
    basis: {
      recordId: "TEST-record",
      version: "TEST-r1",
      excerpt: "TEST 本段为隔离测试的已核验内容。",
      verifiedAt: now,
    },
  };
  return {
    ...query,
    snapshotId: "TEST-brief",
    audience: "CUSTOMER",
    generatedAt: now,
    expiresAt: new Date(Date.now() + 60_000).toISOString(),
    coverage: "COMPLETE",
    lastCompletedCheckAt: now,
    checkedScope: ["TEST 已完成的搜索方向"],
    uncheckedScope: [],
    runs: [{ taskId: "TEST-task", runId: "TEST-run", windowId: "TEST-window" }],
    groups: {
      contact: {
        total: 1,
        items: [{ ...item, basis: { ...item.basis, kind: "REVIEWED_DEMAND" } }],
      },
      changes: {
        total: 1,
        items: [
          {
            ...item,
            id: "TEST-change",
            title: "TEST 重要变化",
            basis: { ...item.basis, kind: "VERIFIED_CHANGE" },
          },
        ],
      },
      followup: {
        total: 1,
        items: [
          {
            ...item,
            id: "TEST-followup",
            title: "TEST 待跟进",
            basis: { ...item.basis, kind: "MANUAL_FOLLOWUP" },
          },
        ],
      },
    },
  };
}
