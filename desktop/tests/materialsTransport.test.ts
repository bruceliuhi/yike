// @vitest-environment jsdom
import { randomUUID } from "node:crypto";
import { afterEach, describe, expect, it, vi } from "vitest";
import { validatedOperation } from "../src/main/servicePolicy";
import { API_OPERATIONS, type YikeDesktopApi } from "../src/shared/contracts";
import { service } from "../src/renderer/services/client";

const host = window as unknown as { yikeDesktop?: YikeDesktopApi };
const id = () => randomUUID();
const profileVersionId = id();
const materialId = "local-" + "a".repeat(64);

function input() {
  return {
    name: "产品资料",
    text: "为制造企业提供设备维保服务。",
    purpose: "产品介绍" as const,
    visibility: "internal" as const,
    fileName: "product.md",
    bytes: 42,
  };
}

function saveRequest() {
  return {
    requestId: id(),
    profileVersionId,
    change: { kind: "save" as const, materialId, expectedVersion: null, input: input() },
  };
}

function record(version = 1) {
  return {
    id: materialId,
    profileVersionId,
    version,
    updatedAt: "2026-09-12T01:00:00Z",
    status: "DRAFT" as const,
    ...input(),
  };
}

afterEach(() => {
  delete host.yikeDesktop;
  vi.unstubAllGlobals();
});

describe("materials fixed-operation policy", () => {
  it("maps the four operations to fixed routes without caller authority", () => {
    const request = saveRequest();
    const requestId = request.requestId;
    expect(API_OPERATIONS).toEqual(expect.arrayContaining([
      "materials.list", "materials.mutate", "materials.operation", "materials.impact",
    ]));
    expect(validatedOperation({ operation: "materials.list", payload: { profileVersionId } })).toEqual({
      path: `/api/ui/materials?profileVersionId=${profileVersionId}`, method: "GET", logout: false,
    });
    expect(validatedOperation({ operation: "materials.mutate", payload: request })).toEqual({
      path: "/api/ui/materials/mutate", method: "POST", body: JSON.stringify(request), logout: false,
    });
    expect(validatedOperation({ operation: "materials.operation", payload: { profileVersionId, requestId } })).toEqual({
      path: `/api/ui/materials/operation?profileVersionId=${profileVersionId}&requestId=${requestId}`,
      method: "GET", logout: false,
    });
    const impact = { profileVersionId, materialId, version: 1, action: "remove" as const };
    expect(validatedOperation({ operation: "materials.impact", payload: impact })).toEqual({
      path: "/api/ui/materials/impact", method: "POST", body: JSON.stringify(impact), logout: false,
    });
  });

  it("rejects extra authority, malformed changes and oversized bodies", () => {
    const valid = saveRequest();
    for (const request of [
      { operation: "materials.list", payload: { profileVersionId, tenantId: id() } },
      { operation: "materials.operation", payload: { profileVersionId, requestId: "../session" } },
      { operation: "materials.impact", payload: { profileVersionId, materialId, version: 0, action: "remove" } },
      { operation: "materials.mutate", payload: { ...valid, ownerId: id() } },
      { operation: "materials.mutate", payload: { ...valid, change: { ...valid.change, input: { ...input(), text: "x".repeat(2001) } } } },
      { operation: "materials.mutate", payload: { ...valid, change: { kind: "parse", materialId, expectedVersion: null } } },
    ]) expect(validatedOperation(request)).toBeNull();
  });
});

describe("materials renderer transport", () => {
  it("uses exact browser routes, validates list scope and never fabricates upload progress", async () => {
    expect(service.materials).toBeDefined();
    const fetch = vi.fn(async () => Response.json([record()]));
    vi.stubGlobal("fetch", fetch);
    await expect(service.materials!.list(profileVersionId)).resolves.toEqual([record()]);
    expect(fetch).toHaveBeenCalledWith(
      `/api/ui/materials?profileVersionId=${profileVersionId}`,
      expect.objectContaining({ method: "GET", body: undefined, credentials: "same-origin", redirect: "error" }),
    );

    const request = saveRequest();
    fetch.mockResolvedValueOnce(Response.json({
      requestId: request.requestId, profileVersionId, materialId, kind: "save", status: "SUCCEEDED", record: record(),
    }));
    const progress = vi.fn();
    await service.materials!.mutate(request, { signal: new AbortController().signal, onUploadProgress: progress });
    expect(fetch).toHaveBeenLastCalledWith("/api/ui/materials/mutate", expect.objectContaining({
      method: "POST", body: JSON.stringify(request),
    }));
    expect(progress).not.toHaveBeenCalled();
  });

  it("rejects mismatched receipts and records instead of adopting them", async () => {
    const requestApi = vi.fn(async () => ({ ok: true as const, status: 200, data: {
      requestId: id(), profileVersionId, materialId, kind: "save", status: "SUCCEEDED", record: record(),
    } }));
    host.yikeDesktop = { requestApi } as unknown as YikeDesktopApi;
    const request = saveRequest();
    await expect(service.materials!.mutate(request, {
      signal: new AbortController().signal, onUploadProgress: vi.fn(),
    })).rejects.toThrow("资料回执与原请求不匹配");
    expect(requestApi).toHaveBeenCalledExactlyOnceWith({ operation: "materials.mutate", payload: request });
  });

  it("forwards browser abort but only rejects a late Electron result after dispatch", async () => {
    const browserAbort = new AbortController();
    const fetch = vi.fn((_url: string, init: RequestInit) => new Promise<Response>((_resolve, reject) => {
      init.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
    }));
    vi.stubGlobal("fetch", fetch);
    const browserPending = service.materials!.mutate(saveRequest(), { signal: browserAbort.signal, onUploadProgress: vi.fn() });
    browserAbort.abort();
    await expect(browserPending).rejects.toMatchObject({ name: "AbortError" });
    expect(fetch.mock.calls[0][1]?.signal).toBe(browserAbort.signal);

    let resolve!: (value: Awaited<ReturnType<YikeDesktopApi["requestApi"]>>) => void;
    const requestApi = vi.fn(() => new Promise<Awaited<ReturnType<YikeDesktopApi["requestApi"]>>>((done) => { resolve = done; }));
    host.yikeDesktop = { requestApi } as unknown as YikeDesktopApi;
    const request = saveRequest();
    const electronAbort = new AbortController();
    const electronPending = service.materials!.mutate(request, { signal: electronAbort.signal, onUploadProgress: vi.fn() });
    electronAbort.abort();
    resolve({ ok: true, status: 200, data: {
      requestId: request.requestId, profileVersionId, materialId, kind: "save", status: "SUCCEEDED", record: record(),
    } });
    await expect(electronPending).rejects.toMatchObject({ name: "AbortError" });
    expect(requestApi).toHaveBeenCalledTimes(1);
  });
});
