import type { Candidate, CandidateAssessment } from "./candidates";

/** A human day is distinct from a raw source timestamp; server repeats these checks. */
export function currentDemandDate(candidate: Candidate, assessment: CandidateAssessment | undefined, now: number): number | null {
  const receipt = candidate.sourceVerification;
  const proof = receipt?.demandEvidence;
  if (!receipt || !proof || receipt.status !== "OPEN" || !Number.isFinite(now) ||
      receipt.binding.candidateId !== candidate.id || receipt.binding.candidateRevision !== candidate.revision ||
      receipt.binding.sourceVersionId !== candidate.sourceVersionId || receipt.binding.profileId !== candidate.profileId ||
      receipt.binding.profileVersion !== candidate.profileVersion || assessment?.demandEvidenceId !== receipt.id) return null;
  const checked = Date.parse(receipt.checkedAt);
  const date = Date.parse(`${proof.publishedDate}T00:00:00+08:00`);
  if (!Number.isFinite(checked) || checked > now || now - checked > 86_400_000 ||
      !Number.isFinite(date) || date > now || now - date > 60 * 86_400_000) return null;
  return date;
}
