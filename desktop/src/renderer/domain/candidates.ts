/** Transport contract for V02 candidates. No candidate HTTP API is wired yet. */
export type CandidateStatus =
  | "PENDING_REVIEW"
  | "IMPORTED"
  | "EXCLUDED"
  | "DUPLICATE";
export type CandidateSourceStatus =
  | "OPEN"
  | "UNVERIFIED"
  | "EXPIRED"
  | "BLOCKED";
export interface CandidateEvidence {
  matchReason: string;
  actionSignal: string;
  value: string;
  risk: string;
  unknowns: string;
}
export interface CandidateAssessment {
  id: string;
  profileId: string;
  profileVersion: number;
  candidateRevision: number;
  sourceVersionId: string;
  evidence: CandidateEvidence;
  assessedAt: string;
}
export interface CandidateReviewSnapshot {
  candidateRevision: number;
  sourceVersionId: string;
  profileId: string;
  profileVersion: number;
  assessmentId: string;
  evidence: CandidateEvidence;
  reason: string;
}
export interface CandidateReceipt {
  requestId: string;
  action: "INCLUDE" | "EXCLUDE";
  status: "PROCESSING" | "SUCCEEDED" | "FAILED" | "UNKNOWN";
  outcome?: "IMPORTED" | "EXCLUDED" | "ALREADY_IMPORTED";
  reviewedBy?: string;
  reviewedAt?: string;
  opportunityId?: string;
  message?: string;
  /** Required on successful receipts: retain the human-reviewed words and binding. */
  review?: CandidateReviewSnapshot;
}
export interface Candidate {
  id: string;
  revision: number;
  sample: boolean;
  status: CandidateStatus;
  title: string;
  buyer: string;
  platform: string;
  sourceLabel: string;
  sourceId: string;
  sourceVersionId: string;
  sourceStatus: CandidateSourceStatus;
  url: string;
  excerpt: string;
  summary: string;
  publishedAt: string;
  collectedAt: string;
  location?: string;
  deadline?: string;
  stage?: string;
  assessment?: CandidateAssessment;
  opportunityId?: string;
  lastReview?: CandidateReceipt;
}
export interface CandidateQuery {
  query?: string;
  platform?: string;
  status?: CandidateStatus;
  page?: number;
  pageSize?: number;
  /** Read-only reconciliation of a previous decision; never creates a review. */
  ids?: string[];
  reviewRequestId?: string;
}
export interface CandidatePage {
  items: Candidate[];
  total: number;
  page: number;
  pageSize: number;
}
interface ReviewBinding {
  candidateId: string;
  candidateRevision: number;
  sourceVersionId: string;
  profileId: string;
  profileVersion: number;
  requestId: string;
}
export type CandidateReview =
  | (ReviewBinding & { action: "ASSESS" })
  | (ReviewBinding & {
      action: "INCLUDE" | "EXCLUDE";
      assessmentId: string;
      evidence: CandidateEvidence;
      reason: string;
      humanConfirmed: true;
    });
export type CandidateReviewResult =
  | {
      kind: "assessment";
      requestId: string;
      candidateId: string;
      assessment: CandidateAssessment;
    }
  | {
      kind: "decision";
      requestId: string;
      candidate: Candidate;
      receipt: CandidateReceipt;
    }
  | {
      kind: "pending";
      requestId: string;
      candidateId: string;
      status: "PROCESSING" | "UNKNOWN";
    };

// Future adapters must validate responses and enforce these rules server-side:
// - Resolve tenant, reviewer and review time from the authenticated service.
// - Persist requestId idempotency and its receipt; ASSESS never imports a row.
// - Recheck profile CONFIRMED, candidate/source revisions, source availability,
//   customer scope, and evidence; a device cannot report its own approval.
// - A read using reviewRequestId returns the receipt, including failed/unknown
//   outcomes. A missing receipt or still-pending candidate is not a failed send.
// - INCLUDE cannot accept public samples or an expired/blocked/unverified source.
export const EMPTY_CANDIDATE_EVIDENCE: CandidateEvidence = {
  matchReason: "",
  actionSignal: "",
  value: "",
  risk: "",
  unknowns: "",
};
export const CANDIDATE_EVIDENCE_LABELS: Record<
  keyof CandidateEvidence,
  string
