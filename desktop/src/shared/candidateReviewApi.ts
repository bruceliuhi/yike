import { z } from "zod";

const uuid = z
  .string()
  .regex(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/);
export const candidateRequestIdSchema = z
  .string()
  .regex(/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/);
export const candidatePlatformSchema = z.enum([
  "XIAOHONGSHU",
  "DOUYIN",
  "BILIBILI",
  "ZHIHU",
  "PUBLIC_WEB",
]);
const status = z.enum(["PENDING_REVIEW", "IMPORTED", "EXCLUDED", "DUPLICATE"]);
const sourceStatus = z.enum(["OPEN", "BLOCKED", "EXPIRED", "UNVERIFIED"]);
const integer = z.number().int().safe().positive();
const instant = z.iso.datetime({ offset: true });
const blank = (value: string) =>
  /^[\p{White_Space}\u001c-\u001f]*$/u.test(value);
const pythonStrip = (value: string) =>
  value.replace(
    /^[\p{White_Space}\u001c-\u001f]+|[\p{White_Space}\u001c-\u001f]+$/gu,
    "",
  );
const wellFormed = (value: string) => !/[\uD800-\uDFFF]/u.test(value);
function text(max: number, nonblank = true) {
  return z
    .string()
    .refine(
      (v) =>
        wellFormed(v) &&
        Array.from(v).length <= max &&
        (!nonblank || !blank(v)),
    );
}
const humanText = text(2000).refine((v) => !v.includes("\0"));
const reason = text(2000, false).refine((v) => !v.includes("\0"));
const rawText = (max: number, nonblank = true) =>
  text(max, nonblank).refine(
    (v) => !/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]/.test(v),
  );
const modelText = (max: number) =>
  rawText(max).refine((v) => /[^\p{C}\p{M}\p{Z}\s]/u.test(v));
const evidenceShape = (value: z.ZodType<string>) => ({
  matchReason: value,
  actionSignal: value,
  value,
  risk: value,
  unknowns: value,
});
const evidence = z.object(evidenceShape(humanText)).strict();
const bindingShape = {
  candidateId: uuid,
  candidateRevision: integer,
  sourceVersionId: uuid,
  profileId: uuid,
  profileVersion: integer,
};
export const candidateBindingSchema = z.object(bindingShape).strict();
export type CandidateReviewBinding = z.infer<typeof candidateBindingSchema>;
const writeBinding = { ...bindingShape, requestId: candidateRequestIdSchema };
const bodyFits = (value: unknown) =>
  new TextEncoder().encode(JSON.stringify(value)).byteLength <= 64 * 1024;

export const candidateQuerySchema = z
  .object({
    taskId: uuid.optional(),
    query: text(200).optional(),
    platform: candidatePlatformSchema.optional(),
    status: status.optional(),
    page: integer.max(999999999).optional(),
    pageSize: integer.max(100).optional(),
    ids: z
      .array(uuid)
      .min(1)
      .max(100)
      .refine((ids) => new Set(ids).size === ids.length)
      .optional(),
    reviewRequestId: candidateRequestIdSchema.optional(),
  })
  .strict()
  .refine(
    (q) =>
      q.reviewRequestId === undefined ||
      (q.ids?.length === 1 && (q.page ?? 1) === 1 && q.pageSize === 1),
  );
export type CandidateQueryInput = z.infer<typeof candidateQuerySchema>;

const assessRequest = z
  .object({
    ...writeBinding,
    action: z.literal("ASSESS"),
    retryOf: candidateRequestIdSchema.nullable().optional(),
  })
  .strict();
const decisionShape = {
  ...writeBinding,
  assessmentId: uuid,
  evidence,
  reason,
  humanConfirmed: z.literal(true),
};
const includeRequest = z
  .object({
    ...decisionShape,
    action: z.literal("INCLUDE"),
    sourceVerificationId: uuid,
  })
  .strict();
