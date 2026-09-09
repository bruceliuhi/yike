import { describe, expect, it } from "vitest";
import {
  candidateQuerySchema,
  candidateReviewRequestSchema,
  sourceVerificationRequestSchema,
  parseCandidatePage,
  parseCandidateReviewResult,
} from "../src/shared/candidateReviewApi";
import {
  candidateBinding,
  assessmentFixture,
  assessmentRequestFixture,
  verificationRequestFixture,
  verificationFixture,
  decisionRequestFixture,
  decisionFixture,
  pageFixture,
  candidateFixture,
} from "./fixtures/candidateReviewApi";

describe("strict candidate requests", () => {
  it("accepts precise query bounds and original-request lookup", () => {
    expect(
      candidateQuerySchema.parse({
        page: 999999999,
        pageSize: 100,
        query: "🙂".repeat(200),
      }),
    ).toMatchObject({ page: 999999999 });
    const q = {
      ids: [candidateBinding.candidateId],
      page: 1,
      pageSize: 1,
      reviewRequestId: "a.b:c-1",
    };
    expect(candidateQuerySchema.parse(q)).toEqual(q);
  });
  it.each([
    { query: " " },
    { query: "🙂".repeat(201) },
    { platform: "小红书" },
    { page: 0 },
    { page: 1000000000 },
    { pageSize: 101 },
    { page: "1" },
    { ids: [] },
    { ids: [candidateBinding.candidateId, candidateBinding.candidateId] },
    { ids: [candidateBinding.candidateId.toUpperCase().replace("1", "A")] },
    {
      ids: [candidateBinding.candidateId],
      reviewRequestId: "a",
      page: 1,
      pageSize: 20,
    },
    { reviewRequestId: "a/b" },
    { tenant: "forged" },
  ])("rejects invalid query %#", (q) =>
    expect(candidateQuerySchema.safeParse(q).success).toBe(false),
  );
  it("preserves all three decision/assessment inputs and nullable explicit retry", () => {
    for (const value of [
      assessmentRequestFixture(),
      { ...assessmentRequestFixture(), retryOf: null },
      { ...assessmentRequestFixture(), retryOf: "original:1" },
      decisionRequestFixture(),
      {
        ...decisionRequestFixture(),
        action: "EXCLUDE",
        sourceVerificationId: null,
      },
    ])
      expect(candidateReviewRequestSchema.parse(value)).toEqual(value);
    const v = verificationRequestFixture();
    expect(sourceVerificationRequestSchema.parse(v)).toEqual(v);
  });
  it.each([
    { ...decisionRequestFixture(), sourceVerificationId: null },
    { ...decisionRequestFixture(), humanConfirmed: 1 },
    { ...decisionRequestFixture(), action: "EXCLUDE", reason: "\t" },
    { ...assessmentRequestFixture(), requestId: "../bad" },
    { ...assessmentRequestFixture(), candidateRevision: 1.2 },
    { ...assessmentRequestFixture(), profileVersion: "3" },
    { ...decisionRequestFixture(), reason: "\uD800" },
    {
      ...decisionRequestFixture(),
      evidence: { ...decisionRequestFixture().evidence, risk: "\0" },
    },
    { ...assessmentRequestFixture(), tenant: "forged" },
  ])("rejects invalid write %#", (v) =>
    expect(candidateReviewRequestSchema.safeParse(v).success).toBe(false),
  );
  it("uses codepoints, preserves text, and caps serialized UTF-8", () => {
    const request = decisionRequestFixture();
    request.evidence.risk = "🙂".repeat(2000);
    expect(candidateReviewRequestSchema.parse(request)).toEqual(request);
    request.evidence = Object.fromEntries(
      Object.keys(request.evidence).map((k) => [k, "\u0001".repeat(2000)]),
    ) as typeof request.evidence;
    request.reason = "\u0001".repeat(2000);
    expect(
      new TextEncoder().encode(JSON.stringify(request)).length,
    ).toBeGreaterThan(65536);
    expect(candidateReviewRequestSchema.safeParse(request).success).toBe(false);
    expect(
      sourceVerificationRequestSchema.safeParse({
        ...verificationRequestFixture(),
        checkedBy: "forged",
      }).success,
    ).toBe(false);
  });
});
describe("complete candidate results", () => {
  it("retains original Unicode/unknown source time and rich assessment", () => {
    const page = pageFixture();
    expect(parseCandidatePage(page, {})).toEqual(page);
    const result = {
      kind: "assessment",
      requestId: "TEST.assess:1",
      candidateId: candidateBinding.candidateId,
      assessment: assessmentFixture(),
    };
    expect(
      parseCandidateReviewResult(result, {
        requestId: result.requestId,
        request: assessmentRequestFixture(),
      }),
    ).toEqual(result);
  });
  it("preserves the backend title fallback when body begins with whitespace", () => {
    const candidate = {
      ...candidateFixture(),
      title: " ".repeat(120),
      excerpt: " ".repeat(120) + "原文",
    };
    const page = { ...pageFixture(), items: [candidate] };
    expect(parseCandidatePage(page, {})).toEqual(page);
  });
  it("accepts all real UNKNOWN/failure/cache-alias forms without invented binding", () => {
    for (const body of [
      { kind: "pending", status: "PROCESSING" },
      { kind: "pending", status: "UNKNOWN" },
      { kind: "pending", status: "UNKNOWN", code: "assessment_unknown" },
      { kind: "failure", status: "FAILED", code: "assessment_failed" },
    ]) {
      for (const alias of [{}, { invocationRequestId: "original:1" }]) {
        const result = {
          ...body,
          ...alias,
          requestId: "alias:1",
          candidateId: candidateBinding.candidateId,
        };
        expect(
          parseCandidateReviewResult(result, {
            requestId: result.requestId,
            binding: candidateBinding,
          }),
        ).toEqual(result);
      }
    }
  });
  it("checks human source verification against its exact original request", () => {
    const v = verificationFixture();
    expect(
      parseCandidateReviewResult(v, {
        requestId: v.requestId,
        request: verificationRequestFixture(),
      }),
    ).toEqual(v);
    expect(() =>
      parseCandidateReviewResult(
        { ...v, excerpt: "other" },
        { requestId: v.requestId, request: verificationRequestFixture() },
      ),
    ).toThrow("INVALID_CANDIDATE_REVIEW_RESULT");
  });
  it("checks INCLUDE confirmation including source verification while reading old receipts", () => {
    const result = decisionFixture();
    expect(
      parseCandidateReviewResult(result, {
        requestId: result.requestId,
        request: decisionRequestFixture(),
      }),
    ).toEqual(result);
    const legacy = structuredClone(result);
    Reflect.deleteProperty(legacy.receipt.review, "sourceVerificationId");
    Reflect.deleteProperty(
      legacy.candidate.lastReview.review,
      "sourceVerificationId",
    );
    expect(
      parseCandidateReviewResult(legacy, { requestId: legacy.requestId }),
    ).toEqual(legacy);
    expect(() =>
      parseCandidateReviewResult(legacy, {
        requestId: legacy.requestId,
        request: decisionRequestFixture(),
      }),
    ).toThrow("INVALID_CANDIDATE_REVIEW_RESULT");
  });
  it("reads historical binding without making it current", () => {
    const candidate = {
      ...decisionFixture().candidate,
      historical: true,
      currentBindingValid: false,
      assessmentStale: true,
    };
    const p = { ...pageFixture(), items: [candidate], pageSize: 1 };
    expect(
      parseCandidatePage(p, {
        ids: [candidate.id],
        reviewRequestId: candidate.lastReview.requestId,
        page: 1,
        pageSize: 1,
      }),
    ).toEqual(p);
    const stale = {
      ...candidateFixture(),
      currentBindingValid: false,
      assessmentStale: false,
    };
    expect(
      parseCandidatePage({ ...pageFixture(), items: [stale] }, {}),
    ).toMatchObject({ items: [stale] });
  });
  it.each([
    { ...pageFixture(), page: 2 },
    { ...pageFixture(), pageSize: 10 },
    { ...pageFixture(), total: 0 },
    { ...pageFixture(), items: [candidateFixture(), candidateFixture()] },
    { ...pageFixture(), items: [{ ...candidateFixture(), sample: true }] },
    { ...pageFixture(), items: [{ ...candidateFixture(), excerpt: "\uD800" }] },
    { ...pageFixture(), items: [{ ...candidateFixture(), unexpected: "x" }] },
    {
      ...pageFixture(),
      items: [{ ...candidateFixture(), profileId: undefined }],
    },
  ])("rejects malformed page %# with a fixed error", (p) =>
    expect(() => parseCandidatePage(p, {})).toThrow("INVALID_CANDIDATE_PAGE"),
  );
  it("rejects mismatched result identities, bindings, action, and fake sending authority", () => {
    const request = assessmentRequestFixture();
    const expected = { requestId: request.requestId, request };
    const a = {
      kind: "assessment",
      requestId: request.requestId,
      candidateId: request.candidateId,
      assessment: assessmentFixture(),
    };
    for (const bad of [
      { ...a, requestId: "other" },
      { ...a, candidateId: request.profileId },
      { ...a, assessment: { ...a.assessment, profileVersion: 4 } },
      { ...a, assessment: { ...a.assessment, sendingAuthorized: true } },
      {
        ...a,
        assessment: { ...a.assessment, effectiveDecision: "SEND_READY" },
      },
      { ...a, secret: "private" },
    ])
      expect(() => parseCandidateReviewResult(bad, expected)).toThrow(
        "INVALID_CANDIDATE_REVIEW_RESULT",
      );
    expect(() =>
      parseCandidateReviewResult(a, {
        ...expected,
        candidateId: request.profileId,
      }),
    ).toThrow("INVALID_CANDIDATE_REVIEW_RESULT");
    expect(() =>
      parseCandidateReviewResult(decisionFixture(), {
        requestId: decisionFixture().requestId,
        request: { ...request, requestId: decisionFixture().requestId },
      }),
    ).toThrow("INVALID_CANDIDATE_REVIEW_RESULT");
  });
  it("does not let a stale flag hide contradictory nested decision evidence", () => {
    const result = decisionFixture();
    result.candidate.assessmentStale = true;
    result.candidate.assessment.profileVersion += 1;
    expect(() =>
      parseCandidateReviewResult(result, { requestId: result.requestId }),
    ).toThrow("INVALID_CANDIDATE_REVIEW_RESULT");
  });
  it("rejects mixed assessment versions in a historical page too", () => {
    const candidate = {
      ...decisionFixture().candidate,
      historical: true,
      assessmentStale: true,
      currentBindingValid: false,
    };
    candidate.assessment.profileVersion += 1;
    expect(() =>
      parseCandidatePage({ ...pageFixture(), items: [candidate] }, {}),
    ).toThrow("INVALID_CANDIDATE_PAGE");
  });
  it("uses Python whitespace semantics without trimming drafts or actor identities", () => {
    const a = assessmentFixture();
    a.draftComment = "same";
    a.draftDm = "\uFEFFsame";
    const result = {
      kind: "assessment",
      requestId: "assess:1",
      candidateId: candidateBinding.candidateId,
      assessment: a,
    };
    expect(
      parseCandidateReviewResult(result, { requestId: result.requestId }),
    ).toEqual(result);
    const v = { ...verificationFixture(), checkedBy: "\uFEFFowner" };
    expect(parseCandidateReviewResult(v, { requestId: v.requestId })).toEqual(
      v,
    );
  });
});
