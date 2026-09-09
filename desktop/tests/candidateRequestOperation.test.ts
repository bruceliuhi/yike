import { describe, expect, it } from "vitest";
import {
  candidateRequestDigest,
  newCandidateRequestOperation,
  parseCandidateRequestOperation,
  candidateRequestEntry,
  validCandidateRequestEntry,
  recoverCandidateRequestResult,
  type CandidateRequestOperation,
} from "../src/renderer/domain/candidateRequestOperation";
import {
  assessmentFixture,
  assessmentRequestFixture,
  candidateBinding,
  candidateFixture,
  decisionFixture,
  decisionRequestFixture,
  verificationFixture,
  verificationRequestFixture,
  verificationId,
} from "./fixtures/candidateReviewApi";

const scope = { id: "TEST.customer", version: 2 };
const binding = [
  candidateBinding.candidateRevision,
  candidateBinding.sourceVersionId,
  candidateBinding.profileId,
  candidateBinding.profileVersion,
];
const failure = "INVALID_CANDIDATE_REQUEST_OPERATION";
function assessmentResult(extra: Record<string, unknown> = {}) {
  return {
    kind: "assessment",
    requestId: assessmentRequestFixture().requestId,
    candidateId: candidateBinding.candidateId,
    assessment: assessmentFixture(),
    ...extra,
  };
}
function excludeRequest(presence: "omitted" | "null" | "uuid") {
  const { sourceVerificationId: _verification, ...request } = decisionRequestFixture();
  return {
    ...request, action: "EXCLUDE", requestId: "TEST.exclude:1",
    ...(presence === "omitted" ? {} : { sourceVerificationId: presence === "null" ? null : verificationId }),
  };
}
function excludeResult(presence: "omitted" | "null" | "uuid") {
  const { candidateId: _candidate, requestId, action, humanConfirmed: _human, ...review } = excludeRequest(presence);
  const receipt = {
    ...decisionFixture().receipt, requestId, action, outcome: "EXCLUDED",
    review: { ...review, sourceVerificationId: presence === "uuid" ? verificationId : null },
  };
  const { opportunityId: _opportunity, ...withoutOpportunity } = receipt;
  return {
    kind: "decision", requestId,
    receipt: withoutOpportunity,
    candidate: {
      ...candidateFixture(), status: "EXCLUDED", assessment: assessmentFixture(),
      lastReview: withoutOpportunity,
    },
  };
}
function frozen<T>(value: T): T {
  if (value && typeof value === "object") {
    Object.values(value).forEach(frozen);
    Object.freeze(value);
  }
  return value;
}

