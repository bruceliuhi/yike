import { z } from "zod";
import {
  reviewSnapshot,
  type CandidateReceipt,
  type CandidateReview,
  type CandidateReviewSnapshot,
} from "./candidates";

export type CandidateDecision = Extract<
  CandidateReview,
  { action: "INCLUDE" | "EXCLUDE" }
>;
export interface CandidateReviewOperation {
  key: string;
  candidateId: string;
  action: "INCLUDE" | "EXCLUDE";
  requestId: string;
  reviewHash: string;
}
const id = z
  .string()
  .min(1)
  .max(128)
  .refine(
    (value) => value.trim() === value && !/[\u0000-\u001f\u007f]/.test(value),
  );
const partsSchema = z.tuple([
  id,
  z.enum(["INCLUDE", "EXCLUDE"]),
  id,
  z.string().regex(/^[a-f0-9]{64}$/),
]);
const text = z.string().min(1).max(2000);
const reviewSchema = z.object({
  candidateRevision: z.number().int().positive(),
  sourceVersionId: id,
  profileId: id,
  profileVersion: z.number().int().positive(),
  assessmentId: id,
  evidence: z.object({
    matchReason: text,
    actionSignal: text,
    value: text,
    risk: text,
    unknowns: text,
  }),
  reason: z.string().max(2000),
});
export function parseCandidateOperation(
  key: string,
): CandidateReviewOperation | null {
  try {
    const parsed = partsSchema.safeParse(JSON.parse(key));
    if (!parsed.success) return null;
    const [candidateId, action, requestId, reviewHash] = parsed.data;
    return { key, candidateId, action, requestId, reviewHash };
  } catch {
    return null;
  }
}
export async function candidateReviewHash(review: CandidateReviewSnapshot) {
  const checked = reviewSchema.parse(review);
  const e = checked.evidence;
  const canonical = JSON.stringify([
    checked.candidateRevision,
    checked.sourceVersionId,
    checked.profileId,
    checked.profileVersion,
    checked.assessmentId,
    [e.matchReason, e.actionSignal, e.value, e.risk, e.unknowns],
    checked.reason,
  ]);
  return Array.from(
    new Uint8Array(
      await crypto.subtle.digest(
        "SHA-256",
        new TextEncoder().encode(canonical),
      ),
    ),
    (byte) => byte.toString(16).padStart(2, "0"),
  ).join("");
}
export async function candidateOperation(
  request: CandidateDecision,
): Promise<CandidateReviewOperation> {
  const key = JSON.stringify([
    request.candidateId,
    request.action,
    request.requestId,
    await candidateReviewHash(reviewSnapshot(request)),
  ]);
  const result = parseCandidateOperation(key);
  if (!result) throw new Error("复核请求记录无效，尚未提交。");
  return result;
}
export async function matchingCandidateReceipt(
  operation: CandidateReviewOperation,
  receipt: CandidateReceipt,
): Promise<boolean> {
  if (
    receipt.requestId !== operation.requestId ||
    receipt.action !== operation.action ||
    !receipt.review
  )
    return false;
  try {
    return (await candidateReviewHash(receipt.review)) === operation.reviewHash;
  } catch {
    return false;
  }
}