> = {
  matchReason: "匹配理由",
  actionSignal: "行动信号",
  value: "价值判断",
  risk: "风险",
  unknowns: "未知项与待核实事项",
};
export const CANDIDATE_STATUS_LABELS: Record<CandidateStatus, string> = {
  PENDING_REVIEW: "待复核",
  IMPORTED: "已入库",
  EXCLUDED: "已排除",
  DUPLICATE: "重复候选",
};
export function completeCandidateEvidence(value: CandidateEvidence): boolean {
  return Object.keys(CANDIDATE_EVIDENCE_LABELS).every((key) => {
    const text = value[key as keyof CandidateEvidence];
    return typeof text === "string" && !!text.trim() && text.length <= 2000;
  });
}
export function assessmentMatches(
  candidate: Candidate,
  assessment: CandidateAssessment | undefined,
  profileId: string,
  profileVersion: number,
): boolean {
  return (
    !!assessment &&
    assessment.profileId === profileId &&
    assessment.profileVersion === profileVersion &&
    assessment.candidateRevision === candidate.revision &&
    assessment.sourceVersionId === candidate.sourceVersionId
  );
}
/** A receipt is authoritative only when it agrees with the returned stored row. */
export function completedCandidateReview(
  candidate: Candidate,
  receipt: CandidateReceipt,
): boolean {
  if (
    candidate.sample ||
    candidate.id === "sample" ||
    receipt.status !== "SUCCEEDED" ||
    !receipt.reviewedBy?.trim() ||
    !receipt.reviewedAt ||
    !Number.isFinite(Date.parse(receipt.reviewedAt))
  )
    return false;
  const review = receipt.review;
  if (
    !review ||
    !review.profileId ||
    !Number.isInteger(review.profileVersion) ||
    review.profileVersion < 1 ||
    !Number.isInteger(review.candidateRevision) ||
    review.candidateRevision < 1 ||
    !review.sourceVersionId ||
    !review.assessmentId ||
    !review.evidence ||
    !completeCandidateEvidence(review.evidence)
  )
    return false;
  if (receipt.action === "EXCLUDE")
    return (
      receipt.outcome === "EXCLUDED" &&
      candidate.status === "EXCLUDED" &&
      !!review.reason?.trim()
    );
  return (
    !!receipt.opportunityId &&
    candidate.opportunityId === receipt.opportunityId &&
    ((receipt.outcome === "IMPORTED" && candidate.status === "IMPORTED") ||
      (receipt.outcome === "ALREADY_IMPORTED" &&
        ["IMPORTED", "DUPLICATE"].includes(candidate.status)))
  );
}
export function reviewSnapshot(
  value: CandidateReview & { action: "INCLUDE" | "EXCLUDE" },
): CandidateReviewSnapshot {
  return {
    candidateRevision: value.candidateRevision,
    sourceVersionId: value.sourceVersionId,
    profileId: value.profileId,
    profileVersion: value.profileVersion,
    assessmentId: value.assessmentId,
    evidence: { ...value.evidence },
    reason: value.reason,
  };
}
export function sameReviewSnapshot(
  a: CandidateReviewSnapshot | undefined,
  b: CandidateReviewSnapshot | undefined,
): boolean {
  return (
    !!a &&
    !!b &&
    a.candidateRevision === b.candidateRevision &&
    a.sourceVersionId === b.sourceVersionId &&
    a.profileId === b.profileId &&
    a.profileVersion === b.profileVersion &&
    a.assessmentId === b.assessmentId &&
    a.reason === b.reason &&
    Object.keys(CANDIDATE_EVIDENCE_LABELS).every(
      (key) =>
        a.evidence[key as keyof CandidateEvidence] ===
        b.evidence[key as keyof CandidateEvidence],
    )
  );
}
