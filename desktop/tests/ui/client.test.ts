// @vitest-environment jsdom
import { afterEach, describe, it, expect, vi } from "vitest";
import {
  service,
  profileDescription,
  mapProfile,
} from "../../src/renderer/services/client";
import type { YikeDesktopApi } from "../../src/shared/contracts";
const host = window as unknown as { yikeDesktop?: YikeDesktopApi };
afterEach(() => {
  delete host.yikeDesktop;
  vi.unstubAllGlobals();
});
describe("real client transport boundaries", () => {
  it("preserves newline and punctuation in real profile roundtrip", () => {
    const fields = {
      service: "展台\n设计",
      customer: "含“引号”客户",
      regions: "沪 / 苏",
      preference: "行1\n行2",
      exclusions: "",
    };
    expect(
      mapProfile({
        version_id: "p1",
        version: 1,
        status: "DRAFT",
        payload: { description: profileDescription(fields) },
      }).fields,
    ).toEqual(fields);
  });
  it("does not turn rejected native copy or external links into success", async () => {
    host.yikeDesktop = {
      copyText: vi.fn().mockResolvedValue({ ok: false, error: "INVALID_TEXT" }),
      openExternal: vi
        .fn()
        .mockResolvedValue({ ok: false, error: "UNSAFE_URL" }),
    } as unknown as YikeDesktopApi;
    await expect(service.copy("")).rejects.toMatchObject({
      code: "INVALID_TEXT",
    });
    await expect(
      service.openExternal("https://example.com"),
    ).rejects.toMatchObject({ code: "UNSAFE_URL" });
  });
  it("preserves configuration error from the native fixed-operation bridge", async () => {
    host.yikeDesktop = {
      requestApi: vi
        .fn()
        .mockResolvedValue({
          ok: false,
          status: 0,
          error: "SERVICE_NOT_CONFIGURED",
        }),
    } as unknown as YikeDesktopApi;
    await expect(service.profiles()).rejects.toMatchObject({
      code: "SERVICE_NOT_CONFIGURED",
    });
    expect(host.yikeDesktop.requestApi).toHaveBeenCalledWith({
      operation: "profiles.list",
      payload: undefined,
    });
  });
  it("sends no GET body and refuses browser redirects", async () => {
    const request = vi
      .fn()
      .mockResolvedValue(
        new Response(
          JSON.stringify({ opportunity: { opportunity_id: "o1" } }),
          { headers: { "content-type": "application/json" } },
        ),
      );
    vi.stubGlobal("fetch", request);
    await service.opportunity("o1");
    expect(request).toHaveBeenCalledWith(
      "/api/ui/opportunities/o1",
      expect.objectContaining({
        method: "GET",
        body: undefined,
        redirect: "error",
        credentials: "same-origin",
      }),
    );
  });
  it("reports plaintext Origin forbidden separately from unconfigured service", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("Forbidden", { status: 403 })),
    );
    await expect(service.profiles()).rejects.toMatchObject({
      code: "HTTP_403",
      status: 403,
    });
  });
  it("does not claim configured service or ready executor from a browser URL", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
    await expect(service.info()).resolves.toMatchObject({
      serviceConfigured: false,
      deviceReady: false,
    });
  });
});
