// @vitest-environment jsdom
import { afterEach, describe, it, expect, vi } from "vitest";
import {
  service,
  profileDescription,
  mapProfile,
  mapOpportunity,
} from "../../src/renderer/services/client";
import {
  compareTaskProfile,
  parseTaskProfiles,
} from "../../src/renderer/domain/taskProfile";
import type { YikeDesktopApi } from "../../src/shared/contracts";
import { capturedEvidenceFixture } from "../fixtures/opportunitySourceEvidence";
import { pageFixture, assessmentRequestFixture } from "../fixtures/candidateReviewApi";
import { rawEvidenceBinding, rawEvidenceFixture } from "../fixtures/rawCandidateEvidence";
const host = window as unknown as { yikeDesktop?: YikeDesktopApi };
afterEach(() => {
  delete host.yikeDesktop;
  vi.unstubAllGlobals();
});
describe("real client transport boundaries", () => {
  it('opens source only through fixed bound desktop entry without raw errors or fallback',async()=>{
    const openSourceView=vi.fn().mockResolvedValue({state:'OPENED',sourceKind:'COMMENT'});
    host.yikeDesktop={openSourceView} as unknown as YikeDesktopApi;
    expect(await service.openSourceView!(rawEvidenceBinding)).toEqual({state:'OPENED',sourceKind:'COMMENT'});
    expect(openSourceView).toHaveBeenCalledWith(rawEvidenceBinding);
    openSourceView.mockResolvedValue({state:'OPENED',sourceKind:'COMMENT',secret:'PRIVATE'});
    await expect(service.openSourceView!(rawEvidenceBinding)).rejects.toThrow('暂时无法打开原文');
    delete host.yikeDesktop;
    await expect(service.openSourceView!(rawEvidenceBinding)).rejects.toThrow('请在最新版客户端中查看');
  });
  it("reads original candidate evidence while the legacy implicit write entry stays disabled", async () => {
    const data = rawEvidenceFixture();
    const requestApi = vi.fn().mockResolvedValue({ok:true,status:200,data});
    host.yikeDesktop = {requestApi} as unknown as YikeDesktopApi;
    expect(await service.rawCandidateEvidence!(rawEvidenceBinding)).toEqual(data);
    expect(requestApi).toHaveBeenCalledExactlyOnceWith({operation:"candidates.rawEvidence",payload:{candidateId:rawEvidenceBinding.candidateId}});
    expect(service.candidateReview).toBeDefined();
    await expect(service.reviewCandidate(assessmentRequestFixture() as Parameters<typeof service.reviewCandidate>[0])).rejects.toMatchObject({status:501});
    expect(requestApi).toHaveBeenCalledTimes(1);
  });
  it("reads strict candidates but does not enable the legacy implicit assessment entry", async () => {
    const data = pageFixture();
    const requestApi = vi
      .fn()
      .mockResolvedValue({ ok: true, status: 200, data });
    host.yikeDesktop = { requestApi } as unknown as YikeDesktopApi;
    const page = await service.candidates({
      query: "   ",
      platform: "公开网站",
    });
    expect(page).toEqual({
      ...data,
      items: data.items.map((item) => ({
        ...item,
        platform: "公开网站",
        sourceLabel: "公开网站",
      })),
    });
    expect(requestApi).toHaveBeenCalledWith({
      operation: "candidates.list",
      payload: { platform: "PUBLIC_WEB" },
    });
    await expect(
      service.reviewCandidate(
        assessmentRequestFixture() as Parameters<
          typeof service.reviewCandidate
        >[0],
      ),
    ).rejects.toMatchObject({ status: 501 });
    expect(requestApi).toHaveBeenCalledTimes(1);
  });
  function profilesResponse(items: unknown[]) {
    host.yikeDesktop = {
      requestApi: vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        data: { items },
      }),
    } as unknown as YikeDesktopApi;
  }

  it.each([
    ["missing", undefined],
    ["zero", 0],
    ["nonnumeric", "invalid"],
    ["numeric string", "1"],
    ["negative", -1],
    ["fractional", 1.5],
    ["unsafe", Number.MAX_SAFE_INTEGER + 1],
    ["boolean", true],
  ])("rejects a raw %s profile version before comparison", async (_case, version) => {
    profilesResponse([
      {
        profile_id: "TEST-business",
        version_id: "TEST-version",
        ...(version === undefined ? {} : { version }),
        status: "CONFIRMED",
        payload: { description: "TEST profile" },
      },
    ]);

    await expect(service.profiles()).rejects.toMatchObject({
      code: "INVALID_SERVICE_RESPONSE",
      message: "画像列表响应不完整，请重新读取；未确认任何版本关系。",
    });
  });

  it.each([
    [{ version_id: "", profile_id: "TEST-business", version: 1, status: "CONFIRMED" }],
    [{ version_id: " TEST-version", profile_id: "TEST-business", version: 1, status: "CONFIRMED" }],
    [{ version_id: "TEST-version", profile_id: null, version: 1, status: "CONFIRMED" }],
    [{ version_id: "TEST-version", profile_id: "bad\nlineage", version: 1, status: "CONFIRMED" }],
    [{ version_id: "TEST-version", profile_id: "TEST-business", version: 1, status: "PUBLISHED" }],
  ])("rejects invalid raw profile identity, lineage, or status", async (raw) => {
    profilesResponse([{ ...raw, payload: { description: "TEST profile" } }]);

    await expect(service.profiles()).rejects.toMatchObject({
      code: "INVALID_SERVICE_RESPONSE",
      message: "画像列表响应不完整，请重新读取；未确认任何版本关系。",
    });
  });

  it("preserves valid raw profile facts and keeps absent lineage unknown", async () => {
    profilesResponse([
      {
        profile_id: "TEST-business",
        version_id: "TEST-draft",
        version: 1,
        status: "DRAFT",
        payload: { description: "TEST draft" },
      },
      {
        profile_id: "TEST-business",
        version_id: "TEST-confirmed",
        version: 2,
        status: "CONFIRMED",
        payload: { description: "TEST confirmed" },
      },
      {
        profile_id: "TEST-business",
        version_id: "TEST-revoked",
        version: Number.MAX_SAFE_INTEGER,
        status: "REVOKED",
        payload: { description: "TEST revoked" },
      },
      {
        version_id: "TEST-legacy",
        version: 3,
        status: "CONFIRMED",
        payload: { description: "TEST legacy" },
      },
    ]);

    const profiles = await service.profiles();
    expect(profiles.map(({ id, profileEntityId, version, status }) => ({
      id,
      profileEntityId,
      version,
      status,
    }))).toEqual([
      { id: "TEST-draft", profileEntityId: "TEST-business", version: 1, status: "DRAFT" },
      { id: "TEST-confirmed", profileEntityId: "TEST-business", version: 2, status: "CONFIRMED" },
      { id: "TEST-revoked", profileEntityId: "TEST-business", version: Number.MAX_SAFE_INTEGER, status: "REVOKED" },
      { id: "TEST-legacy", profileEntityId: undefined, version: 3, status: "CONFIRMED" },
    ]);
    expect(
      compareTaskProfile(
        { profileId: "TEST-legacy", profileVersion: 3 },
        parseTaskProfiles(profiles),
      ),
    ).toMatchObject({ status: "UNKNOWN" });
  });

  it("does not echo malformed raw profile facts in the fixed failure", async () => {
    profilesResponse([
      {
        profile_id: "TEST-secret-lineage",
        version_id: "TEST-secret-version",
        version: "TEST-secret-value",
        status: "CONFIRMED",
      },
    ]);

    const error = await service.profiles().catch((value: unknown) => value);
    expect(error).toMatchObject({ code: "INVALID_SERVICE_RESPONSE" });
    expect(String(error)).not.toContain("TEST-secret");
  });

  it("keeps absent P10 facts optional and malformed facts distinct without deriving dates", () => {
    const missing = mapOpportunity({
      opportunity_id: "TEST-o",
      intent_status: "QUOTED",
      action_signal: "9月15日18:00截止",
    });
    expect(missing.libraryFacts).toBeUndefined();
    const invalid = mapOpportunity({
      opportunity_id: "TEST-o",
      library_facts: { schema_version: 999 },
      source_observed_at: "2026-09-09T00:00:00Z",
      source_evidence_version: "TEST-v1",
    });
    expect(invalid.libraryFacts).toBeNull();
    expect(invalid.sourceObservedAt).toBe("2026-09-09T00:00:00Z");
    expect(invalid.sourceEvidenceVersion).toBe("TEST-v1");
  });
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
      requestApi: vi.fn().mockResolvedValue({
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
          JSON.stringify({ opportunity: {
            opportunity_id: "o1",
            profile_version_id: "p1",
            source_evidence: { status: "UNAVAILABLE", reason: "NOT_CAPTURED" },
          } }),
          { headers: { "content-type": "application/json" } },
        ),
      );
    vi.stubGlobal("fetch", request);
    await service.opportunity("o1");
    expect(request).toHaveBeenCalledWith(
      "/api/ui/opportunities/o1?evidenceVersion=1",
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

describe("fixed original evidence in the ordinary opportunity client", () => {
  const absent = { status: "UNAVAILABLE", reason: "NOT_CAPTURED" };
  function detail(raw: Record<string, unknown>) {
    const requestApi = vi.fn().mockResolvedValue({
      ok: true, status: 200, data: { opportunity: raw },
    });
    host.yikeDesktop = { requestApi } as unknown as YikeDesktopApi;
    return requestApi;
  }
  it("retains the entire captured snapshot even when current source is blocked", async () => {
    const evidence = capturedEvidenceFixture();
    detail({ opportunity_id: "TEST-o", profile_version_id: "TEST-p", source_evidence: evidence,
      source_status: "BLOCKED", source_evidence_version: "TEST-R4-version" });
    await expect(service.opportunity("TEST-o")).resolves.toMatchObject({
      sourceEvidence: evidence, sourceStatus: "BLOCKED", sourceEvidenceVersion: "TEST-R4-version",
    });
  });
  it.each([
    { opportunityId: "TEST-other" }, { profileVersionId: "TEST-other" },
  ])("rejects a captured snapshot for another identity or profile", async (overrides) => {
    detail({ opportunity_id: "TEST-o", profile_version_id: "TEST-p",
      source_evidence: capturedEvidenceFixture(overrides) });
    await expect(service.opportunity("TEST-o")).rejects.toMatchObject({ code: "INVALID_SERVICE_RESPONSE" });
  });
  it("keeps list omission distinct from explicit absence without rebinding legacy evidence", () => {
    const raw = { opportunity_id: "TEST-o", profile_version_id: "TEST-p",
      source_evidence_version: "TEST-legacy-version", source_observed_at: "TEST-legacy-time" };
    expect(mapOpportunity(raw).sourceEvidence).toBeUndefined();
    expect(mapOpportunity({ ...raw, source_evidence: absent })).toMatchObject({
      sourceEvidence: absent, sourceEvidenceVersion: "TEST-legacy-version",
      sourceObservedAt: "TEST-legacy-time",
    });
  });
  it.each([null, undefined, { status: "CAPTURED", raw_secret: "TEST-secret" },
    { ...absent, extra: "TEST-secret" }])("rejects invalid present evidence without exposing its payload", (evidence) => {
    expect(() => mapOpportunity({ opportunity_id: "TEST-o", profile_version_id: "TEST-p",
      source_evidence: evidence })).toThrow("原文证据响应不完整，请重新读取。");
  });
  it("requires explicit evidence on detail, rather than inventing NOT_CAPTURED", async () => {
    detail({ opportunity_id: "TEST-o", profile_version_id: "TEST-p" });
    await expect(service.opportunity("TEST-o")).rejects.toMatchObject({
      code: "INVALID_SERVICE_RESPONSE", message: "原文证据响应不完整，请重新读取。",
    });
  });
  it("rejects a different opportunity returned by the detail endpoint", async () => {
    detail({ opportunity_id: "TEST-other", profile_version_id: "TEST-p", source_evidence: absent });
    await expect(service.opportunity("TEST-o")).rejects.toMatchObject({ code: "INVALID_SERVICE_RESPONSE" });
  });
  it("preserves explicit absence from a successful native detail read", async () => {
    const requestApi = detail({ opportunity_id: "TEST-o", profile_version_id: "TEST-p", source_evidence: absent });
    await expect(service.opportunity("TEST-o")).resolves.toMatchObject({ sourceEvidence: absent });
    expect(requestApi).toHaveBeenCalledWith({ operation: "opportunities.get", payload: { id: "TEST-o" } });
  });
  it("passes cancellation to the actual browser GET", async () => {
    const controller = new AbortController();
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ opportunity: {
      opportunity_id: "TEST-o", profile_version_id: "TEST-p", source_evidence: absent,
    } }), { headers: { "content-type": "application/json" } }));
    vi.stubGlobal("fetch", fetcher);
    await service.opportunity("TEST-o", controller.signal);
    expect(fetcher).toHaveBeenCalledWith("/api/ui/opportunities/TEST-o?evidenceVersion=1", expect.objectContaining({
      signal: controller.signal, method: "GET", body: undefined,
    }));
  });
  it("does not dispatch an already canceled native read", async () => {
    const requestApi = detail({ opportunity_id: "TEST-o", profile_version_id: "TEST-p", source_evidence: absent });
    const controller = new AbortController();
    controller.abort();
    await expect(service.opportunity("TEST-o", controller.signal)).rejects.toMatchObject({ name: "AbortError" });
    expect(requestApi).not.toHaveBeenCalled();
  });
  it("discards a native reply after cancellation without claiming to cancel IPC", async () => {
    let resolve!: (value: unknown) => void;
    const requestApi = vi.fn(() => new Promise((done) => { resolve = done; }));
    host.yikeDesktop = { requestApi } as unknown as YikeDesktopApi;
    const controller = new AbortController();
    const pending = service.opportunity("TEST-o", controller.signal);
    controller.abort();
    resolve({ ok: true, status: 200, data: { opportunity: {
      opportunity_id: "TEST-o", profile_version_id: "TEST-p", source_evidence: absent,
    } } });
    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
    expect(requestApi).toHaveBeenCalledTimes(1);
  });
});
