import type { MaterialReceipt } from "../../src/renderer/domain/materials";
import type { MaterialService } from "../../src/renderer/services/materials";
import { makeVisualMaterials, TEST_MATERIAL_PROFILE_ID } from "./materials";

type FaultKind = "save" | "revoke" | "remove";
type Snapshot = {
  next: FaultKind | null;
  phase: "READY" | "UNKNOWN" | "RELEASED";
  requestId: string;
};

/** TEST transport only. The real page keeps its own request lock and recovery logic. */
export function makeMaterialRecovery(record: (operation: string, detail?: string) => void) {
  const base = makeVisualMaterials();
  const listeners = new Set<() => void>();
  let state: Snapshot = { next: null, phase: "READY", requestId: "" };
  const withheld = new Map<string, { input: string; receipt: MaterialReceipt; released: boolean }>();
  const update = (patch: Partial<Snapshot>) => {
    state = { ...state, ...patch };
    listeners.forEach((listener) => listener());
  };
  const unknown = (receipt: MaterialReceipt): MaterialReceipt => ({
    requestId: receipt.requestId,
    profileVersionId: receipt.profileVersionId,
    materialId: receipt.materialId,
    kind: receipt.kind,
    status: "UNKNOWN",
    message: "TEST 内存回执暂不可见，请核对原资料操作。",
  });
  const service: MaterialService = {
    ...base,
    async mutate(request, options) {
      if (request.profileVersionId !== TEST_MATERIAL_PROFILE_ID)
        throw new Error("TEST 资料恢复仅接受本场景画像。");
      if (options.signal.aborted) throw new Error("TEST 等待已取消。");
      const cached = withheld.get(request.requestId);
      if (cached) {
        if (cached.input !== JSON.stringify(request))
          throw new Error("TEST 原请求内容不匹配，未重复操作。");
        record("materialRecovery.replay", request.requestId);
        return cached.released ? structuredClone(cached.receipt) : unknown(cached.receipt);
      }
      if (state.phase === "UNKNOWN")
        throw new Error("TEST 原资料操作尚未核对，拒绝新请求。");
      const receipt = await base.mutate(request, options);
      record("materialRecovery.mutate", `${request.change.kind}:${request.requestId}:${receipt.status}`);
      if (state.next === request.change.kind && receipt.status === "SUCCEEDED") {
        withheld.set(request.requestId, {
          input: JSON.stringify(request), receipt: structuredClone(receipt), released: false,
        });
        update({ next: null, phase: "UNKNOWN", requestId: request.requestId });
        return unknown(receipt);
      }
      return receipt;
    },
    async operation(profileId, requestId) {
      if (profileId !== TEST_MATERIAL_PROFILE_ID)
        throw new Error("TEST 资料恢复画像不匹配。");
      record("materialRecovery.query", requestId);
      const cached = withheld.get(requestId);
      return cached
        ? cached.released ? structuredClone(cached.receipt) : unknown(cached.receipt)
        : base.operation(profileId, requestId);
    },
  };
  return {
    service,
    snapshot: () => state,
    subscribe(listener: () => void) { listeners.add(listener); return () => { listeners.delete(listener); }; },
    arm(kind: FaultKind) {
      if (state.phase === "UNKNOWN") throw new Error("TEST 请先释放原回执。");
      update({ next: kind, phase: "READY", requestId: "" });
    },
    release() {
      const cached = withheld.get(state.requestId);
      if (!cached || cached.released) return;
      cached.released = true;
      record("materialRecovery.release", state.requestId);
      update({ phase: "RELEASED" });
    },
  };
}
export type MaterialRecoveryController = ReturnType<typeof makeMaterialRecovery>;