const excludeRequest = z
  .object({
    ...decisionShape,
    action: z.literal("EXCLUDE"),
    sourceVerificationId: uuid.nullable().optional(),
  })
  .strict()
  .refine((r) => !blank(r.reason));
export const candidateReviewRequestSchema = z
  .union([assessRequest, includeRequest, excludeRequest])
  .refine(bodyFits);
export type CandidateReviewRequest = z.infer<
  typeof candidateReviewRequestSchema
>;
const sourceFields = {
  status: sourceStatus,
  openingMethod: z.enum(["DIRECT", "IN_PLATFORM"]),
  locator: humanText,
  excerpt: humanText,
  contactMethod: z.enum(["COMMENT", "DM", "PUBLIC_CONTACT", "NONE"]),
};
export const sourceVerificationRequestSchema = z
  .object({ ...writeBinding, ...sourceFields, humanConfirmed: z.literal(true) })
  .strict()
  .refine(bodyFits);
export type SourceVerificationRequest = z.infer<
  typeof sourceVerificationRequestSchema
>;

const citation = z
  .object({
    field: z.enum([
      "title",
      "body",
      "parent.title",
      "parent.body",
      "profile.description",
    ]),
    quote: modelText(8000),
  })
  .strict();
const dimension = z
  .object({
    level: z.enum(["HIGH", "MEDIUM", "LOW", "UNKNOWN"]),
    reason: modelText(1200),
    citations: z.array(citation).max(16),
  })
  .strict()
  .refine((d) => d.level === "UNKNOWN" || d.citations.length > 0);
const assessment = z
  .object({
    ...bindingShape,
    id: uuid,
    businessMatch: dimension,
    intent: dimension,
    urgency: dimension,
    actionability: dimension,
    purchaseType: z.enum([
      "PROJECT",
      "DIAGNOSIS",
      "PRODUCT",
      "SUPPLY_OR_JOB",
      "UNKNOWN",
    ]),
    grade: z.enum(["S", "A", "B+"]).nullable(),
    decision: z.enum(["SEND_READY", "REVIEW", "OBSERVE", "EXCLUDE"]),
    effectiveDecision: z.enum(["REVIEW", "OBSERVE", "EXCLUDE"]),
    sendingAuthorized: z.literal(false),
    evidence: z.object(evidenceShape(modelText(1200))).strict(),
    summary: modelText(1200),
    draftComment: modelText(120),
    draftDm: modelText(120),
    assessedAt: instant,
    provider: text(200),
    model: text(200),
    rule_version: text(200),
    rule_sha256: text(200),
    strategyVersionId: uuid,
  })
  .strict()
  .refine(
    (a) =>
      a.effectiveDecision ===
        (a.decision === "SEND_READY" ? "REVIEW" : a.decision) &&
      (!["OBSERVE", "EXCLUDE"].includes(a.decision) || a.grade === null) &&
      pythonStrip(a.draftComment) !== pythonStrip(a.draftDm) &&
      [a.intent, a.urgency].every(
        (d) =>
          d.level === "UNKNOWN" ||
          d.citations.some((c) => c.field === "title" || c.field === "body"),
      ),
  );
export type CandidateAssessmentDto = z.infer<typeof assessment>;
const actor = text(256).refine(
  (v) => !/[\x00-\x1f]/.test(v) && pythonStrip(v) === v,
);
const verification = z
  .object({
    kind: z.literal("sourceVerification"),
    id: uuid,
    requestId: candidateRequestIdSchema,
    candidateId: uuid,
    ...sourceFields,
    method: z.literal("HUMAN_REOPENED"),
    checkedBy: actor,
    checkedAt: instant,
    binding: candidateBindingSchema,
  })
  .strict()
  .refine((v) => v.candidateId === v.binding.candidateId);
