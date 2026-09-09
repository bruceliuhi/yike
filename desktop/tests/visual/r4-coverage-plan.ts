import type { YikeService } from "../../src/renderer/services/contracts";
import { ServiceError } from "../../src/renderer/services/contracts";
import {
  coveragePlan,
  parseCoverageSnapshot,
} from "../../src/renderer/domain/searchCoverage";
import {
  coverageConfirmationHash,
  readCoveragePreview,
  type CoverageAdjustmentReceipt,
  type CoveragePlanPreview,
} from "../../src/renderer/domain/coveragePlan";
import { defaultResearchSettings } from "../../src/renderer/domain/researchUsage";
import { taskDraft, TEST_USER } from "./fixtures";
import type { VisualState } from "./service";

/** Pure TEST state. The first adjustment reports UNKNOWN; its original query
 * confirms the in-memory change with notResumed=true. No external IO or billing. */
export function configureCoveragePlanVisual(
  service: YikeService,
  state: VisualState,
  options: { terminal?: boolean } = {},
): void {
  const records = new Map<string, CoverageAdjustmentReceipt>();
  const budgets = new Map<string, { revision: number; maximum: number }>();
  const fail = (message: string): never => {
    throw new ServiceError("VISUAL_SCOPE_REJECTED", "TEST " + message, 400);
  };
  const identity = async () => {
    const session = await service.session();
    if (
      !session.authenticated ||
      session.userId !== TEST_USER ||
      !session.accountScope
    )
      return fail("只接受本实例客户空间");
    return {
      session,
      key: JSON.stringify([session.userId, session.accountScope]),
    };
  };
  const originalQuery = service.searchCoverage?.query;
  if (originalQuery)
    service.searchCoverage = {
      query: async (input, signal) => {
        const current = await identity();
        const result = await originalQuery(input, signal);
        const saved = budgets.get(current.key + result.taskId);
        if (saved && result.usage)
          result.usage = {
            ...result.usage,
            maximum: saved.maximum,
            budgetRevision: saved.revision,
          };
        if (options.terminal)
          result.units = result.units.map((unit) =>
            unit.stopReason === "LIMIT_REACHED"
              ? { ...unit, recovery: "TERMINAL" }
              : unit,
          );
        return result;
      },
    };
  service.coveragePlans = {
    async preview(input) {
      const current = await identity();
      if (state === "error")
        throw new ServiceError("VISUAL_TEST_ERROR", "TEST 补查预览失败", 503);
      if (state === "loading")
        return new Promise<CoveragePlanPreview>(() => {});
      if (!service.searchCoverage) return fail("本实例尚未配置覆盖夹具");
      const query = {
        contractVersion: 1 as const,
        requestId: crypto.randomUUID(),
        taskId: input.plan.taskId,
        profileId: input.plan.profileId,
        profileVersion: input.plan.profileVersion,
        expectedScope: {
          userId: current.session.userId!,
          accountScopeId: current.session.accountScope!.id,
          scopeVersion: current.session.accountScope!.version,
        },
      };
      const snapshot = parseCoverageSnapshot(
        await service.searchCoverage.query(query),
        query,
      );
      const unit = snapshot.units.find((row) => row.id === input.plan.unitId);
      const source = unit && coveragePlan(snapshot, unit);
      if (
        !source ||
        Object.entries(input.plan).some(
          ([key, value]) =>
            key !== "expiresAt" && source[key as keyof typeof source] !== value,
        )
      )
        return fail("原方向或预算版本不再一致");
      const common = {
        requestId: input.requestId,
        plan: input.plan,
        previewId: "TEST-plan-" + crypto.randomUUID(),
        generatedAt: new Date().toISOString(),
        expiresAt: input.plan.expiresAt,
        scopeSummary: unit!.unchecked.join("；"),
      };
      let preview: CoveragePlanPreview;
      if (input.plan.kind === "NEW_DRAFT")
        preview = {
          ...common,
          kind: "NEW_DRAFT",
          recovery: "TERMINAL",
          draft: {
            ...taskDraft("monitor"),
            id: "TEST-original-draft",
            name: "TEST 未查方向",
            profileId: input.plan.profileId,
            profileVersion: input.plan.profileVersion,
            revision: input.plan.configurationRevision,
            platforms: [unit!.platform],
            research: {
              ...defaultResearchSettings(),
              maxSoubei: snapshot.usage?.maximum || null,
            },
          },
        };
      else {
        if (!snapshot.usage?.maximum || !input.newMaxSoubei)
          return fail("缺少实际旧上限或新上限");
        preview = {
          ...common,
          kind: "ADJUST_LIMIT",
          recovery: "RESUMABLE_CONFIRMED",
          quote: {
            quoteId: "TEST-quote-" + crypto.randomUUID(),
            ruleVersion: snapshot.usage.ruleVersion,
            authorizationToken: "TEST-in-memory-only",
            accountScopeId: input.plan.accountScopeId,
            scopeVersion: input.plan.scopeVersion,
            taskId: input.plan.taskId,
            runId: input.plan.runId,
            budgetRevision: snapshot.usage.budgetRevision,
            oldMaxSoubei: snapshot.usage.maximum,
            newMaxSoubei: input.newMaxSoubei,
            additionalSoubei: input.newMaxSoubei - snapshot.usage.maximum,
            estimatedAdditionalSoubei: null,
            expiresAt: input.plan.expiresAt,
          },
        };
      }
      return readCoveragePreview(preview, input, current.session);
    },
    async adjust({ binding, preview }) {
      const current = await identity();
      if (
        preview.kind !== "ADJUST_LIMIT" ||
        binding.accountScopeId !== current.session.accountScope!.id ||
        binding.scopeVersion !== current.session.accountScope!.version ||
        binding.taskId !== preview.plan.taskId ||
        (await coverageConfirmationHash(preview)) !== binding.confirmationHash
      )
        return fail("调整确认范围不匹配");
      readCoveragePreview(
        preview,
        {
          requestId: preview.requestId,
          plan: preview.plan,
          newMaxSoubei: preview.quote.newMaxSoubei,
        },
        current.session,
      );
      const key = current.key + binding.requestId;
      const existing = records.get(key);
      if (existing) {
        if (existing.binding.confirmationHash !== binding.confirmationHash)
          return fail("原请求不允许改变上限");
        return structuredClone(existing);
      }
      const old = budgets.get(current.key + binding.taskId);
      if (old && old.revision !== preview.quote.budgetRevision)
        return fail("预算版本已变化");
      const { authorizationToken: _token, ...quote } = preview.quote;
      const result: CoverageAdjustmentReceipt = {
        binding,
        status: "APPLIED",
        notResumed: true,
        previousBudgetRevision: quote.budgetRevision,
        budgetRevision: quote.budgetRevision + 1,
        maximum: quote.newMaxSoubei,
        confirmation: { ...preview, quote },
      };
      budgets.set(current.key + binding.taskId, {
        revision: result.budgetRevision,
        maximum: result.maximum,
      });
      records.set(key, structuredClone(result));
      return { binding, status: "UNKNOWN" };
    },
    async reconcile(binding) {
      const current = await identity();
      if (
        binding.accountScopeId !== current.session.accountScope!.id ||
        binding.scopeVersion !== current.session.accountScope!.version
      )
        return fail("核对空间不匹配");
      const result = records.get(current.key + binding.requestId);
      if (!result) return { binding, status: "UNKNOWN" };
      if (
        result.binding.confirmationHash !== binding.confirmationHash ||
        result.binding.taskId !== binding.taskId
      )
        return fail("核对不是原请求");
      return structuredClone(result);
    },
  };
}
