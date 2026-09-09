import type { YikeService } from "../../src/renderer/services/contracts";
import { ServiceError } from "../../src/renderer/services/contracts";
import {
  defaultResearchSettings,
  parseUsageQuote,
} from "../../src/renderer/domain/researchUsage";
import { configurationHash } from "../../src/renderer/domain/taskOperations";
import { taskDraft, TEST_USER } from "./fixtures";
import type { VisualState } from "./service";
import { configureResearchVisual } from "./r4-opportunity-research";
import { configureShortCoachVisual } from "./r4-short-coach";
import { configureCoverageVisual } from "./r4-search-coverage";
import { configureBriefVisual } from "./r4-opportunity-brief";
import { configureCoveragePlanVisual } from "./r4-coverage-plan";

export const R4_TEST_SCOPE = { id: "TEST-r4-space", version: 1 };
export function r4TaskDraft(mode: "once" | "monitor") {
  const draft = taskDraft(mode);
  return {
    ...draft,
    terms: draft.terms.slice(0, 4),
    exclusions: draft.exclusions.slice(0, 3),
    research: { ...defaultResearchSettings(), maxSoubei: 50 },
  };
}
/** Explicit opt-in visual adapter. No production import and no external side effect. */
export function configureR4Visual(service: YikeService, state: VisualState) {
  const session = service.session;
  service.session = async () => {
    const current = await session();
    return current.authenticated
      ? { ...current, accountScope: R4_TEST_SCOPE }
      : current;
  };
  service.researchUsage = {
    quote: async (request, draft) => {
      if (state === "loading") return new Promise(() => {});
      if (state === "error" || state === "empty")
        throw new ServiceError(
          "TEST_USAGE_UNAVAILABLE",
          "TEST 计量规则待确认；没有扣减搜贝。",
        );
      const current = await service.session();
      if (
        !current.authenticated ||
        current.userId !== TEST_USER ||
        request.userId !== current.userId ||
        request.accountScopeId !== current.accountScope?.id ||
        request.accountScopeVersion !== current.accountScope.version ||
        request.configurationHash !== (await configurationHash(draft))
      )
        throw new ServiceError("TEST_SCOPE_MISMATCH", "TEST 估算范围不匹配");
      return parseUsageQuote(
        {
          ...request,
          quoteId: crypto.randomUUID(),
          ruleVersion: "TEST-规则-v1",
          authorizationToken: "TEST-in-memory-only",
          estimatedSoubei: Math.min(12, request.maxSoubei),
          generatedAt: new Date(Date.now() - 100).toISOString(),
          expiresAt: new Date(Date.now() + 300000).toISOString(),
          basis: "TEST 隔离估算，仅验证页面交互，不是实际价格或用量。",
        },
        request,
      );
    },
  };
  configureResearchVisual(service, state);
  configureShortCoachVisual(service, state);
  configureCoverageVisual(service, state);
  configureCoveragePlanVisual(service, state);
  configureBriefVisual(service, state);
}
