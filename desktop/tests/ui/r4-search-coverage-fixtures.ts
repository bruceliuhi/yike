import type {
  CoverageSnapshot,
  SearchCoverageQuery,
} from "../../src/renderer/domain/searchCoverage";
import type { TaskRun } from "../../src/renderer/domain/models";

export const coverageRun: TaskRun = {
  id: "TEST-task",
  name: "TEST 搜索覆盖",
  mode: "monitor",
  status: "PARTIAL",
  platforms: ["xhs", "douyin", "bilibili", "web"],
  profileId: "TEST-profile",
  profileVersion: 1,
};
export const coverageQuery: SearchCoverageQuery = {
  contractVersion: 1,
  requestId: "TEST-request",
  taskId: coverageRun.id,
  profileId: "TEST-profile",
  profileVersion: 1,
  expectedScope: {
    userId: "TEST-user",
    accountScopeId: "TEST-account",
    scopeVersion: 1,
  },
};
export function coverageFixture(
  query: SearchCoverageQuery = coverageQuery,
): CoverageSnapshot {
  const counts = {
    requests: null,
    rawContents: null,
    duplicates: null,
    independentSources: null,
    newCandidates: null,
    confirmedOpportunities: null,
    pendingReviews: null,
  };
  const source = {
    id: "TEST-evidence",
    sourceId: "TEST-source",
    sourceVersionId: "TEST-source-v1",
    excerpt: "TEST 仅用于覆盖显示的合成公开内容。",
    url: "https://example.com/TEST-source",
  };
  const base = {
    scope: "TEST 本次配置内的公开内容",
    countingBasis: "TEST 同一运行窗口、每个平台方向独立去重；不跨平台求和",
    evidence: [source],
    exclusions: [],
    explanation: "TEST 返回的方向说明",
    counts,
    unchecked: ["TEST 后续内容未检查"],
    recovery: "NONE" as const,
  };
  return {
    contractVersion: 1,
    requestId: query.requestId,
    snapshotId: "TEST-snapshot",
    audience: "CUSTOMER",
    userId: query.expectedScope.userId,
    accountScopeId: query.expectedScope.accountScopeId,
    scopeVersion: query.expectedScope.scopeVersion,
    taskId: query.taskId,
    runId: "TEST-run",
    profileId: query.profileId,
    profileVersion: query.profileVersion,
    configurationRevision: 1,
    window: {
      id: "TEST-window",
      start: "2026-09-09T09:00:00+08:00",
      end: "2026-09-09T10:00:00+08:00",
      timezone: "Asia/Shanghai",
    },
    generatedAt: new Date().toISOString(),
    expiresAt: new Date(Date.now() + 60_000).toISOString(),
    deduplicationVersion: "TEST-dedup-v1",
    coverage: "PARTIAL",
    screening: "MIXED",
    usage: null,
    units: [
      {
        ...base,
        id: "TEST-xhs",
        platform: "xhs",
        direction: "TEST 买方询价",
        coverage: "PARTIAL",
        screening: "UNKNOWN",
        stopReason: "LOGIN_EXPIRED",
        explanation: "TEST 登录失效，本方向未完成。",
      },
      {
        ...base,
        id: "TEST-douyin",
        platform: "douyin",
        direction: "TEST 方案比较",
        coverage: "PARTIAL",
        screening: "PENDING_REVIEW",
        stopReason: "LIMIT_REACHED",
        recovery: "RESUMABLE_CONFIRMED",
        explanation: "TEST 研究到达上限，服务已确认暂停。",
      },
      {
        ...base,
        id: "TEST-bili",
        platform: "bilibili",
        direction: "TEST 替换服务商",
        coverage: "COMPLETE",
        screening: "ALL_EXCLUDED",
        stopReason: "NONE",
        unchecked: [],
        counts: { ...counts, independentSources: 1, pendingReviews: 0 },
        exclusions: [
          {
            id: "TEST-filter",
            phase: "FILTERING",
            reason: "TEST 不符合画像",
            ruleVersion: "TEST-r1",
            count: 1,
            overlapping: false,
            evidence: [source],
          },
        ],
      },
      {
        ...base,
        id: "TEST-web",
        platform: "web",
        direction: "TEST 公开需求",
        coverage: "COMPLETE",
        screening: "NO_QUALIFIED",
        stopReason: "NONE",
        unchecked: [],
        counts: { ...counts, independentSources: 0, pendingReviews: 0 },
      },
    ],
  };
}
