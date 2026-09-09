import { z } from "zod";
import {
  candidateBindingSchema,
  candidateRequestIdSchema,
  candidateReviewRequestSchema,
  sourceVerificationRequestSchema,
  parseCandidateReviewResult,
  type CandidateReviewResultDto,
} from "../../shared/candidateReviewApi";
import { hashText } from "./taskOperations";

const FAILURE = "INVALID_CANDIDATE_REQUEST_OPERATION";
const uuid = candidateBindingSchema.shape.candidateId;
const version = candidateBindingSchema.shape.candidateRevision;
const scopeId = z.string().min(1).max(128).refine(
  value => value.trim() === value && !/[\p{Cc}\p{Cf}\uD800-\uDFFF]/u.test(value),
);
const scopeSchema = z.object({ id: scopeId, version }).strict().nullable();
const keySchema = z.tuple([
  scopeId.nullable(), version.nullable(), uuid, candidateRequestIdSchema,
]).refine(parts => (parts[0] === null) === (parts[1] === null));
const recordSchema = z.object({
  v: z.literal(1),
  action: z.enum(["ASSESS", "VERIFY_SOURCE", "INCLUDE", "EXCLUDE"]),
  binding: z.tuple([version, uuid, uuid, version]),
  requestHash: z.string().regex(/^[a-f0-9]{64}$/),
  assessmentId: uuid.nullable(),
  // [] is omitted on the original JSON wire; [null] is explicit null.
  verification: z.union([z.tuple([]), z.tuple([uuid.nullable()])]),
  retryOf: z.union([z.tuple([]), z.tuple([candidateRequestIdSchema.nullable()])]),
  invocationId: candidateRequestIdSchema.nullable(),
  state: z.enum(["PENDING", "PROCESSING", "UNKNOWN", "FAILED", "RECORDED"]),
}).strict().refine(record => {
  if (record.action === "ASSESS")
    return record.assessmentId === null && record.verification.length === 0;
  if (record.retryOf.length !== 0 || record.invocationId !== null ||
    record.state === "PROCESSING" || record.state === "FAILED") return false;
  if (record.action === "VERIFY_SOURCE")
    return record.assessmentId === null && record.verification.length === 0;
  return record.assessmentId !== null && (record.action === "EXCLUDE" ||
    (record.verification.length === 1 && record.verification[0] !== null));
});
const operationSchema = recordSchema.safeExtend({
  key: z.string(), scopeId: scopeId.nullable(), scopeVersion: version.nullable(),
  candidateId: uuid, requestId: candidateRequestIdSchema,
}).refine(op =>
  (op.scopeId === null) === (op.scopeVersion === null) &&
  op.key === JSON.stringify([op.scopeId, op.scopeVersion, op.candidateId, op.requestId]),
);
export type CandidateRequestOperation = z.infer<typeof operationSchema>;

