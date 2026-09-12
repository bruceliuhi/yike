import { describe, expect, it } from "vitest";
import { configureCandidateReviewVisual } from "./candidate-review";
import { createVisualService } from "./service";
import { candidateBinding, assessmentRequestFixture, decisionRequestFixture, verificationRequestFixture } from "../fixtures/candidateReviewApi";
import { rawEvidenceBinding } from "../fixtures/rawCandidateEvidence";
import { candidateReviewRequestSchema } from "../../src/shared/candidateReviewApi";

function setup(mode = "live") {
  const harness = createVisualService();
  configureCandidateReviewVisual(harness.service, new URLSearchParams(`scenario=P07&candidateReview=${mode}`), harness.record);
  return harness;
}

describe("TEST-only P07 candidate review adapter transport", () => {
  it("offers synthetic dynamic page evidence without changing its unknown raw author/date", async () => {
    const {service} = setup("dynamic");
    const raw = await service.rawCandidateEvidence!({...rawEvidenceBinding});
    expect(raw.candidate.kind).toBe("PAGE");
    expect(raw.candidate.current_version.published_at).toBeNull();
    expect(raw.observations.items[0].normalizer_version).toBe("dynamic-public-read-v1");
    const proof = {schemaVersion:"human-demand-evidence-v1",authorLocator:"TEST采购人，第2楼",
      authorExcerpt:"TEST采购人",demandExcerpt:"采购输送设备，需要报价。",
      publishedDate:new Date(Date.now()-86_400_000).toISOString().slice(0,10),dateExcerpt:"TEST原文日期"};
    const receipt = await service.candidateReview!.verifySource({...verificationRequestFixture(),demandEvidence:proof});
    expect(receipt.demandEvidence).toEqual(proof);
    expect(await service.candidateReview!.review(assessmentRequestFixture())).toMatchObject({
      kind:"assessment",assessment:{demandEvidenceId:receipt.id},
    });
  });
  it("requires an explicit isolated P07/populated scenario and refuses unsafe combinations", () => {
    const harness = createVisualService();
    expect(configureCandidateReviewVisual(harness.service, new URLSearchParams("scenario=P07"), harness.record)).toBe(false);
    for (const query of ["candidateReview=live", "scenario=P11&candidateReview=live", "scenario=P07&candidateReview=other", "scenario=P07&candidateReview=live&session=guest", "scenario=P07&candidateReview=live&state=empty", "scenario=P07&candidateReview=live&reference=r3", "scenario=P07&candidateReview=live&suite=r4", "scenario=P07&candidateReview=live&candidateReview=recovery"])
      expect(() => configureCandidateReviewVisual(harness.service, new URLSearchParams(query), harness.record)).toThrow(/TEST/);
    expect(configureCandidateReviewVisual(harness.service, new URLSearchParams("scenario=P07&candidateReview=live&state=populated"), harness.record)).toBe(true);
  });

  it("uses strict raw COMMENT fixtures and performs ASSESS, VERIFY, INCLUDE through the actual adapter", async () => {
    const { service, events } = setup();
    const api = service.candidateReview!;
    const [candidate] = (await service.candidates()).items;
    expect(candidate.title).toContain("TEST");
    expect(await service.profiles()).toMatchObject([{ id: candidateBinding.profileId, version: 3, status: "CONFIRMED" }]);
    const raw = await service.rawCandidateEvidence!({ ...rawEvidenceBinding });
    expect(raw.candidate.kind).toBe("COMMENT");
    expect(raw.candidate.current_version.body).toContain("采购输送设备");
    expect(raw.candidate.current_version.title).toContain("不是评论人的采购意向");
    expect(raw.candidate.current_version.parent!.body).toContain("不属于当前作者");
    expect(Date.parse(raw.candidate.current_version.published_at!)).toBeLessThan(Date.now());
    expect(await api.review(assessmentRequestFixture())).toMatchObject({ kind: "assessment", assessment: { sendingAuthorized: false } });
    const verification = await api.verifySource(verificationRequestFixture());
    expect(Math.abs(Date.now() - Date.parse(verification.checkedAt))).toBeLessThan(24 * 60 * 60 * 1000);
    const request = candidateReviewRequestSchema.parse({ ...decisionRequestFixture(), sourceVerificationId: verification.id });
    const result = await api.review(request);
    expect(result).toMatchObject({ kind: "decision", receipt: { review: { sourceVerificationId: verification.id } } });
    expect(await api.getRequest(request.requestId, { request })).toEqual(result);
    expect((await api.list({ status: "IMPORTED" })).items).toHaveLength(1);
    expect(events.map(event => event.operation)).toEqual(expect.arrayContaining(["candidateReview.ASSESS", "candidateReview.VERIFY", "candidateReview.INCLUDE"]));
    await service.openExternal("https://example.com/TEST");
    expect(events.at(-1)).toMatchObject({ operation: "openExternal", detail: expect.stringContaining("拦截") });
  });

  it("persists a lost decision response and recovers the identical original receipt by GET only", async () => {
    const { service, events } = setup("recovery");
    const api = service.candidateReview!;
    await api.review(assessmentRequestFixture());
    const verification = await api.verifySource(verificationRequestFixture());
    const request = candidateReviewRequestSchema.parse({ ...decisionRequestFixture(), sourceVerificationId: verification.id });
    await expect(api.review(request)).rejects.toMatchObject({ code: "NETWORK_ERROR" });
    const result = await api.getRequest(request.requestId, { request });
    expect(result).toMatchObject({ kind: "decision", receipt: { requestId: request.requestId, review: { sourceVerificationId: verification.id } } });
    expect(events.filter(event => event.operation === "candidateReview.INCLUDE")).toHaveLength(1);
    expect((await api.list({ ids: [candidateBinding.candidateId], pageSize: 1, reviewRequestId: request.requestId })).items[0]).toMatchObject({ historical: true, status: "IMPORTED" });
  });

  it("isolates raw GET failures while other strict operations and exclusion remain available", async () => {
    const { service } = setup("raw-error");
    const api = service.candidateReview!;
    const [candidate] = (await api.list()).items;
    await expect(api.getRawEvidence({ ...rawEvidenceBinding })).rejects.toMatchObject({ code: "VISUAL_TEST_RAW_ERROR" });
    await api.review(assessmentRequestFixture());
    const { sourceVerificationId: _source, ...request } = decisionRequestFixture();
    expect(await api.review({ ...request, action: "EXCLUDE", reason: "TEST 人工排除" })).toMatchObject({ kind: "decision", receipt: { outcome: "EXCLUDED", review: { sourceVerificationId: null } } });
  });

  it("filters and paginates without leaking mutations or allowing foreign binding writes", async () => {
    const { service } = setup();
    const api = service.candidateReview!;
    const page = await api.list();
    page.items[0].title = "caller mutation";
    expect((await api.list()).items[0].title).toContain("TEST");
    for (const query of [{ query: "nothing matches TEST" }, { platform: "DOUYIN" }, { status: "EXCLUDED" }, { ids: ["99999999-9999-4999-8999-999999999999"] }])
      expect(await api.list(query)).toMatchObject({ items: [], total: 0 });
    expect(await api.list({ page: 2, pageSize: 1 })).toMatchObject({ items: [], total: 1, page: 2, pageSize: 1 });
    await expect(api.review({ ...assessmentRequestFixture(), profileVersion: 9 })).rejects.toMatchObject({ code: "VISUAL_TEST_BINDING_MISMATCH" });
    await expect(api.getRequest("TEST.unknown")).rejects.toMatchObject({ status: 404 });
  });

  it("maps only the legacy page view labels like the production client, retaining strict API platform identifiers", async () => {
    const { service } = setup();
    expect((await service.candidates({ platform: "公开网站" })).items[0]).toMatchObject({ platform: "公开网站", sourceLabel: "公开网站" });
    expect((await service.candidateReview!.list()).items[0]).toMatchObject({ platform: "PUBLIC_WEB", sourceLabel: "PUBLIC_WEB" });
  });
});
