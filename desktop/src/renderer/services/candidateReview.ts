import { z } from "zod";
import type { ApiOperation } from "../../shared/contracts";
import {
  candidateBindingSchema,
  candidatePlatformSchema,
  candidateQuerySchema,
  candidateRequestIdSchema,
  candidateReviewRequestSchema,
  sourceVerificationRequestSchema,
  parseCandidatePage,
  parseCandidateReviewResult,
  type CandidateQueryInput,
  type CandidateReviewResultDto,
  type CandidateSourceVerificationDto,
  type ExpectedCandidateReviewResult,
  type ReviewedCandidatePageDto,
} from "../../shared/candidateReviewApi";
import { ServiceError } from "./contracts";
import { expectedRawCandidateEvidenceSchema, parseRawCandidateEvidence, type RawCandidateEvidenceDto } from "../../shared/rawCandidateEvidence";

export const CANDIDATE_PLATFORM_LABELS = {
  XIAOHONGSHU: "小红书",
  DOUYIN: "抖音",
  BILIBILI: "B站",
  ZHIHU: "知乎",
  PUBLIC_WEB: "公开网站",
} as const satisfies Record<z.infer<typeof candidatePlatformSchema>, string>;

export interface CandidateReviewService {
  getRawEvidence(expected: unknown, signal?: AbortSignal): Promise<RawCandidateEvidenceDto>;
  list(
    query?: unknown,
    signal?: AbortSignal,
  ): Promise<ReviewedCandidatePageDto>;
  review(
    input: unknown,
    signal?: AbortSignal,
  ): Promise<CandidateReviewResultDto>;
  verifySource(
    input: unknown,
    signal?: AbortSignal,
  ): Promise<CandidateSourceVerificationDto>;
  getRequest(
    requestId: string,
    expected?: Omit<ExpectedCandidateReviewResult, "requestId">,
    signal?: AbortSignal,
  ): Promise<CandidateReviewResultDto>;
}

type Transport = (
  operation: ApiOperation,
  path: string,
  method: string,
  payload: unknown,
  signal?: AbortSignal,
) => Promise<unknown>;
const invalidInput = () =>
  new ServiceError(
    "INVALID_REQUEST",
    "候选审核请求不完整或已变化，请重新核对。",
    422,
  );
const invalidResponse = () =>
  new ServiceError(
    "INVALID_SERVICE_RESPONSE",
    "候选审核服务返回的数据不完整或不匹配，请重新核对。",
    502,
  );

function validate<T>(schema: z.ZodType<T>, input: unknown): T {
  try {
    return schema.parse(input);
  } catch {
    throw invalidInput();
  }
}

/** UI-only normalization: response data and submitted human evidence remain untouched. */
export function normalizeCandidateQuery(
  input: unknown = {},
): CandidateQueryInput {
  try {
    if (
      !input ||
      typeof input !== "object" ||
      Array.isArray(input) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(input))
    )
      throw invalidInput();
    const query = { ...input } as Record<string, unknown>;
    if (typeof query.query === "string") {
      query.query = query.query.trim();
      if (!query.query) delete query.query;
    }
    if (typeof query.platform === "string") {
      if (!query.platform.trim()) delete query.platform;
      else {
        const mapped = Object.entries(CANDIDATE_PLATFORM_LABELS).find(
          ([, label]) => label === query.platform,
        );
        if (mapped) query.platform = mapped[0];
      }
    }
    return validate(candidateQuerySchema, query);
  } catch {
    throw invalidInput();
  }
}

const recoveryContext = z
  .object({
    candidateId: candidateBindingSchema.shape.candidateId.optional(),
    binding: candidateBindingSchema.optional(),
    request: z
      .union([candidateReviewRequestSchema, sourceVerificationRequestSchema])
      .optional(),
  })
  .strict();