describe("opaque candidate request records", () => {
  it.each([
    ["ASSESS", assessmentRequestFixture()],
    ["VERIFY_SOURCE", verificationRequestFixture()],
    ["INCLUDE", decisionRequestFixture()],
    ["EXCLUDE", excludeRequest("omitted")],
  ])("round-trips the original %s request without raw content", async (action, request) => {
    const original = structuredClone(request);
    const op = await newCandidateRequestOperation(frozen(request), scope);
    expect(op).toMatchObject({
      scopeId: scope.id, scopeVersion: scope.version, action, v: 1,
      candidateId: request.candidateId, requestId: request.requestId,
      binding, state: "PENDING", invocationId: null,
    });
    expect(op.key).toBe(JSON.stringify([scope.id, scope.version, request.candidateId, request.requestId]));
    expect(op.requestHash).toMatch(/^[a-f0-9]{64}$/);
    const entry = candidateRequestEntry(op);
    expect(validCandidateRequestEntry(entry.key, entry.value)).toBe(true);
    expect(parseCandidateRequestOperation(entry.key, entry.value)).toEqual(op);
    expect(Object.keys(JSON.parse(entry.value)).sort()).toEqual([
      "v", "action", "binding", "requestHash", "assessmentId", "verification", "retryOf", "invocationId", "state",
    ].sort());
    for (const field of ["evidence", "excerpt", "locator", "reason", "humanConfirmed", "receipt", "recipient", "credentials", "body"])
      expect(entry.value).not.toContain(`"${field}"`);
    for (const secret of ["采购输送设备", "人工核对", "https://example.com/synthetic"])
      expect(entry.value).not.toContain(secret);
    expect(request).toEqual(original);
  });

  it("keeps null scope paired and distinguishes customer versions", async () => {
    const request = assessmentRequestFixture();
    const local = await newCandidateRequestOperation(request, null);
    expect([local.scopeId, local.scopeVersion]).toEqual([null, null]);
    expect(local.key).toBe(JSON.stringify([null, null, request.candidateId, request.requestId]));
    const first = await newCandidateRequestOperation(request, scope);
    const next = await newCandidateRequestOperation(request, { ...scope, version: 3 });
    expect(first.key).not.toBe(next.key);
    expect(first.requestHash).toBe(next.requestHash);
  });

  it.each(["omitted", "null", "uuid"] as const)("preserves EXCLUDE verification %s", async (presence) => {
    const op = await newCandidateRequestOperation(excludeRequest(presence), scope);
    expect(op.verification).toEqual(presence === "omitted" ? [] : [presence === "null" ? null : verificationId]);
  });

  it("hashes optional presence exactly but normalizes undefined as JSON omission", async () => {
    const request = assessmentRequestFixture();
    const omitted = await newCandidateRequestOperation(request, scope);
    const nil = await newCandidateRequestOperation({ ...request, retryOf: null }, scope);
    const known = await newCandidateRequestOperation({ ...request, retryOf: "TEST.original" }, scope);
    expect([omitted.retryOf, nil.retryOf, known.retryOf]).toEqual([[], [null], ["TEST.original"]]);
    expect(new Set([omitted.requestHash, nil.requestHash, known.requestHash]).size).toBe(3);
    expect(await candidateRequestDigest({ ...request, retryOf: undefined })).toBe(omitted.requestHash);
    const exclude = excludeRequest("omitted");
    const hashes = await Promise.all(["omitted", "null", "uuid"].map(p => candidateRequestDigest(excludeRequest(p as "omitted" | "null" | "uuid"))));
    expect(new Set(hashes).size).toBe(3);
    expect(await candidateRequestDigest({ ...exclude, sourceVerificationId: undefined })).toBe(hashes[0]);
  });

  it("uses canonical object order and exact request values", async () => {
    const request = decisionRequestFixture();
    const reordered: Record<string, unknown> = Object.fromEntries(Object.entries(request).reverse());
    reordered.evidence = Object.fromEntries(Object.entries(request.evidence).reverse());
    expect(await candidateRequestDigest(reordered)).toBe(await candidateRequestDigest(request));
    const variants = [
      { ...request, requestId: "TEST.include:2" },
      { ...request, action: "EXCLUDE" },
      { ...request, candidateRevision: 3 },
      { ...request, profileVersion: 4 },
      { ...request, reason: `${request.reason} ` },
      { ...request, evidence: { ...request.evidence, risk: "另一风险" } },
      { ...request, sourceVerificationId: "88888888-8888-4888-8888-888888888888" },
    ];
    for (const variant of variants)
      expect(await candidateRequestDigest(variant)).not.toBe(await candidateRequestDigest(request));
  });

  it.each([
    null, {}, { ...assessmentRequestFixture(), requestId: "bad/id" },
    { ...decisionRequestFixture(), sourceVerificationId: undefined },
    { ...decisionRequestFixture(), humanConfirmed: false },
    { ...verificationRequestFixture(), action: "VERIFY_SOURCE" },
    { ...assessmentRequestFixture(), token: "sensitive" },
    { ...assessmentRequestFixture(), profileVersion: Number.MAX_SAFE_INTEGER + 1 },
  ])("rejects invalid original input %# without echoing it", async input => {
    await expect(candidateRequestDigest(input)).rejects.toThrow(failure);
    await expect(newCandidateRequestOperation(input, scope)).rejects.toThrow(failure);
  });

  it.each([
    { id: "", version: 1 }, { id: "bad\n", version: 1 },
    { id: "bad\u200b", version: 1 }, { id: "x".repeat(129), version: 1 },
    { id: "valid", version: 0 }, { id: "valid", version: Number.MAX_SAFE_INTEGER + 1 },
    { id: "valid", version: 1, userId: "injected" },
  ])("rejects invalid scope %#", async badScope => {
    await expect(newCandidateRequestOperation(assessmentRequestFixture(), badScope)).rejects.toThrow(failure);
  });

  it("rejects corrupt, unknown, oversized and cross-action persisted fields", async () => {
    const op = await newCandidateRequestOperation(assessmentRequestFixture(), scope);
    const entry = candidateRequestEntry(op);
    const value = JSON.parse(entry.value);
    const variants = [
      { ...value, v: 2 }, { ...value, body: "private" },
      { ...value, requestHash: "x".repeat(64) }, { ...value, binding: [0, ...binding.slice(1)] },
      { ...value, binding: [2, "BAD", binding[2], 3] }, { ...value, binding: [...binding, 4] },
      { ...value, assessmentId: verificationId }, { ...value, verification: [verificationId] },
      { ...value, retryOf: [null, null] }, { ...value, retryOf: ["bad/id"] },
      { ...value, invocationId: "bad/id" }, { ...value, state: "SUCCESS" },
      { ...value, action: "VERIFY_SOURCE", invocationId: "TEST.original" },
      { ...value, action: "VERIFY_SOURCE", retryOf: [null] },
      { ...value, action: "VERIFY_SOURCE", state: "PROCESSING" },
      { ...value, action: "VERIFY_SOURCE", state: "FAILED" },
      { ...value, action: "INCLUDE" },
      { ...value, action: "EXCLUDE" },
    ];
    for (const variant of variants)
      expect(parseCandidateRequestOperation(entry.key, JSON.stringify(variant))).toBeNull();
    for (const field of Object.keys(value)) {
      const missing = { ...value }; delete missing[field];
      expect(parseCandidateRequestOperation(entry.key, JSON.stringify(missing))).toBeNull();
    }
    const invalidKeys = ["{}", "[]", "invalid", entry.key + " ",
      JSON.stringify([scope.id, null, op.candidateId, op.requestId]),
      JSON.stringify([null, 1, op.candidateId, op.requestId]),
      JSON.stringify([scope.id, 1, "bad", op.requestId]),
      JSON.stringify([scope.id, 1, op.candidateId, "bad/id"]),
      " ".repeat(1025),
    ];
    for (const key of invalidKeys) expect(validCandidateRequestEntry(key, entry.value)).toBe(false);
    expect(parseCandidateRequestOperation(entry.key, " ".repeat(4097))).toBeNull();
    expect(parseCandidateRequestOperation(entry.key, "null")).toBeNull();
    expect(parseCandidateRequestOperation(entry.key, "[")).toBeNull();
    expect(() => candidateRequestEntry({ ...op, scopeVersion: 99 })).toThrow(failure);
    expect(() => candidateRequestEntry({ ...op, secret: "private" } as CandidateRequestOperation)).toThrow(failure);
  });

  it("allows only assessment PROCESSING/FAILED and all-action transport UNKNOWN", async () => {
    for (const request of [assessmentRequestFixture(), verificationRequestFixture(), decisionRequestFixture(), excludeRequest("null")]) {
      const op = await newCandidateRequestOperation(request, scope);
      for (const state of ["PENDING", "UNKNOWN", "RECORDED"] as const) {
        const entry = candidateRequestEntry({ ...op, state });
        expect(validCandidateRequestEntry(entry.key, entry.value)).toBe(true);
      }
      if (op.action !== "ASSESS") {
        for (const state of ["PROCESSING", "FAILED"] as const)
          expect(() => candidateRequestEntry({ ...op, state })).toThrow(failure);
      }
    }
  });
});