function parseRequest(input: unknown) {
  return z.union([candidateReviewRequestSchema, sourceVerificationRequestSchema]).parse(input);
}
function presence<T>(value: T | undefined): [] | [T] {
  return value === undefined ? [] : [value];
}
function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value !== null && typeof value === "object") return `{${Object.entries(value)
    .filter(([, item]) => item !== undefined)
    .sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0)
    .map(([key, item]) => `${JSON.stringify(key)}:${canonical(item)}`).join(",")}}`;
  return JSON.stringify(value);
}
/** Local original-request fingerprint, not the legacy review or server hash. */
export async function candidateRequestDigest(input: unknown): Promise<string> {
  try {
    const request = parseRequest(input);
    const action = "action" in request ? request.action : "VERIFY_SOURCE";
    return await hashText(canonical(["candidate-request-operation", 1, action, request]));
  } catch { throw new Error(FAILURE); }
}
export async function newCandidateRequestOperation(
  input: unknown,
  scope: { id: string; version: number } | null,
): Promise<CandidateRequestOperation> {
  try {
    const request = parseRequest(input), context = scopeSchema.parse(scope);
    const action = "action" in request ? request.action : "VERIFY_SOURCE";
    return operationSchema.parse({
      key: JSON.stringify([context?.id ?? null, context?.version ?? null, request.candidateId, request.requestId]),
      scopeId: context?.id ?? null, scopeVersion: context?.version ?? null,
      candidateId: request.candidateId, requestId: request.requestId,
      v: 1, action,
      binding: [request.candidateRevision, request.sourceVersionId, request.profileId, request.profileVersion],
      requestHash: await candidateRequestDigest(request),
      assessmentId: "assessmentId" in request ? request.assessmentId : null,
      verification: "sourceVerificationId" in request ? presence(request.sourceVerificationId) : [],
      retryOf: "retryOf" in request ? presence(request.retryOf) : [],
      invocationId: null, state: "PENDING",
    });
  } catch { throw new Error(FAILURE); }
}
export function parseCandidateRequestOperation(
  key: string, value: string,
): CandidateRequestOperation | null {
  try {
    if (typeof key !== "string" || typeof value !== "string" || key.length > 1024 || value.length > 4096)
      return null;
    const [scopeId, scopeVersion, candidateId, requestId] = keySchema.parse(JSON.parse(key));
    return operationSchema.parse({
      ...recordSchema.parse(JSON.parse(value)), key, scopeId, scopeVersion, candidateId, requestId,
    });
  } catch { return null; }
}
export function candidateRequestEntry(
  operation: CandidateRequestOperation,
): { key: string; value: string } {
  try {
    const { key, scopeId: _scope, scopeVersion: _version, candidateId: _candidate, requestId: _request, ...record } =
      operationSchema.parse(operation);
    const value = JSON.stringify(record);
    if (!validCandidateRequestEntry(key, value)) throw new Error();
    return { key, value };
  } catch { throw new Error(FAILURE); }
}
export function validCandidateRequestEntry(key: string, value: string): boolean {
  return parseCandidateRequestOperation(key, value) !== null;
}
/** Verify the response against the saved fingerprint before adopting any state. */
export async function recoverCandidateRequestResult(
  raw: unknown, operation: CandidateRequestOperation,
): Promise<{ result: CandidateReviewResultDto; operation: CandidateRequestOperation }> {
  try {
    const entry = candidateRequestEntry(operation);
    const op = parseCandidateRequestOperation(entry.key, entry.value)!;
    const binding = {
      candidateId: op.candidateId, candidateRevision: op.binding[0],
      sourceVersionId: op.binding[1], profileId: op.binding[2], profileVersion: op.binding[3],
    };
    const result = parseCandidateReviewResult(raw, { requestId: op.requestId, binding });
    const original = { ...binding, requestId: op.requestId };
    let reconstructed: unknown;
    let invocationId = op.invocationId;
    let state: CandidateRequestOperation["state"] = "RECORDED";
    if (op.action === "ASSESS") {
      if (result.kind !== "assessment" && result.kind !== "pending" && result.kind !== "failure") throw new Error();
      reconstructed = { ...original, action: "ASSESS",
        ...(op.retryOf.length ? { retryOf: op.retryOf[0] } : {}) };
      // The response requestId remains this ledger key; invocationRequestId is metadata only.
      const actualInvocation = result.invocationRequestId ?? result.requestId;
      if (invocationId !== null && invocationId !== actualInvocation) throw new Error();
      invocationId = actualInvocation;
      if (result.kind === "pending" || result.kind === "failure") state = result.status;
    } else if (op.action === "VERIFY_SOURCE") {
      if (result.kind !== "sourceVerification") throw new Error();
      reconstructed = { ...original, humanConfirmed: true,
        status: result.status, openingMethod: result.openingMethod,
        locator: result.locator, excerpt: result.excerpt, contactMethod: result.contactMethod };
    } else {
      if (result.kind !== "decision" || result.receipt.action !== op.action) throw new Error();
      const { sourceVerificationId, ...review } = result.receipt.review;
      if (review.assessmentId !== op.assessmentId ||
        sourceVerificationId !== (op.verification.length ? op.verification[0] : null)) throw new Error();
      reconstructed = { ...original, ...review, action: op.action, humanConfirmed: true,
        ...(op.verification.length ? { sourceVerificationId: op.verification[0] } : {}) };
    }
    if (await candidateRequestDigest(reconstructed) !== op.requestHash) throw new Error();
    // The producer finalizes only PROCESSING rows; a saved success/failure is terminal.
    if ((op.state === "RECORDED" || op.state === "FAILED") && op.state !== state) throw new Error();
    return { result, operation: operationSchema.parse({ ...op, invocationId, state }) };
  } catch { throw new Error(FAILURE); }
}
