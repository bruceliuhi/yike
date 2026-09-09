import { describe, expect, it, vi } from "vitest";
import type { MaterialRequest } from "../../src/renderer/domain/materials";
import { TEST_MATERIAL_PROFILE_ID } from "./materials";
import { makeMaterialRecovery } from "./materialRecovery";

const options = () => ({ signal: new AbortController().signal, onUploadProgress: vi.fn() });
const save = (): MaterialRequest => ({
  requestId: crypto.randomUUID(), profileVersionId: TEST_MATERIAL_PROFILE_ID,
  change: { kind: "save", materialId: "TEST-recovery-material", expectedVersion: null,
    input: { name: "TEST 资料恢复", text: "TEST 仅用于内存验收", purpose: "产品介绍", visibility: "external" } },
});
describe("TEST material receipt withholding", () => {
  it("keeps one original request unknown across repeated queries and releases its exact snapshot", async () => {
    const log = vi.fn(); const c = makeMaterialRecovery(log); const req = save();
    c.arm("save");
    expect(await c.service.mutate(req, options())).toMatchObject({ requestId: req.requestId, status: "UNKNOWN" });
    expect((await c.service.operation(req.profileVersionId, req.requestId)).status).toBe("UNKNOWN");
    expect((await c.service.mutate(req, options())).status).toBe("UNKNOWN");
    await expect(c.service.mutate({ ...req, requestId: crypto.randomUUID() }, options())).rejects.toThrow("拒绝新请求");
    expect(log.mock.calls.filter(([event]) => event === "materialRecovery.mutate")).toHaveLength(1);
    c.release();
    const result = await c.service.operation(req.profileVersionId, req.requestId);
    expect(result).toMatchObject({ status: "SUCCEEDED", record: { version: 1, status: "DRAFT" } });
    result.record!.name = "mutated caller";
    expect((await c.service.operation(req.profileVersionId, req.requestId)).record!.name).toBe("TEST 资料恢复");
  });
  it("rejects scope, changed request bytes and unknown request IDs without fabricating receipts", async () => {
    const c = makeMaterialRecovery(vi.fn()); const req = save(); c.arm("save");
    await c.service.mutate(req, options());
    await expect(c.service.operation("another-profile", req.requestId)).rejects.toThrow("画像不匹配");
    await expect(c.service.operation(req.profileVersionId, crypto.randomUUID())).rejects.toThrow("没有该原请求");
    await expect(c.service.mutate({ ...req, change: { ...req.change, materialId: "TEST-other" } }, options())).rejects.toThrow("内容不匹配");
  });
  it("uses real fixture versions and impact tokens for revoke and remove, with no duplicate mutation", async () => {
    const c = makeMaterialRecovery(vi.fn()); const req = save(); const api = c.service;
    const saved = await api.mutate(req, options());
    const parsed = await api.mutate({ ...req, requestId: crypto.randomUUID(), change: { kind: "parse", materialId: req.change.materialId, expectedVersion: saved.record!.version } }, options());
    const ready = await api.mutate({ ...req, requestId: crypto.randomUUID(), change: { kind: "confirm", materialId: req.change.materialId, expectedVersion: parsed.record!.version, extractionId: parsed.record!.extraction!.id, fields: parsed.record!.extraction!.fields } }, options());
    for (const kind of ["revoke", "remove"] as const) {
      const row = (await api.list(req.profileVersionId))[0];
      const impact = await api.impact(req.profileVersionId, row.id, row.version, kind);
      const request = { ...req, requestId: crypto.randomUUID(), change: { kind, materialId: row.id, expectedVersion: row.version, impactToken: impact.token } };
      c.arm(kind);
      expect((await api.mutate(request, options())).status).toBe("UNKNOWN");
      c.release();
      const result = await api.operation(req.profileVersionId, request.requestId);
      expect(result.status).toBe("SUCCEEDED");
      if (kind === "revoke") expect(result.record).toMatchObject({ version: ready.record!.version + 1, status: "REVOKED" });
    }
    expect(await api.list(req.profileVersionId)).toEqual([]);
  });
});