export type CandidateSourceVerificationDto = z.infer<typeof verification>;
const reviewSnapshot = z
  .object({
    candidateRevision: integer,
    sourceVersionId: uuid,
    profileId: uuid,
    profileVersion: integer,
    assessmentId: uuid,
    evidence,
    reason,
    sourceVerificationId: uuid.nullable().optional(),
  })
  .strict();
const receipt = z
  .object({
    requestId: candidateRequestIdSchema,
    action: z.enum(["INCLUDE", "EXCLUDE"]),
    status: z.literal("SUCCEEDED"),
    outcome: z.enum(["IMPORTED", "ALREADY_IMPORTED", "EXCLUDED"]),
    reviewedBy: actor,
    reviewedAt: instant,
    review: reviewSnapshot,
    opportunityId: uuid.optional(),
  })
  .strict()
  .refine((r) =>
    r.action === "EXCLUDE"
      ? r.outcome === "EXCLUDED" &&
        r.opportunityId === undefined &&
        !blank(r.review.reason)
      : r.outcome !== "EXCLUDED" &&
        r.opportunityId !== undefined &&
        (r.review.sourceVerificationId === undefined ||
          r.review.sourceVerificationId !== null),
  );
export type CandidateDecisionReceiptDto = z.infer<typeof receipt>;

const publicUrl = text(2048).refine((v) => {
  try {
    const url = new URL(v);
    return (
      ["http:", "https:"].includes(url.protocol) &&
      !!url.hostname &&
      !url.username &&
      !url.password &&
      !/[\x00-\x20\x7f\\]/.test(v)
    );
  } catch {
    return false;
  }
});
const candidate = z
  .object({
    id: uuid,
    revision: integer,
    sample: z.literal(false),
    status,
    // A null source title falls back to body[:120], which can consist of whitespace.
    title: rawText(512, false).refine((v) => v.length > 0),
    buyer: rawText(256, false),
    platform: candidatePlatformSchema,
    sourceLabel: candidatePlatformSchema,
    sourceId: z.string().regex(/^[a-f0-9]{64}$/),
    sourceVersionId: uuid,
    sourceStatus,
    url: publicUrl.nullable(),
    excerpt: rawText(20000),
    summary: text(1200, false),
    publishedAt: z.union([z.literal(""), instant]),
    collectedAt: instant,
    profileId: uuid,
    profileVersion: integer,
    strategyVersionId: uuid,
    historical: z.boolean(),
    currentBindingValid: z.boolean(),
    assessmentStale: z.boolean(),
    assessment: assessment.optional(),
    sourceVerification: verification.optional(),
    lastReview: receipt.optional(),
    opportunityId: uuid.optional(),
  })
  .strict()
  .refine((c) => {
    const b = candidateBinding(c);
    if (c.sourceLabel !== c.platform) return false;
    if (
      c.assessment &&
      (!sameBinding(c.assessment, b) ||
        c.assessment.strategyVersionId !== c.strategyVersionId)
    )
      return false;
    if (c.sourceVerification && !sameBinding(c.sourceVerification.binding, b))
      return false;
    if (
      c.lastReview &&
      (!sameReviewBinding(c.lastReview.review, b) ||
        !receiptMatchesCandidate(c, c.lastReview))
    )
      return false;
    return true;
  });
export type ReviewedCandidateDto = z.infer<typeof candidate>;
const pageSchema = z
  .object({
    taskId: uuid.optional(),
    items: z.array(candidate).max(100),
    total: z.number().int().safe().nonnegative(),
    page: integer.max(999999999),
    pageSize: integer.max(100),
  })
  .strict();
