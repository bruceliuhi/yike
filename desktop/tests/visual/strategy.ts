import { ServiceError, type YikeService } from "../../src/renderer/services/contracts";
import { newTaskDraft, EMPTY_PROFILE, type TaskDraft } from "../../src/renderer/domain/models";
import { defaultResearchSettings } from "../../src/renderer/domain/researchUsage";
import type { StrategyReceipt } from "../../src/shared/researchStrategies";

/** TEST memory only, reached solely through the isolated visual entry. */
export function configureStrategyVisual(service: YikeService): TaskDraft {
  const draft = { ...newTaskDraft(), name: "TEST 跨行业设备需求研究", profileId: crypto.randomUUID(), profileVersion: 1,
    terms: [{ id: "TEST-term", value: "设备采购", origin: "manual" as const, edited: true }],
    exclusions: [{ id: "TEST-exclusion", value: "招聘", origin: "manual" as const, edited: true }],
    platforms: ["web" as const], links: "",
    executionLimits: { max_records: 37, max_runtime_seconds: 913 },
    research: { ...defaultResearchSettings(), maxSoubei: 200 } };
  service.profiles = async () => [{ id: draft.profileId, version: 1, status: "CONFIRMED", description: "TEST 合成画像",
    fields: { ...EMPTY_PROFILE, service: "TEST 设备服务" } }];
  const receipts = new Map<string, StrategyReceipt>();
  let prepared: StrategyReceipt | null = null;
  let state: StrategyReceipt["state"] = "DRAFT";
  const instant = "2026-09-10T00:00:00Z";
  function known(id: string) {
    if (!prepared || prepared.strategy_version_id !== id) throw new ServiceError("request_not_found", "TEST 未找到", 404);
    return prepared;
  }
  service.researchStrategies = {
    async prepare(request) {
      if (receipts.has(request.request_id)) return structuredClone(receipts.get(request.request_id));
      const id = crypto.randomUUID();
      prepared = { schema_version: "strategy-confirmation-v1", operation: "PREPARE", request_id: request.request_id,
        strategy_version_id: id, draft_id: request.draft_id, draft_revision: request.draft_revision,
        profile_version_id: request.profile_version_id, profile_sha256: "a".repeat(64), configuration_sha256: "b".repeat(64),
        snapshot: { strategy_version_id: id, profile_version_id: request.profile_version_id,
          configuration: structuredClone(request.configuration), platforms: [...request.platforms],
          max_records: request.max_records, max_runtime_seconds: request.max_runtime_seconds }, state: "DRAFT", recorded_at: instant };
      state = "DRAFT";
      receipts.set(request.request_id, structuredClone(prepared));
      return structuredClone(prepared);
    },
    async confirm(request) {
      const original = known(request.strategy_version_id);
      if (state === "REVOKED" || request.configuration_sha256 !== original.configuration_sha256 || request.human_confirmed !== true)
        throw new ServiceError("conflict", "TEST 快照已失效", 409);
      state = "CONFIRMED";
      const result = { ...original, request_id: request.request_id, operation: "CONFIRM" as const, state };
      receipts.set(request.request_id, result);
      return structuredClone(result);
    },
    async revoke(request) {
      const original = known(request.strategy_version_id);
      state = "REVOKED";
      const result = { ...original, request_id: request.request_id, operation: "REVOKE" as const, state };
      receipts.set(request.request_id, result);
      return structuredClone(result);
    },
    async getReceipt(id) {
      if (!receipts.has(id)) throw new ServiceError("request_not_found", "TEST 未找到", 404);
      return structuredClone(receipts.get(id));
    },
    async getStrategy(id) {
      const { request_id: _request, operation: _operation, recorded_at: _recorded, ...binding } = known(id);
      return { ...structuredClone(binding), state, created_at: instant, confirmed_at: state === "CONFIRMED" ? instant : null,
        revoked_at: state === "REVOKED" ? instant : null, is_current: true, profile_current: true };
    },
  };
  return draft;
}