describe("strict original candidate request recovery", () => {
  it.each([
    [assessmentRequestFixture(), assessmentResult(), "RECORDED"],
    [assessmentRequestFixture(), { kind: "pending", status: "PROCESSING", requestId: "TEST.assess:1", candidateId: candidateBinding.candidateId }, "PROCESSING"],
    [assessmentRequestFixture(), { kind: "pending", status: "UNKNOWN", code: "assessment_unknown", requestId: "TEST.assess:1", candidateId: candidateBinding.candidateId }, "UNKNOWN"],
    [assessmentRequestFixture(), { kind: "failure", status: "FAILED", code: "assessment_failed", requestId: "TEST.assess:1", candidateId: candidateBinding.candidateId }, "FAILED"],
    [verificationRequestFixture(), verificationFixture(), "RECORDED"],
    [decisionRequestFixture(), decisionFixture(), "RECORDED"],
    [excludeRequest("omitted"), excludeResult("omitted"), "RECORDED"],
    [excludeRequest("null"), excludeResult("null"), "RECORDED"],
    [excludeRequest("uuid"), excludeResult("uuid"), "RECORDED"],
  ])("recovers real result %# without changing raw or original operation", async (request, raw, state) => {
    const op = frozen(await newCandidateRequestOperation(request, scope));
    const original = structuredClone(op);
    const rawOriginal = structuredClone(raw);
    const recovered = await recoverCandidateRequestResult(frozen(raw), op);
    expect(recovered.result).toEqual(rawOriginal);
    expect(recovered.operation).toEqual({ ...op, state,
      invocationId: op.action === "ASSESS" ? op.requestId : null });
    expect(recovered.operation.key).toBe(op.key);
    expect(op).toEqual(original);
    expect(raw).toEqual(rawOriginal);
    if (raw.kind === "pending" || raw.kind === "failure")
      expect(recovered.result).not.toHaveProperty("binding");
  });

  it.each([undefined, null, "TEST.original"])("recovers assessment retry presence %s", async retryOf => {
    const op = await newCandidateRequestOperation({ ...assessmentRequestFixture(), retryOf }, scope);
    expect((await recoverCandidateRequestResult(assessmentResult(), op)).operation.requestHash).toBe(op.requestHash);
  });

  it("preserves invocation aliases as metadata, never as original request identity", async () => {
    const op = await newCandidateRequestOperation(assessmentRequestFixture(), scope);
    const raw = assessmentResult({ invocationRequestId: "TEST.original.invocation" });
    const first = await recoverCandidateRequestResult(raw, op);
    expect(first.result).toEqual(raw);
    expect(first.operation).toMatchObject({ requestId: op.requestId, key: op.key, invocationId: "TEST.original.invocation" });
    expect((await recoverCandidateRequestResult(raw, first.operation)).operation).toEqual(first.operation);
    await expect(recoverCandidateRequestResult(assessmentResult({ invocationRequestId: "TEST.changed" }), first.operation)).rejects.toThrow(failure);
    await expect(recoverCandidateRequestResult(assessmentResult({ requestId: "TEST.other", invocationRequestId: op.requestId }), op)).rejects.toThrow(failure);
  });

  it.each(["RECORDED", "FAILED"] as const)("does not replace terminal %s with a contradictory later result", async terminalState => {
    const op = await newCandidateRequestOperation(assessmentRequestFixture(), scope);
    const failed = { kind: "failure", status: "FAILED", code: "assessment_failed", requestId: op.requestId, candidateId: op.candidateId };
    const originalResult = terminalState === "RECORDED" ? assessmentResult() : failed;
    const recorded = (await recoverCandidateRequestResult(originalResult, op)).operation;
    expect((await recoverCandidateRequestResult(originalResult, recorded)).operation).toEqual(recorded);
    const contradictory = terminalState === "RECORDED" ? failed : assessmentResult();
    for (const raw of [contradictory,
      { kind: "pending", status: "PROCESSING", requestId: op.requestId, candidateId: op.candidateId },
      { kind: "pending", status: "UNKNOWN", requestId: op.requestId, candidateId: op.candidateId },
    ]) await expect(recoverCandidateRequestResult(raw, frozen(recorded))).rejects.toThrow(failure);
    expect(recorded.state).toBe(terminalState);
  });

  it("rejects changed identities, bindings, action or stored hash without adoption", async () => {
    const op = frozen(await newCandidateRequestOperation(assessmentRequestFixture(), scope));
    for (const raw of [
      assessmentResult({ requestId: "TEST.other" }),
      assessmentResult({ candidateId: verificationId }),
      assessmentResult({ assessment: { ...assessmentFixture(), candidateRevision: 3 } }),
      assessmentResult({ assessment: { ...assessmentFixture(), profileVersion: 4 } }),
      assessmentResult({ assessment: { ...assessmentFixture(), sourceVersionId: verificationId } }),
      assessmentResult({ assessment: { ...assessmentFixture(), profileId: verificationId } }),
      assessmentResult({ extra: "private" }),
      verificationFixture(), decisionFixture(),
    ]) await expect(recoverCandidateRequestResult(raw, op)).rejects.toThrow(failure);
    await expect(recoverCandidateRequestResult(assessmentResult(), { ...op, requestHash: "b".repeat(64) })).rejects.toThrow(failure);
    const pending = { kind: "pending", status: "UNKNOWN", requestId: op.requestId, candidateId: op.candidateId };
    await expect(recoverCandidateRequestResult(pending, { ...op, binding: [3, op.binding[1], op.binding[2], 3] })).rejects.toThrow(failure);
    expect(op.state).toBe("PENDING");
  });

  it("rejects pending and failure for non-assessment operations", async () => {
    for (const request of [verificationRequestFixture(), decisionRequestFixture(), excludeRequest("omitted")]) {
      const op = await newCandidateRequestOperation(request, scope);
      for (const raw of [{ kind: "pending", status: "UNKNOWN" }, { kind: "failure", status: "FAILED", code: "assessment_failed" }])
        await expect(recoverCandidateRequestResult({ ...raw, requestId: op.requestId, candidateId: op.candidateId }, op)).rejects.toThrow(failure);
    }
  });

  it.each(["status", "openingMethod", "locator", "excerpt", "contactMethod"])("checks original verification %s in the saved digest", async field => {
    const op = await newCandidateRequestOperation(verificationRequestFixture(), scope);
    const changed: Record<string, unknown> = { status: "BLOCKED", openingMethod: "IN_PLATFORM", locator: "other", excerpt: "other", contactMethod: "DM" };
    await expect(recoverCandidateRequestResult({ ...verificationFixture(), [field]: changed[field] }, op)).rejects.toThrow(failure);
  });

  it.each(["assessmentId", "reason", "evidence", "sourceVerificationId"])("checks original decision %s rather than learning it from a receipt", async field => {
    const request = decisionRequestFixture();
    const op = await newCandidateRequestOperation(request, scope);
    const result = decisionFixture();
    const changed = { ...result.receipt.review,
      [field]: field === "reason" ? "另一理由" : field === "evidence" ? { ...request.evidence, risk: "另一风险" } : "88888888-8888-4888-8888-888888888888" };
    const receipt = { ...result.receipt, review: changed };
    await expect(recoverCandidateRequestResult({ ...result, receipt,
      candidate: { ...result.candidate, lastReview: receipt,
        ...(field === "assessmentId" ? { assessment: { ...assessmentFixture(), id: changed.assessmentId } } : {}) } }, op)).rejects.toThrow(failure);
  });

  it("rejects old INCLUDE receipts without the original verification ID", async () => {
    const op = await newCandidateRequestOperation(decisionRequestFixture(), scope);
    const result = decisionFixture();
    const { sourceVerificationId: _verification, ...review } = result.receipt.review;
    const receipt = { ...result.receipt, review };
    await expect(recoverCandidateRequestResult({ ...result, receipt, candidate: { ...result.candidate, lastReview: receipt } }, op)).rejects.toThrow(failure);
  });

  it("accepts EXCLUDE normalized null only against its original presence fingerprint", async () => {
    for (const presence of ["omitted", "null"] as const) {
      const op = await newCandidateRequestOperation(excludeRequest(presence), scope);
      const result = excludeResult(presence);
      const { sourceVerificationId: _verification, ...review } = result.receipt.review;
      const oldReceipt = { ...result.receipt, review };
      await expect(recoverCandidateRequestResult({ ...result, receipt: oldReceipt,
        candidate: { ...result.candidate, lastReview: oldReceipt } }, op)).rejects.toThrow(failure);
      await expect(recoverCandidateRequestResult(excludeResult("uuid"), op)).rejects.toThrow(failure);
      await expect(recoverCandidateRequestResult(result, { ...op, verification: presence === "omitted" ? [null] : [] })).rejects.toThrow(failure);
    }
  });
});
