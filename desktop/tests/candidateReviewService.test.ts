import { describe, expect, it, vi } from "vitest";
import { createCandidateReviewService } from "../src/renderer/services/candidateReview";
import { ServiceError } from "../src/renderer/services/contracts";
import { rawEvidenceBinding, rawEvidenceFixture } from "./fixtures/rawCandidateEvidence";
import {
  candidateReviewRequestSchema,
  type ExpectedCandidateReviewResult,
} from "../src/shared/candidateReviewApi";
import {
  assessmentFixture,
  assessmentRequestFixture,
  candidateBinding,
  decisionFixture,
  decisionRequestFixture,
  pageFixture,
  verificationFixture,
  verificationRequestFixture,
} from "./fixtures/candidateReviewApi";

describe("candidate review service fixed transport boundary", () => {
  it("reads raw evidence through the fixed candidate route without changing any original text", async () => {
    const raw = rawEvidenceFixture(), request = vi.fn().mockResolvedValue(raw);
    const controller = new AbortController();
    expect(await createCandidateReviewService(request).getRawEvidence(rawEvidenceBinding,controller.signal)).toEqual(raw);
    expect(request).toHaveBeenCalledExactlyOnceWith("candidates.rawEvidence",`/raw-candidates/${rawEvidenceBinding.candidateId}`,"GET",{candidateId:rawEvidenceBinding.candidateId},controller.signal);
  });
  it.each([{}, {...rawEvidenceBinding,candidateId:"../other"}, {...rawEvidenceBinding,tenantId:"secret"}])("rejects invalid raw evidence expectations before requesting", async expected => {
    const request = vi.fn();
    await expect(createCandidateReviewService(request).getRawEvidence(expected)).rejects.toMatchObject({code:"INVALID_REQUEST",status:422});
    expect(request).not.toHaveBeenCalled();
  });
  it("rejects raw evidence from another source version", async () => {
    const raw = rawEvidenceFixture(), request = vi.fn().mockResolvedValue(raw);
    await expect(createCandidateReviewService(request).getRawEvidence({...rawEvidenceBinding,sourceVersionId:"eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"})).rejects.toMatchObject({code:"INVALID_SERVICE_RESPONSE",status:502});
    expect(request).toHaveBeenCalledTimes(1);
  });
  it("honors cancellation before raw evidence dispatch and before adopting it", async () => {
    const controller = new AbortController(), request = vi.fn();
    controller.abort();
    await expect(createCandidateReviewService(request).getRawEvidence(rawEvidenceBinding,controller.signal)).rejects.toMatchObject({name:"AbortError"});
    expect(request).not.toHaveBeenCalled();
    const late = new AbortController();
    request.mockImplementation(async () => {late.abort(); return rawEvidenceFixture();});
    await expect(createCandidateReviewService(request).getRawEvidence(rawEvidenceBinding,late.signal)).rejects.toMatchObject({name:"AbortError"});
    expect(request).toHaveBeenCalledTimes(1);
  });
  it("lists the strict default page using only the fixed GET route", async () => {
    const raw = pageFixture(),
      request = vi.fn().mockResolvedValue(raw);
    const result = await createCandidateReviewService(request).list();
    expect(result).toEqual(raw);
    expect(request).toHaveBeenCalledExactlyOnceWith(
      "candidates.list",
      "/candidates",
      "GET",
      {},
      undefined,
    );
  });

  it.each([
    ["小红书", "XIAOHONGSHU"],
    ["抖音", "DOUYIN"],
    ["B站", "BILIBILI"],
    ["知乎", "ZHIHU"],
    ["公开网站", "PUBLIC_WEB"],
    ["PUBLIC_WEB", "PUBLIC_WEB"],
  ])(
    "normalizes the UI platform %s and safely encodes query text",
    async (label, platform) => {
      const raw = pageFixture();
      raw.items[0].platform = platform;
      raw.items[0].sourceLabel = platform;
      const request = vi.fn().mockResolvedValue(raw);
      const query = {
        query: "  采购 & a=2 + 中  ",
        platform: label,
        ids: [candidateBinding.candidateId],
      };
      const original = structuredClone(query);
      expect(await createCandidateReviewService(request).list(query)).toEqual(
        raw,
      );
      const payload = { ...query, query: "采购 & a=2 + 中", platform };
      const search = new URLSearchParams({
        ...payload,
        ids: payload.ids.join(","),
      });
      expect(request).toHaveBeenCalledExactlyOnceWith(
        "candidates.list",
        `/candidates?${search}`,
        "GET",
        payload,
        undefined,
      );
      expect(query).toEqual(original);
    },
  );

  it("omits blank UI fields and leaves pagination defaults to the schema", async () => {
    const request = vi.fn().mockResolvedValue(pageFixture());
    await createCandidateReviewService(request).list({
      query: " \t ",
      platform: "\n ",
    });
    expect(request).toHaveBeenCalledExactlyOnceWith(
      "candidates.list",
      "/candidates",
      "GET",
      {},
      undefined,
    );
  });

  it("serializes comma-joined ids and explicit recovery pagination", async () => {
    const raw = pageFixture();
    raw.pageSize = 1;
    const review = decisionFixture().receipt;
    raw.items = [{ ...decisionFixture().candidate, historical: true }];
    const query = {
      ids: [candidateBinding.candidateId],
      reviewRequestId: review.requestId,
      page: 1,
      pageSize: 1,
    };
    const request = vi.fn().mockResolvedValue(raw);
    expect(await createCandidateReviewService(request).list(query)).toEqual(
      raw,
    );
    expect(request.mock.calls[0][1]).toBe(
      `/candidates?page=1&pageSize=1&ids=${candidateBinding.candidateId}&reviewRequestId=TEST.include%3A1`,
    );
    expect(request.mock.calls[0][3]).toEqual(query);
  });

  it("sends a single review and retains the full matching decision DTO", async () => {
    const input = decisionRequestFixture(),
      raw = decisionFixture();
    const request = vi.fn().mockResolvedValue(raw),
      controller = new AbortController();
    expect(
      await createCandidateReviewService(request).review(
        input,
        controller.signal,
      ),
    ).toEqual(raw);
    expect(request).toHaveBeenCalledExactlyOnceWith(
      "candidates.review",
      "/candidate-reviews",
      "POST",
      input,
      controller.signal,
    );
  });

  it("sends one verification with the exact original source evidence", async () => {
    const input = verificationRequestFixture(),
      raw = verificationFixture();
    const request = vi.fn().mockResolvedValue(raw),
      controller = new AbortController();
    expect(
      await createCandidateReviewService(request).verifySource(
        input,
        controller.signal,
      ),
    ).toEqual(raw);
    expect(request).toHaveBeenCalledExactlyOnceWith(
      "candidates.verifySource",
      "/candidate-source-verifications",
      "POST",
      input,
      controller.signal,
    );
  });

  it("encodes the request id in the fixed recovery route and matches known context", async () => {
    const input = assessmentRequestFixture();
    const raw = {
      kind: "assessment",
      requestId: input.requestId,
      candidateId: input.candidateId,
      assessment: assessmentFixture(),
    };
    const request = vi.fn().mockResolvedValue(raw),
      controller = new AbortController();
    expect(
      await createCandidateReviewService(request).getRequest(
        input.requestId,
        {
          binding: candidateBinding,
          request: candidateReviewRequestSchema.parse(input),
        },
        controller.signal,
      ),
    ).toEqual(raw);
    expect(request).toHaveBeenCalledExactlyOnceWith(
      "candidates.request",
      "/candidate-review-requests/TEST.assess%3A1",
      "GET",
      { requestId: input.requestId },
      controller.signal,
    );
  });

  it("does not insert absent ASSESS retryOf or EXCLUDE sourceVerificationId", async () => {
    const input = assessmentRequestFixture();
    const request = vi
      .fn()
      .mockResolvedValue({
        kind: "pending",
        requestId: input.requestId,
        candidateId: input.candidateId,
        status: "PROCESSING",
      });
    const service = createCandidateReviewService(request);
    await service.review(input);
    expect(request.mock.calls[0][3]).toEqual(input);
    expect(request.mock.calls[0][3]).not.toHaveProperty("retryOf");
    const { sourceVerificationId: _source, ...decision } =
      decisionRequestFixture();
    request.mockResolvedValue({});
    await expect(
      service.review({ ...decision, action: "EXCLUDE" }),
    ).rejects.toMatchObject({ code: "INVALID_SERVICE_RESPONSE" });
    expect(request.mock.calls[1][3]).not.toHaveProperty("sourceVerificationId");
  });

  it.each(
    [
      null,
      [],
      "secret",
      { platform: "arbitrary" },
      { platform: " PUBLIC_WEB " },
      { query: 2 },
      { pageSize: 101 },
      { page: 0 },
      { url: "https://private.invalid" },
      { method: "DELETE" },
      { headers: {} },
      { ids: [] },
      { ids: [candidateBinding.candidateId], reviewRequestId: "TEST.a" },
      {
        ids: [candidateBinding.candidateId],
        reviewRequestId: "TEST.a",
        page: 2,
        pageSize: 1,
      },
    ].map((query) => [query]),
  )("rejects invalid list input without a dispatch: %j", async (query) => {
    const request = vi.fn();
    await expect(
      createCandidateReviewService(request).list(query),
    ).rejects.toMatchObject({ code: "INVALID_REQUEST", status: 422 });
    expect(request).not.toHaveBeenCalled();
  });

  it.each(["review", "verifySource"] as const)(
    "rejects malformed %s requests without exposing input",
    async (method) => {
      const request = vi.fn();
      const error = await createCandidateReviewService(request)
        [method]({ secret: "private-data" })
        .catch((e: unknown) => e);
      expect(error).toBeInstanceOf(ServiceError);
      expect(error).toMatchObject({ code: "INVALID_REQUEST", status: 422 });
      expect(JSON.stringify(error)).not.toContain("private-data");
      expect(error).not.toHaveProperty("cause");
      expect(request).not.toHaveBeenCalled();
    },
  );

  it.each([
    ["bad/id", undefined],
    ["TEST.valid", { requestId: "TEST.other" }],
    ["TEST.valid", { candidateId: "bad" }],
    ["TEST.valid", { request: assessmentRequestFixture() }],
    [
      "TEST.valid",
      {
        candidateId: "88888888-8888-4888-8888-888888888888",
        binding: candidateBinding,
      },
    ],
  ])(
    "rejects invalid recovery context before dispatch",
    async (id, expected) => {
      const request = vi.fn();
      await expect(
        createCandidateReviewService(request).getRequest(
          id,
          expected as unknown as Omit<
            ExpectedCandidateReviewResult,
            "requestId"
          >,
        ),
      ).rejects.toMatchObject({ code: "INVALID_REQUEST", status: 422 });
      expect(request).not.toHaveBeenCalled();
    },
  );

  it.each([
    null,
    {},
    { ...pageFixture(), secret: "provider-secret" },
    { ...pageFixture(), pageSize: 10 },
  ])("rejects malformed or mismatched page data", async (raw) => {
    const request = vi.fn().mockResolvedValue(raw);
    await expect(
      createCandidateReviewService(request).list(),
    ).rejects.toMatchObject({ code: "INVALID_SERVICE_RESPONSE", status: 502 });
    expect(request).toHaveBeenCalledTimes(1);
  });

  it("requires the original review's sourceVerificationId, not merely a valid decision", async () => {
    const raw = decisionFixture();
    raw.receipt.review.sourceVerificationId =
      "88888888-8888-4888-8888-888888888888";
    const request = vi.fn().mockResolvedValue(raw);
    await expect(
      createCandidateReviewService(request).review(decisionRequestFixture()),
    ).rejects.toMatchObject({ code: "INVALID_SERVICE_RESPONSE", status: 502 });
    expect(request).toHaveBeenCalledTimes(1);
  });

  it.each([
    "status",
    "openingMethod",
    "locator",
    "excerpt",
    "contactMethod",
  ] as const)("matches the original verification %s", async (field) => {
    const raw = verificationFixture();
    Object.assign(raw, {
      [field]: {
        status: "BLOCKED",
        openingMethod: "IN_PLATFORM",
        locator: "other",
        excerpt: "other",
        contactMethod: "NONE",
      }[field],
    });
    const request = vi.fn().mockResolvedValue(raw);
    await expect(
      createCandidateReviewService(request).verifySource(
        verificationRequestFixture(),
      ),
    ).rejects.toMatchObject({ code: "INVALID_SERVICE_RESPONSE", status: 502 });
  });

  it.each([401, 404, 409, 501, 503])(
    "preserves valid ServiceError %s without retry",
    async (status) => {
      const error = new ServiceError("BACKEND_ERROR", "安全的服务错误", status),
        request = vi.fn().mockRejectedValue(error);
      await expect(
        createCandidateReviewService(request).review(
          assessmentRequestFixture(),
        ),
      ).rejects.toBe(error);
      expect(request).toHaveBeenCalledTimes(1);
    },
  );

  it.each([
    new Error("provider-secret"),
    "private-token",
    { message: "private-url" },
  ])("normalizes unknown transport errors safely", async (error) => {
    const request = vi.fn().mockRejectedValue(error);
    const caught = await createCandidateReviewService(request)
      .list()
      .catch((e: unknown) => e);
    expect(caught).toBeInstanceOf(ServiceError);
    expect(caught).toMatchObject({ code: "NETWORK_ERROR" });
    expect(caught).not.toHaveProperty("cause");
    expect(JSON.stringify(caught)).not.toMatch(
      /provider-secret|private-token|private-url/,
    );
    expect(request).toHaveBeenCalledTimes(1);
  });

  const operations = [
    ["list", undefined, pageFixture()],
    [
      "review",
      assessmentRequestFixture(),
      {
        kind: "pending",
        requestId: "TEST.assess:1",
        candidateId: candidateBinding.candidateId,
        status: "UNKNOWN",
        code: "assessment_unknown",
      },
    ],
    ["verifySource", verificationRequestFixture(), verificationFixture()],
    ["getRequest", "TEST.include:1", decisionFixture()],
  ] as const;
  it.each(operations)(
    "checks cancellation before %s dispatch and after completion",
    async (method, input, raw) => {
      const controller = new AbortController(),
        request = vi.fn().mockResolvedValue(raw);
      const service = createCandidateReviewService(request);
      const call = () =>
        method === "getRequest"
          ? service.getRequest(input as string, undefined, controller.signal)
          : service[method](input, controller.signal);
      controller.abort();
      await expect(call()).rejects.toMatchObject({ name: "AbortError" });
      expect(request).not.toHaveBeenCalled();
      const late = new AbortController();
      request.mockImplementation(async () => {
        late.abort();
        return raw;
      });
      const result =
        method === "getRequest"
          ? service.getRequest(input as string, undefined, late.signal)
          : service[method](input, late.signal);
      await expect(result).rejects.toMatchObject({ name: "AbortError" });
      expect(request).toHaveBeenCalledTimes(1);
      expect(request.mock.calls[0][4]).toBe(late.signal);
    },
  );

  it("propagates a transport AbortError without normalizing or retrying", async () => {
    const error = new DOMException("Cancelled", "AbortError"),
      request = vi.fn().mockRejectedValue(error);
    await expect(createCandidateReviewService(request).list()).rejects.toBe(
      error,
    );
    expect(request).toHaveBeenCalledTimes(1);
  });

  it.each([
    new Date(),
    new Map(),
    Object.defineProperty({}, "query", {
      enumerable: true,
      get() {
        throw new Error("private-getter");
      },
    }),
  ])("rejects non-query objects without raw input errors", async (query) => {
    const request = vi.fn();
    const error = await createCandidateReviewService(request)
      .list(query)
      .catch((e: unknown) => e);
    expect(error).toMatchObject({ code: "INVALID_REQUEST", status: 422 });
    expect(JSON.stringify(error)).not.toContain("private-getter");
    expect(request).not.toHaveBeenCalled();
  });

  it("rejects review bodies larger than 64 KiB before dispatch", async () => {
    const input = decisionRequestFixture();
    input.reason = "\u0001".repeat(2000);
    for (const key of Object.keys(
      input.evidence,
    ) as (keyof typeof input.evidence)[])
      input.evidence[key] = "\u0001".repeat(2000);
    const request = vi.fn();
    await expect(
      createCandidateReviewService(request).review(input),
    ).rejects.toMatchObject({ code: "INVALID_REQUEST", status: 422 });
    expect(request).not.toHaveBeenCalled();
  });

  it.each(["review", "verifySource", "getRequest"] as const)(
    "rejects a valid but wrong-kind %s response without follow-up",
    async (method) => {
      const input = assessmentRequestFixture();
      const raw = { ...verificationFixture(), requestId: input.requestId };
      const request = vi.fn().mockResolvedValue(raw),
        service = createCandidateReviewService(request);
      const result =
        method === "review"
          ? service.review(input)
          : method === "verifySource"
            ? service.verifySource(verificationRequestFixture())
            : service.getRequest(input.requestId, {
                request: candidateReviewRequestSchema.parse(input),
              });
      await expect(result).rejects.toMatchObject({
        code: "INVALID_SERVICE_RESPONSE",
        status: 502,
      });
      expect(request).toHaveBeenCalledTimes(1);
    },
  );
});
