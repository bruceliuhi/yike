import { describe, expect, it } from "vitest";
import {
  candidateOperation,
  candidateReviewHash,
  matchingCandidateReceipt,
  parseCandidateOperation,
  type CandidateDecision,
} from "../../src/renderer/domain/candidateReviewOperation";
import { reviewSnapshot } from "../../src/renderer/domain/candidates";

const request: CandidateDecision = {
  action: "INCLUDE",
  candidateId: "TEST-candidate",
  candidateRevision: 2,
  sourceVersionId: "TEST-source-v2",
  profileId: "TEST-profile",
  profileVersion: 3,
  requestId: "TEST-review",
  assessmentId: "TEST-assessment",
  humanConfirmed: true,
  reason: "",
  evidence: {
    matchReason: "TEST 匹配",
    actionSignal: "TEST 信号",
    value: "TEST 价值",
    risk: "TEST 风险",
    unknowns: "TEST 未知",
  },
};
describe("candidate review operation binding", () => {
  it("stores only identifiers and SHA256, and accepts only the original confirmed receipt", async () => {
    const operation = await candidateOperation(request);
    expect(operation.key).not.toContain("TEST 匹配");
    expect(operation.reviewHash).toMatch(/^[a-f0-9]{64}$/);
    expect(
      await matchingCandidateReceipt(operation, {
        requestId: request.requestId,
        action: request.action,
        status: "FAILED",
        review: reviewSnapshot(request),
      }),
    ).toBe(true);
    expect(
      await matchingCandidateReceipt(operation, {
        requestId: "TEST-other",
        action: request.action,
        status: "FAILED",
        review: reviewSnapshot(request),
      }),
    ).toBe(false);
    expect(
      await matchingCandidateReceipt(operation, {
        requestId: request.requestId,
        action: "EXCLUDE",
        status: "FAILED",
        review: reviewSnapshot(request),
      }),
    ).toBe(false);
  });
  it("binds every confirmed revision, assessment, evidence field and reason", async () => {
    const snapshot = reviewSnapshot(request),
      hash = await candidateReviewHash(snapshot);
    for (const patch of [
      { candidateRevision: 3 },
      { sourceVersionId: "OTHER" },
      { profileId: "OTHER" },
      { profileVersion: 4 },
      { assessmentId: "OTHER" },
      { reason: "TEST changed" },
      ...Object.keys(snapshot.evidence).map((key) => ({
        evidence: { ...snapshot.evidence, [key]: "TEST changed" },
      })),
    ]) {
      expect(await candidateReviewHash({ ...snapshot, ...patch })).not.toBe(
        hash,
      );
    }
  });
  it.each([
    ["TEST-id", "ASSESS", "TEST-request", "a".repeat(64)],
    ["TEST-id", "INCLUDE", "", "a".repeat(64)],
    ["TEST-id", "INCLUDE", " TEST-request ", "a".repeat(64)],
    ["TEST-id", "INCLUDE", "TEST-request", "A".repeat(64)],
    ["TEST-id", "INCLUDE", "TEST-request", "wrong-hash"],
    ["", "INCLUDE", "TEST-request", "a".repeat(64)],
  ])("refuses malformed durable key %#", (...parts) => {
    expect(parseCandidateOperation(JSON.stringify(parts))).toBeNull();
  });
});