export type ReviewedCandidatePageDto = z.infer<typeof pageSchema>;
const resultIdentity = {
  requestId: candidateRequestIdSchema,
  candidateId: uuid,
};
const alias = { invocationRequestId: candidateRequestIdSchema.optional() };
const resultSchema = z.union([
  z
    .object({
      ...resultIdentity,
      ...alias,
      kind: z.literal("assessment"),
      assessment,
    })
    .strict()
    .refine((r) => r.candidateId === r.assessment.candidateId),
  z
    .object({
      ...resultIdentity,
      ...alias,
      kind: z.literal("pending"),
      status: z.enum(["PROCESSING", "UNKNOWN"]),
      code: z.literal("assessment_unknown").optional(),
    })
    .strict()
    .refine((r) => r.code === undefined || r.status === "UNKNOWN"),
  z
    .object({
      ...resultIdentity,
      ...alias,
      kind: z.literal("failure"),
      status: z.literal("FAILED"),
      code: z.literal("assessment_failed"),
    })
    .strict(),
  verification,
  z
    .object({
      kind: z.literal("decision"),
      requestId: candidateRequestIdSchema,
      candidate,
      receipt,
    })
    .strict()
    .refine(
      (r) =>
        r.requestId === r.receipt.requestId &&
        sameValue(r.candidate.lastReview, r.receipt) &&
        !!r.candidate.assessment &&
        r.candidate.assessment.id === r.receipt.review.assessmentId &&
        sameBinding(r.candidate.assessment, candidateBinding(r.candidate)) &&
        r.candidate.assessment.strategyVersionId ===
          r.candidate.strategyVersionId &&
        sameReviewBinding(r.receipt.review, candidateBinding(r.candidate)),
    ),
]);
export type CandidateReviewResultDto = z.infer<typeof resultSchema>;
const expectedSchema = z
  .object({
    requestId: candidateRequestIdSchema,
    candidateId: uuid.optional(),
    binding: candidateBindingSchema.optional(),
    request: z
      .union([candidateReviewRequestSchema, sourceVerificationRequestSchema])
      .optional(),
  })
  .strict()
  .refine(
    (e) =>
      (!e.request || e.requestId === e.request.requestId) &&
      (!e.candidateId ||
        !e.binding ||
        e.candidateId === e.binding.candidateId) &&
      (!e.request ||
        !e.candidateId ||
        e.request.candidateId === e.candidateId) &&
      (!e.request || !e.binding || sameBinding(e.request, e.binding)),
  );
export type ExpectedCandidateReviewResult = z.infer<typeof expectedSchema>;

function sameValue(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (!a || !b || typeof a !== "object" || typeof b !== "object") return false;
  if (Array.isArray(a) || Array.isArray(b))
    return (
      Array.isArray(a) &&
      Array.isArray(b) &&
      a.length === b.length &&
      a.every((v, i) => sameValue(v, b[i]))
    );
  const x = a as Record<string, unknown>,
    y = b as Record<string, unknown>;
  const keys = Object.keys(x);
  return (
    keys.length === Object.keys(y).length &&
    keys.every((k) => Object.hasOwn(y, k) && sameValue(x[k], y[k]))
  );
}
function sameBinding(
  a: CandidateReviewBinding,
  b: CandidateReviewBinding,
): boolean {
  return a.candidateId === b.candidateId && sameReviewBinding(a, b);
}
function sameReviewBinding(
  a: Omit<CandidateReviewBinding, "candidateId">,
  b: CandidateReviewBinding,
): boolean {
  return (
    a.candidateRevision === b.candidateRevision &&
    a.sourceVersionId === b.sourceVersionId &&
    a.profileId === b.profileId &&
    a.profileVersion === b.profileVersion
  );
}
function candidateBinding(c: {
  id: string;
  revision: number;
  sourceVersionId: string;
  profileId: string;
  profileVersion: number;
}): CandidateReviewBinding {
  return {
    candidateId: c.id,
    candidateRevision: c.revision,
    sourceVersionId: c.sourceVersionId,
    profileId: c.profileId,
    profileVersion: c.profileVersion,
  };
}
function receiptMatchesCandidate(
  c: { status: string; opportunityId?: string },
  r: CandidateDecisionReceiptDto,
): boolean {
  const expectedStatus = {
    IMPORTED: "IMPORTED",
    ALREADY_IMPORTED: "DUPLICATE",
    EXCLUDED: "EXCLUDED",
  }[r.outcome];
  return c.status === expectedStatus && c.opportunityId === r.opportunityId;
}

