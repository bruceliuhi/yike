import type { YikeService } from "../../src/renderer/services/contracts";
import { ServiceError } from "../../src/renderer/services/contracts";
import type { CoverageSnapshot } from "../../src/renderer/domain/searchCoverage";
import { monitor, opportunity, profile, TEST_USER } from "./fixtures";
import type { VisualState } from "./service";

/** Pure TEST data only. No external IO, budget operation, task start or production import. */
export function configureCoverageVisual(
  service: YikeService,
  state: VisualState,
) {
  service.searchCoverage = {
    query: async (request) => {
      const session = await service.session();
      if (
        !session.authenticated ||
        session.userId !== TEST_USER ||
        !session.accountScope ||
        request.expectedScope.userId !== session.userId ||
        request.expectedScope.accountScopeId !== session.accountScope.id ||
        request.expectedScope.scopeVersion !== session.accountScope.version ||
        request.taskId !== monitor.id ||
        request.profileId !== profile.id ||
        request.profileVersion !== profile.version
      )
        throw new ServiceError(
          "FORBIDDEN",
          "TEST 覆盖仅接受本机隔离账户和固定测试任务。",
          403,
        );
      if (state === "error")
        throw new ServiceError(
          "TEST_READ_FAILED",
          "TEST 覆盖读取失败，可重试；没有执行真实搜索。",
        );
      if (state === "loading") return new Promise<CoverageSnapshot>(() => {});
      const now = Date.now();
      const counts = {
        requests: null,
        rawContents: null,
        duplicates: null,
        independentSources: null,
        newCandidates: null,
        confirmedOpportunities: null,
        pendingReviews: null,
      };
      const evidence = {
        id: "TEST-coverage-evidence",
        sourceId: opportunity.id,
        sourceVersionId: opportunity.sourceEvidenceVersion!,
        url: opportunity.url,
        excerpt: "TEST 本段仅用于覆盖明细，不是真实运行或客户结论。",
      };
      const base = {
        scope: "TEST 固定画像下的公开内容范围",
        explanation: "TEST 本机内存覆盖示意，未执行真实平台请求。",
        unchecked: ["TEST 后续方向尚未检查"],
        countingBasis: "TEST 当前窗口内按平台和方向独立去重，不跨平台相加",
        counts,
        evidence: [evidence],
        exclusions: [],
        recovery: "NONE" as const,
      };
      return {
        contractVersion: 1,
        requestId: request.requestId,
        snapshotId: "TEST-coverage-snapshot",
        audience: "CUSTOMER",
        userId: session.userId,
        accountScopeId: session.accountScope.id,
        scopeVersion: session.accountScope.version,
        taskId: monitor.id,
        runId: "TEST-coverage-run",
        profileId: profile.id,
        profileVersion: profile.version,
        configurationRevision: 1,
        window: {
          id: "TEST-coverage-window",
          start: new Date(now - 3600_000).toISOString(),
          end: new Date(now).toISOString(),
          timezone: "Asia/Shanghai",
        },
        generatedAt: new Date(now).toISOString(),
        expiresAt: new Date(now + 900_000).toISOString(),
        deduplicationVersion: "TEST-dedup-v1",
        coverage: state === "empty" ? "NOT_STARTED" : "PARTIAL",
        screening: state === "empty" ? "UNKNOWN" : "MIXED",
        usage: {
          unit: "SOUBEI",
          ruleVersion: "TEST-rule-not-price",
          budgetRevision: 1,
          estimated: null,
          maximum: 30,
          actual: null,
          settlement: "UNKNOWN",
        },
        units:
          state === "empty"
            ? []
            : [
                {
                  ...base,
                  id: "TEST-coverage-xhs",
                  platform: "xhs",
                  direction: "TEST 买方询价表达",
                  coverage: "PARTIAL",
                  screening: "UNKNOWN",
                  stopReason: "LOGIN_EXPIRED",
                  explanation: "TEST 登录失效，本次未取得可判断的搜索结果。",
                },
                {
                  ...base,
                  id: "TEST-coverage-douyin",
                  platform: "douyin",
                  direction: "TEST 方案比较表达",
                  coverage: "PARTIAL",
                  screening: "PENDING_REVIEW",
                  stopReason: "LIMIT_REACHED",
                  recovery: "RESUMABLE_CONFIRMED",
                  explanation:
                    "TEST 用量停止示意，内存状态已确认暂停；没有实际消耗或追加。",
                },
                {
                  ...base,
                  id: "TEST-coverage-bilibili",
                  platform: "bilibili",
                  direction: "TEST 替换服务商表达",
                  coverage: "COMPLETE",
                  screening: "ALL_EXCLUDED",
                  stopReason: "NONE",
                  unchecked: [],
                  counts: {
                    ...counts,
                    independentSources: 1,
                    pendingReviews: 0,
                  },
                  exclusions: [
                    {
                      id: "TEST-excluded",
                      phase: "FILTERING",
                      reason: "TEST 不符合目标画像",
                      count: 1,
                      ruleVersion: "TEST-review-v1",
                      overlapping: false,
                      evidence: [evidence],
                    },
                  ],
                },
                {
                  ...base,
                  id: "TEST-coverage-web",
                  platform: "web",
                  direction: "TEST 公开需求表达",
                  coverage: "COMPLETE",
                  screening: "NO_QUALIFIED",
                  stopReason: "NONE",
                  unchecked: [],
                  counts: {
                    ...counts,
                    independentSources: 0,
                    pendingReviews: 0,
                  },
                  explanation:
                    "TEST 仅此已检查方向无合格机会，不是全平台结论。",
                },
              ],
      };
    },
  };
}
