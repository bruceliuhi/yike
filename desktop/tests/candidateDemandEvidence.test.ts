import { describe, expect, it } from "vitest";
import { sourceVerificationRequestSchema, parseCandidateReviewResult, parseCandidatePage } from "../src/shared/candidateReviewApi";
import { verificationRequestFixture, verificationFixture, assessmentFixture, candidateFixture, pageFixture } from "./fixtures/candidateReviewApi";
import { currentDemandDate } from "../src/renderer/domain/candidateDemandEvidence";
import { validatedOperation } from "../src/main/servicePolicy";

const proof = {
  schemaVersion: "human-demand-evidence-v1",
  authorLocator: "TEST采购人，第2楼",
  authorExcerpt: "TEST采购人",
  demandExcerpt: "采购输送设备",
  publishedDate: "2026-09-10",
  dateExcerpt: "2026年9月10日",
};

describe("human demand evidence contract (synthetic)", () => {
  it("negotiates evidence on each fixed candidate and opportunity route", () => {
    for (const [operation, payload] of [
      ["candidates.list", {}], ["candidates.review", { ...verificationRequestFixture(), action: "ASSESS" }],
      ["candidates.verifySource", verificationRequestFixture()],
      ["candidates.request", {requestId:"TEST.verify:1"}], ["opportunities.get", {id:"TEST-o"}],
    ] as const) {
      const input = operation === "candidates.review" ? {operation,payload: {
        candidateId:verificationRequestFixture().candidateId,candidateRevision:2,
        sourceVersionId:verificationRequestFixture().sourceVersionId,profileId:verificationRequestFixture().profileId,
        profileVersion:3,requestId:"TEST.assess",action:"ASSESS",
      }} : {operation,payload};
      expect(validatedOperation(input)?.path).toContain("evidenceVersion=1");
    }
  });
  it("preserves optional evidence on request, receipt and candidate without changing raw date", () => {
    const request = { ...verificationRequestFixture(), demandEvidence: proof };
    expect(sourceVerificationRequestSchema.parse(request)).toEqual(request);
    const receipt = { ...verificationFixture(), demandEvidence: proof };
    expect(parseCandidateReviewResult(receipt, { requestId: request.requestId, request })).toEqual(receipt);
    const candidate = { ...candidateFixture(), sourceVerification: receipt,
      assessment: { ...assessmentFixture(), demandEvidenceId: receipt.id } };
    const page = { ...pageFixture(), items: [candidate] };
    expect(parseCandidatePage(page, {})).toEqual(page);
    expect(parseCandidatePage(page, {}).items[0].publishedAt).toBe("");
  });
  it("keeps absent evidence absent for older objects", () => {
    const request = verificationRequestFixture();
    expect(sourceVerificationRequestSchema.parse(request)).toEqual(request);
    expect(parseCandidateReviewResult(verificationFixture(), { requestId: request.requestId, request })).toEqual(verificationFixture());
  });
  it.each([
    { publishedDate: "2026-02-29" }, { publishedDate: "2026-04-31" },
    { publishedDate: "2026-9-10" }, { publishedDate: "2026-09-10T00:00:00Z" },
    { authorLocator: " " }, { authorLocator: "字".repeat(257) },
    { authorExcerpt: "" }, { demandExcerpt: "字".repeat(2001) },
    { dateExcerpt: "\0" }, { schemaVersion: "future" }, { confirmedBy: "forged" },
  ])("rejects invalid demand proof %#", (change) => {
    expect(sourceVerificationRequestSchema.safeParse({ ...verificationRequestFixture(),
      demandEvidence: { ...proof, ...change } }).success).toBe(false);
  });
  it.each(["BLOCKED", "EXPIRED", "UNVERIFIED"])("rejects %s proof writes but preserves server-projected expiry reads", (status) => {
    expect(sourceVerificationRequestSchema.safeParse({ ...verificationRequestFixture(), status,
      demandEvidence: proof }).success).toBe(false);
    const parseReceipt = () => parseCandidateReviewResult({ ...verificationFixture(), status, demandEvidence: proof },
      { requestId: verificationRequestFixture().requestId });
    if (status === "EXPIRED") expect(parseReceipt().kind).toBe("sourceVerification");
    else expect(parseReceipt).toThrow();
  });
  it("accepts a valid leap day and counts Unicode code points", () => {
    expect(sourceVerificationRequestSchema.safeParse({ ...verificationRequestFixture(), demandEvidence: {
      ...proof, publishedDate: "2024-02-29", authorLocator: "🙂".repeat(256),
    } }).success).toBe(true);
  });
  it("uses only current bound proof and assessment, never collected time", () => {
    const verification = { ...verificationFixture(), demandEvidence: proof };
    const candidate = parseCandidatePage({ ...pageFixture(), items: [{ ...candidateFixture(),
      sourceVerification: verification, assessment: { ...assessmentFixture(), demandEvidenceId: verification.id } }] }, {}).items[0];
    const now = Date.parse("2026-09-10T03:00:00Z");
    expect(currentDemandDate(candidate, candidate.assessment, now)).toBe(Date.parse("2026-09-10T00:00:00+08:00"));
    expect(currentDemandDate(candidate, { ...candidate.assessment!, demandEvidenceId: undefined }, now)).toBeNull();
    expect(currentDemandDate({ ...candidate, revision: 3 }, candidate.assessment, now)).toBeNull();
    expect(currentDemandDate(candidate, candidate.assessment, now + 86_400_000)).toBeNull();
    expect(currentDemandDate({ ...candidate, sourceVerification: undefined }, candidate.assessment, now)).toBeNull();
    const expired = {...candidate, sourceStatus:"EXPIRED" as const,
      sourceVerification:{...candidate.sourceVerification!,status:"EXPIRED" as const}};
    expect(parseCandidatePage({...pageFixture(),items:[expired]}).items[0].sourceVerification?.demandEvidence).toEqual(proof);
    expect(currentDemandDate(expired,candidate.assessment,now)).toBeNull();
  });
});