/** Reading never upgrades old evidence, repairs a receipt, or starts an operation. */
export function parseCandidatePage(
  raw: unknown,
  query: unknown = {},
): ReviewedCandidatePageDto {
  try {
    const q = candidateQuerySchema.parse(query),
      page = pageSchema.parse(raw);
    if (page.taskId !== q.taskId) throw new Error();
    if (page.page !== (q.page ?? 1) || page.pageSize !== (q.pageSize ?? 20))
      throw new Error();
    const count = Math.min(
      page.pageSize,
      Math.max(0, page.total - (page.page - 1) * page.pageSize),
    );
    if (
      page.items.length !== count ||
      new Set(page.items.map((c) => c.id)).size !== page.items.length ||
      (q.ids && page.total > q.ids.length)
    )
      throw new Error();
    for (const item of page.items) {
      if (
        (q.ids && !q.ids.includes(item.id)) ||
        (q.platform && q.platform !== item.platform) ||
        (q.status && q.status !== item.status)
      )
        throw new Error();
      if (
        q.reviewRequestId &&
        (!item.historical || item.lastReview?.requestId !== q.reviewRequestId)
      )
        throw new Error();
    }
    return page;
  } catch {
    throw new Error("INVALID_CANDIDATE_PAGE");
  }
}

/** Request-only expectations serve GET recovery; known original context strengthens matching. */
export function parseCandidateReviewResult(
  raw: unknown,
  expected: unknown,
): CandidateReviewResultDto {
  try {
    const e = expectedSchema.parse(expected),
      result = resultSchema.parse(raw);
    const id =
      result.kind === "decision" ? result.candidate.id : result.candidateId;
    const expectedBinding = e.request ?? e.binding;
    const expectedId = e.candidateId ?? expectedBinding?.candidateId;
    if (result.requestId !== e.requestId || (expectedId && id !== expectedId))
      throw new Error();
    const actualBinding =
      result.kind === "assessment"
        ? result.assessment
        : result.kind === "sourceVerification"
          ? result.binding
          : result.kind === "decision"
            ? candidateBinding(result.candidate)
            : undefined;
    // Pending/failure legitimately omit the versions. Keep their original local binding outside this response.
    if (
      actualBinding &&
      expectedBinding &&
      !sameBinding(actualBinding, expectedBinding)
    )
      throw new Error();
    if (e.request) {
      const request = e.request;
      if (!("action" in request)) {
        if (
          result.kind !== "sourceVerification" ||
          !Object.keys(sourceFields).every((k) =>
            sameValue(
              request[k as keyof SourceVerificationRequest],
              result[k as keyof CandidateSourceVerificationDto],
            ),
          )
        )
          throw new Error();
      } else if (request.action === "ASSESS") {
        if (!["assessment", "pending", "failure"].includes(result.kind))
          throw new Error();
      } else {
        if (
          result.kind !== "decision" ||
          result.receipt.action !== request.action
        )
          throw new Error();
        const saved = result.receipt.review;
        if (
          saved.assessmentId !== request.assessmentId ||
          saved.reason !== request.reason ||
          !sameValue(saved.evidence, request.evidence)
        )
          throw new Error();
        if (
          request.action === "INCLUDE" &&
          saved.sourceVerificationId !== request.sourceVerificationId
        )
          throw new Error();
        if (
          request.action === "EXCLUDE" &&
          saved.sourceVerificationId !== (request.sourceVerificationId ?? null)
        )
          throw new Error();
      }
    }
    return result;
  } catch {
    throw new Error("INVALID_CANDIDATE_REVIEW_RESULT");
  }
}
