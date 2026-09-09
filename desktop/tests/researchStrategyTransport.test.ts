// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { randomUUID } from "node:crypto";
import { API_OPERATIONS, type YikeDesktopApi } from "../src/shared/contracts";
import { validatedOperation } from "../src/main/servicePolicy";
import { createServiceClient } from "../src/main/serviceClient";
import { service } from "../src/renderer/services/client";

const host = window as unknown as { yikeDesktop?: YikeDesktopApi };
afterEach(() => { delete host.yikeDesktop; vi.unstubAllGlobals(); });

function prepare() {
  return {
    schema_version: "strategy-confirmation-v1", request_id: randomUUID(), draft_id: randomUUID(),
    draft_revision: 1, profile_version_id: randomUUID(),
    configuration: { schema_version: "research-strategy-v1", name: "工厂设备需求", source: "search",
      keywords: ["输送设备采购"], exclusions: [], links: [], mode: "once", schedule: null, research: null },
    platforms: ["PUBLIC_WEB"], max_records: 100, max_runtime_seconds: 900,
  };
}
function body(kind: string): Record<string, unknown> {
  if (kind === "prepare") return prepare();
  if (kind === "receipt") return { request_id: randomUUID() };
  if (kind === "get") return { strategy_version_id: randomUUID() };
  return { schema_version: "strategy-confirmation-v1", request_id: randomUUID(), strategy_version_id: randomUUID(),
    ...(kind === "confirm" ? { configuration_sha256: "a".repeat(64), human_confirmed: true } : {}) };
}

describe("real strategy fixed-operation transport", () => {
  it.each(["prepare", "confirm", "revoke", "receipt", "get"])("registers the fixed %s operation", (kind) => {
    const operation = `strategies.${kind}`;
    const payload = body(kind);
    expect(API_OPERATIONS).toContain(operation);
    const actual = validatedOperation({ operation, payload });
    expect(actual).not.toBeNull();
    const expectedPath = kind === "receipt" ? `/api/ui/research-strategy-operations/${payload.request_id}`
      : kind === "get" ? `/api/ui/research-strategies/${payload.strategy_version_id}`
        : `/api/ui/research-strategies/${kind}`;
    expect(actual).toMatchObject({ path: expectedPath, method: ["receipt", "get"].includes(kind) ? "GET" : "POST", logout: false });
    if (["receipt", "get"].includes(kind)) expect(actual!.body).toBeUndefined();
    else expect(JSON.parse(actual!.body!)).toEqual(payload);
  });

  it("rejects caller-controlled authority and malformed requests before network", async () => {
    const fetch = vi.fn();
    const client = createServiceClient({ baseUrl: "https://pilot.example", fetch, clearSession: async () => {} });
    const payload = prepare();
    for (const bad of [
      { operation: "strategies.prepare", payload, path: "/admin" },
      { operation: "strategies.prepare", payload: { ...payload, owner_user_id: "private-input" } },
      { operation: "strategies.prepare", payload: { ...payload, max_records: true } },
      { operation: "strategies.prepare", payload: { ...payload, draft_revision: 2147483648 } },
      { operation: "strategies.confirm", payload: { ...body("confirm"), human_confirmed: 1 } },
      { operation: "strategies.receipt", payload: { request_id: "../session" } },
      { operation: "strategies.get", payload: { strategy_version_id: randomUUID(), tenant_id: "private-input" } },
      { operation: "strategies.prepare", payload: { ...payload, configuration: { ...payload.configuration, name: "x".repeat(131073) } } },
    ]) expect(await client.request(bad)).toEqual({ ok: false, status: 0, error: "INVALID_API_REQUEST" });
    expect(fetch).not.toHaveBeenCalled();
  });

  it("sends one exact validated browser request and no GET body", async () => {
    expect(service.researchStrategies).toBeDefined();
    const fetch = vi.fn(async () => Response.json({ transport_test: true }));
    vi.stubGlobal("fetch", fetch);
    const payload = prepare();
    await service.researchStrategies!.prepare(payload as never);
    expect(fetch).toHaveBeenCalledWith("/api/ui/research-strategies/prepare", expect.objectContaining({
      method: "POST", body: JSON.stringify(payload), credentials: "same-origin", redirect: "error",
    }));
    const key = randomUUID();
    await service.researchStrategies!.getReceipt(key);
    expect(fetch).toHaveBeenLastCalledWith(`/api/ui/research-strategy-operations/${key}`, expect.objectContaining({ method: "GET", body: undefined }));
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it("uses the same fixed bridge and propagates 409 without success or retry", async () => {
    expect(service.researchStrategies).toBeDefined();
    const requestApi = vi.fn(async () => ({ ok: false as const, status: 409, error: "strategy_conflict" }));
    host.yikeDesktop = { requestApi } as unknown as YikeDesktopApi;
    const payload = body("confirm");
    await expect(service.researchStrategies!.confirm(payload as never)).rejects.toMatchObject({ code: "strategy_conflict", status: 409 });
    expect(requestApi).toHaveBeenCalledExactlyOnceWith({ operation: "strategies.confirm", payload });
  });

  it.each([401, 404, 422, 501, 503])("does not synthesize a successful strategy on HTTP %s", async (status) => {
    expect(service.researchStrategies).toBeDefined();
    const fetch = vi.fn(async () => Response.json({ detail: { code: "strategy_unavailable" } }, { status }));
    vi.stubGlobal("fetch", fetch);
    await expect(service.researchStrategies!.getStrategy(randomUUID())).rejects.toMatchObject({ status });
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("validates browser inputs too and preserves timeout as an unknown outcome", async () => {
    expect(service.researchStrategies).toBeDefined();
    const requestApi = vi.fn(async () => ({ ok: false as const, status: 0, error: "SERVICE_TIMEOUT" }));
    host.yikeDesktop = { requestApi } as unknown as YikeDesktopApi;
    await expect(service.researchStrategies!.prepare({ ...prepare(), tenant_id: "private-input" } as never)).rejects.toMatchObject({ code: "INVALID_REQUEST" });
    expect(requestApi).not.toHaveBeenCalled();
    await expect(service.researchStrategies!.revoke(body("revoke") as never)).rejects.toMatchObject({ code: "SERVICE_TIMEOUT" });
    expect(requestApi).toHaveBeenCalledTimes(1);
  });
});