function recoveryExpectation(
  requestId: string,
  input: unknown,
): ExpectedCandidateReviewResult {
  const id = validate(candidateRequestIdSchema, requestId);
  const context = validate(recoveryContext, input === undefined ? {} : input);
  if (
    (context.request && context.request.requestId !== id) ||
    (context.candidateId &&
      context.binding &&
      context.candidateId !== context.binding.candidateId) ||
    (context.candidateId &&
      context.request &&
      context.candidateId !== context.request.candidateId) ||
    (context.request &&
      context.binding &&
      Object.keys(candidateBindingSchema.shape).some(
        (key) =>
          context.request![key as keyof typeof context.binding] !==
          context.binding![key as keyof typeof context.binding],
      ))
  )
    throw invalidInput();
  return { ...context, requestId: id };
}

function checkAbort(signal?: AbortSignal): void {
  if (signal?.aborted) throw new DOMException("请求已取消。", "AbortError");
}

/** Exactly one explicit operation; IPC cancellation prevents adoption, not backend execution. */
export function createCandidateReviewService(
  request: Transport,
): CandidateReviewService {
  async function dispatch<T>(
    operation: ApiOperation,
    path: string,
    method: string,
    payload: unknown,
    parse: (raw: unknown) => T,
    signal?: AbortSignal,
  ): Promise<T> {
    checkAbort(signal);
    let raw: unknown;
    try {
      raw = await request(operation, path, method, payload, signal);
    } catch (error) {
      checkAbort(signal);
      if (error instanceof DOMException && error.name === "AbortError")
        throw error;
      if (error instanceof ServiceError) throw error;
      throw new ServiceError(
        "NETWORK_ERROR",
        "候选审核服务暂时无法连接，请稍后重试。",
        0,
      );
    }
    checkAbort(signal);
    let parsed: T;
    try {
      parsed = parse(raw);
    } catch {
      throw invalidResponse();
    }
    checkAbort(signal);
    return parsed;
  }
  return {
    async getRawEvidence(input, signal) {
      checkAbort(signal);
      const expected = validate(expectedRawCandidateEvidenceSchema, input);
      return dispatch(
        "candidates.rawEvidence",
        `/raw-candidates/${encodeURIComponent(expected.candidateId)}`,
        "GET",
        { candidateId: expected.candidateId },
        raw => parseRawCandidateEvidence(raw, expected),
        signal,
      );
    },
    async list(input, signal) {
      checkAbort(signal);
      const query = normalizeCandidateQuery(input);
      const search = new URLSearchParams();
      for (const [key, value] of Object.entries(query)) {
        if (value !== undefined)
          search.set(
            key,
            Array.isArray(value) ? value.join(",") : String(value),
          );
      }
      search.set("evidenceVersion", "1");
      const suffix = `?${search}`;
      return dispatch(
        "candidates.list",
        `/candidates${suffix}`,
        "GET",
        query,
        (raw) => parseCandidatePage(raw, query),
        signal,
      );
    },
    async review(input, signal) {
      checkAbort(signal);
      const payload = validate(candidateReviewRequestSchema, input);
      return dispatch(
        "candidates.review",
        "/candidate-reviews?evidenceVersion=1",
        "POST",
        payload,
        (raw) =>
          parseCandidateReviewResult(raw, {
            requestId: payload.requestId,
            request: payload,
          }),
        signal,
      );
    },
    async verifySource(input, signal) {
      checkAbort(signal);
      const payload = validate(sourceVerificationRequestSchema, input);
      return dispatch(
        "candidates.verifySource",
        "/candidate-source-verifications?evidenceVersion=1",
        "POST",
        payload,
        (raw) => {
          const result = parseCandidateReviewResult(raw, {
            requestId: payload.requestId,
            request: payload,
          });
          if (result.kind !== "sourceVerification") throw invalidResponse();
          return result;
        },
        signal,
      );
    },
    async getRequest(requestId, expected, signal) {
      checkAbort(signal);
      const context = recoveryExpectation(requestId, expected);
      return dispatch(
        "candidates.request",
        `/candidate-review-requests/${encodeURIComponent(context.requestId)}?evidenceVersion=1`,
        "GET",
        { requestId: context.requestId },
        (raw) => parseCandidateReviewResult(raw, context),
        signal,
      );
    },
  };
}
