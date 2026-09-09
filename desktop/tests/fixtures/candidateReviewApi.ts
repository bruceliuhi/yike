export const candidateBinding = {
  candidateId: "11111111-1111-4111-8111-111111111111",
  candidateRevision: 2,
  sourceVersionId: "22222222-2222-4222-8222-222222222222",
  profileId: "33333333-3333-4333-8333-333333333333",
  profileVersion: 3,
};
export const strategyId = "44444444-4444-4444-8444-444444444444";
export const assessmentId = "55555555-5555-4555-8555-555555555555";
export const verificationId = "66666666-6666-4666-8666-666666666666";
export const opportunityId = "77777777-7777-4777-8777-777777777777";
export const candidateTime = "2026-09-10T01:02:03.123456+00:00";
export function evidenceFixture() {
  return {
    matchReason: "匹配运输设备",
    actionSignal: "采购输送设备",
    value: "需要报价",
    risk: "预算未核实",
    unknowns: "联系人未知",
  };
}
export function assessmentFixture() {
  const dimension = () => ({
    level: "HIGH",
    reason: "逐字出处支持",
    citations: [{ field: "body", quote: "采购输送设备" }],
  });
  return {
    ...candidateBinding,
    id: assessmentId,
    businessMatch: dimension(),
    intent: dimension(),
    urgency: dimension(),
    actionability: dimension(),
    purchaseType: "PROJECT",
    grade: "A",
    decision: "SEND_READY",
    effectiveDecision: "REVIEW",
    sendingAuthorized: false,
    evidence: evidenceFixture(),
    summary: "TEST 需要核实的采购线索",
    draftComment: "您希望什么时候完成采购？",
    draftDm: "方便了解设备规格吗？",
    assessedAt: candidateTime,
    provider: "synthetic",
    model: "boundary-only",
    rule_version: "test-v1",
    rule_sha256: "a".repeat(64),
    strategyVersionId: strategyId,
  };
}
export function assessmentRequestFixture() {
  return { ...candidateBinding, requestId: "TEST.assess:1", action: "ASSESS" };
}
export function verificationRequestFixture() {
  return {
    ...candidateBinding,
    requestId: "TEST.verify:1",
    humanConfirmed: true,
    status: "OPEN",
    openingMethod: "DIRECT",
    locator: "https://example.com/synthetic",
    excerpt: "采购输送设备",
    contactMethod: "COMMENT",
  };
}
export function verificationFixture() {
  const { humanConfirmed: _human, ...request } = verificationRequestFixture();
  const {
    candidateRevision: _revision,
    sourceVersionId: _source,
    profileId: _profile,
    profileVersion: _version,
    ...fields
  } = request;
  return {
    ...fields,
    kind: "sourceVerification",
    id: verificationId,
    method: "HUMAN_REOPENED",
    checkedBy: "TEST-owner",
    checkedAt: candidateTime,
    binding: { ...candidateBinding },
  };
}
export function decisionRequestFixture() {
  return {
    ...candidateBinding,
    requestId: "TEST.include:1",
    action: "INCLUDE",
    assessmentId,
    evidence: evidenceFixture(),
    reason: "人工核对",
    humanConfirmed: true,
    sourceVerificationId: verificationId,
  };
}
export function receiptFixture() {
  const {
    requestId,
    action,
    candidateId: _candidate,
    humanConfirmed: _human,
    ...review
  } = decisionRequestFixture();
  return {
    requestId,
    action,
    status: "SUCCEEDED",
    outcome: "IMPORTED",
    reviewedBy: "TEST-owner",
    reviewedAt: candidateTime,
    review,
    opportunityId,
  };
}
export function candidateFixture() {
  return {
    id: candidateBinding.candidateId,
    revision: candidateBinding.candidateRevision,
    sample: false,
    status: "PENDING_REVIEW",
    title: "食品工厂扩产",
    buyer: "",
    platform: "PUBLIC_WEB",
    sourceLabel: "PUBLIC_WEB",
    sourceId: "b".repeat(64),
    sourceVersionId: candidateBinding.sourceVersionId,
    sourceStatus: "UNVERIFIED",
    url: null,
    excerpt: "采购输送设备\n  原文🙂",
    summary: "",
    publishedAt: "",
    collectedAt: "2026-09-10T01:01:00Z",
    profileId: candidateBinding.profileId,
    profileVersion: candidateBinding.profileVersion,
    strategyVersionId: strategyId,
    historical: false,
    currentBindingValid: true,
    assessmentStale: false,
  };
}
export function decisionFixture() {
  const receipt = receiptFixture();
  return {
    kind: "decision",
    requestId: receipt.requestId,
    candidate: {
      ...candidateFixture(),
      status: "IMPORTED",
      assessment: assessmentFixture(),
      lastReview: receipt,
      opportunityId,
    },
    receipt,
  };
}
export function pageFixture() {
  return { items: [candidateFixture()], total: 1, page: 1, pageSize: 20 };
}
