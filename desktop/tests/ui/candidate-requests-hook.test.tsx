// @vitest-environment jsdom
import { StrictMode } from "react";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AppContextValue } from "../../src/renderer/app/context";
import { service } from "../../src/renderer/services/client";
import { ServiceError } from "../../src/renderer/services/contracts";
import { createCandidateReviewService } from "../../src/renderer/services/candidateReview";
import { parseRoute } from "../../src/renderer/domain/routes";
import { clearLocalDrafts } from "../../src/renderer/app/hooks";
import { useCandidateRequests } from "../../src/renderer/pages/opportunities/useCandidateRequests";
import {
  assessmentFixture,
  assessmentRequestFixture,
  candidateBinding,
  decisionFixture,
  decisionRequestFixture,
  verificationFixture,
  verificationRequestFixture,
} from "../fixtures/candidateReviewApi";

let context: AppContextValue;
let transport: ReturnType<
  typeof vi.fn<Parameters<typeof createCandidateReviewService>[0]>
>;
const stored = () =>
  localStorage.getItem(
    "yike.ui.operation.v1.candidate-request-operations." +
      encodeURIComponent(context.session.userId!),
  );
vi.mock("../../src/renderer/app/context", () => ({ useApp: () => context }));
beforeEach(() => {
  transport = vi.fn(
    async (
      operation: string,
      _path: string,
      _method: string,
      input: unknown,
    ) => {
      const request = input as { requestId: string };
      expect(stored()).toContain(request.requestId);
      if (operation === "candidates.verifySource") return verificationFixture();
      if (request.requestId === decisionRequestFixture().requestId)
        return decisionFixture();
      return {
        kind: "assessment",
        requestId: request.requestId,
        candidateId: candidateBinding.candidateId,
        assessment: assessmentFixture(),
      };
    },
  );
  context = {
    service: {
      ...service,
      candidateReview: createCandidateReviewService(transport),
    },
    session: { authenticated: true, userId: crypto.randomUUID() },
    route: parseRoute("#/candidates"),
    navigate: vi.fn(),
    notify: vi.fn(),
    refreshSession: vi.fn(),
  };
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe("explicit candidate requests with durable recovery", () => {
  it.each([
    assessmentRequestFixture,
    verificationRequestFixture,
    decisionRequestFixture,
  ])(
    "persists opaque confirmation before an explicit operation, never on render",
    async (fixture) => {
      const hook = renderHook(() => useCandidateRequests(), {
        wrapper: StrictMode,
      });
      expect(transport).not.toHaveBeenCalled();
      await act(async () => {
        await Promise.all([
          hook.result.current.submit(fixture()),
          hook.result.current.submit(fixture()),
        ]);
      });
      expect(transport).toHaveBeenCalledTimes(1);
      expect(hook.result.current.operations[0].state).toBe("RECORDED");
      expect(hook.result.current.result).toBeTruthy();
      expect(stored()).not.toMatch(
        /采购输送设备|人工核对|https:\/\/example|matchReason|checkedBy/,
      );
    },
  );
  it("does not dispatch when durable storage fails", async () => {
    const hook = renderHook(() => useCandidateRequests());
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("quota");
    });
    await act(async () => {
      await hook.result.current.submit(assessmentRequestFixture());
    });
    expect(transport).not.toHaveBeenCalled();
    expect(hook.result.current.error).toBeTruthy();
  });
  it("does not bypass an unresolved legacy candidate confirmation", async () => {
    const key = JSON.stringify([
      candidateBinding.candidateId,
      "INCLUDE",
      "TEST.old-review",
      "a".repeat(64),
    ]);
    localStorage.setItem(
      "yike.ui.operation.v1.candidate-reviews." +
        encodeURIComponent(context.session.userId!),
      JSON.stringify({ [key]: "PENDING" }),
    );
    const hook = renderHook(() => useCandidateRequests());
    await act(async () => {
      await hook.result.current.submit(assessmentRequestFixture());
    });
    expect(transport).not.toHaveBeenCalled();
    expect(hook.result.current.error).toBeTruthy();
  });
  it("keeps an unknown request through remount and 404; lookup never creates another POST", async () => {
    transport.mockRejectedValueOnce(new ServiceError("NETWORK_ERROR", "超时"));
    const hook = renderHook(() => useCandidateRequests());
    await act(async () => {
      await hook.result.current.submit(assessmentRequestFixture());
    });
    expect(hook.result.current.operations).toHaveLength(1);
    const key = hook.result.current.operations[0].key;
    hook.unmount();
    const again = renderHook(() => useCandidateRequests());
    transport.mockRejectedValueOnce(
      new ServiceError("request_not_found", "未找到", 404),
    );
    await act(async () => {
      await again.result.current.reconcile(key);
    });
    expect(transport.mock.calls.map((call) => call[2])).toEqual([
      "POST",
      "GET",
    ]);
    expect(again.result.current.operations).toHaveLength(1);
    await act(async () => {
      await again.result.current.submit({
        ...assessmentRequestFixture(),
        requestId: "another",
      });
    });
    expect(transport).toHaveBeenCalledTimes(2);
  });
  it("does not permit a new attempt while the freshly queried original is PROCESSING", async () => {
    transport.mockResolvedValue({
      kind: "pending",
      status: "PROCESSING",
      requestId: assessmentRequestFixture().requestId,
      candidateId: candidateBinding.candidateId,
    });
    const hook = renderHook(() => useCandidateRequests());
    await act(async () => {
      await hook.result.current.submit(assessmentRequestFixture());
    });
    expect(hook.result.current.operations).toHaveLength(1);
    await act(async () => {
      await hook.result.current.retryAssessment(
        hook.result.current.operations[0].key,
        true,
      );
    });
    expect(transport.mock.calls.map((call) => call[2])).toEqual([
      "POST",
      "GET",
    ]);
    expect(hook.result.current.operations[0].state).toBe("PROCESSING");
  });
  it("retries an alias only after explicit confirmation and a fresh UNKNOWN result, against its original invocation", async () => {
    const original = assessmentRequestFixture();
    transport.mockResolvedValue({
      kind: "pending",
      status: "UNKNOWN",
      requestId: original.requestId,
      invocationRequestId: "TEST.actual-invocation",
      candidateId: candidateBinding.candidateId,
    });
    const hook = renderHook(() => useCandidateRequests());
    await act(async () => {
      await hook.result.current.submit(original);
    });
    expect(hook.result.current.operations).toHaveLength(1);
    const key = hook.result.current.operations[0].key;
    await act(async () => {
      await hook.result.current.retryAssessment(key, false);
    });
    expect(transport).toHaveBeenCalledTimes(1);
    transport.mockImplementation(async (_operation, _path, method, input) =>
      method === "GET"
        ? {
            kind: "pending",
            status: "UNKNOWN",
            requestId: original.requestId,
            invocationRequestId: "TEST.actual-invocation",
            candidateId: candidateBinding.candidateId,
          }
        : {
            kind: "assessment",
            requestId: (input as { requestId: string }).requestId,
            candidateId: candidateBinding.candidateId,
            assessment: assessmentFixture(),
          },
    );
    await act(async () => {
      await hook.result.current.retryAssessment(key, true);
    });
    expect(transport.mock.calls.map((call) => call[2])).toEqual([
      "POST",
      "GET",
      "POST",
    ]);
    const retry = transport.mock.calls[2][3] as {
      requestId: string;
      retryOf: string;
    };
    expect(retry.requestId).not.toBe(original.requestId);
    expect(retry.retryOf).toBe("TEST.actual-invocation");
    expect(stored()).toContain(retry.requestId);
    expect(hook.result.current.operations).toHaveLength(2);
  });
  it("prevents two same-scope consumers from starting distinct requests for the same candidate", async () => {
    const first = renderHook(() => useCandidateRequests()),
      second = renderHook(() => useCandidateRequests());
    transport.mockRejectedValue(new ServiceError("NETWORK_ERROR", "未知"));
    await act(async () => {
      await Promise.all([
        first.result.current.submit(assessmentRequestFixture()),
        second.result.current.submit({
          ...assessmentRequestFixture(),
          requestId: "TEST.second",
        }),
      ]);
    });
    expect(transport).toHaveBeenCalledTimes(1);
  });
  it("does not race a completed first submission with another consumer's slower confirmation hash", async () => {
    const digest = crypto.subtle.digest.bind(crypto.subtle);
    let release!: () => void;
    let held = false;
    vi.spyOn(crypto.subtle, "digest").mockImplementation(
      async (algorithm, data) => {
        if (
          !held &&
          new TextDecoder().decode(data).includes('"requestId":"TEST.second"')
        ) {
          held = true;
          await new Promise<void>((resolve) => {
            release = resolve;
          });
        }
        return digest(algorithm, data);
      },
    );
    const first = renderHook(() => useCandidateRequests()),
      second = renderHook(() => useCandidateRequests());
    let slow!: Promise<unknown>;
    act(() => {
      slow = second.result.current.submit({
        ...assessmentRequestFixture(),
        requestId: "TEST.second",
      });
    });
    await waitFor(() => expect(release).toBeTypeOf("function"));
    await act(async () => {
      await first.result.current.submit(assessmentRequestFixture());
    });
    expect(first.result.current.operations[0].state).toBe("RECORDED");
    await act(async () => {
      release();
      await slow;
    });
    expect(transport).toHaveBeenCalledTimes(1);
  });
  it("settles only the old ledger and hides a late response on account scope change", async () => {
    let release!: () => void;
    transport.mockImplementationOnce(
      async () =>
        new Promise((resolve) => {
          release = () =>
            resolve({
              kind: "assessment",
              requestId: assessmentRequestFixture().requestId,
              candidateId: candidateBinding.candidateId,
              assessment: assessmentFixture(),
            });
        }),
    );
    const hook = renderHook(() => useCandidateRequests());
    let pending!: Promise<unknown>;
    act(() => {
      pending = hook.result.current.submit(assessmentRequestFixture());
    });
    await waitFor(() => expect(release).toBeTypeOf("function"));
    context = {
      ...context,
      session: {
        ...context.session,
        accountScope: { id: "new-scope", version: 2 },
      },
    };
    hook.rerender();
    await act(async () => {
      release();
      await pending;
    });
    expect(hook.result.current.result).toBeNull();
    expect(hook.result.current.operations).toHaveLength(0);
    expect(stored()).toContain("RECORDED");
  });
  it.each([401, 404, 409, 503])(
    "keeps an original request after HTTP %s and never retries on lookup failure",
    async (status) => {
      transport.mockRejectedValue(
        new ServiceError("backend_error", "尚未核实", status),
      );
      const hook = renderHook(() => useCandidateRequests());
      await act(async () => {
        await hook.result.current.submit(verificationRequestFixture());
      });
      expect(hook.result.current.operations).toHaveLength(1);
      const before = stored(),
        key = hook.result.current.operations[0].key;
      await act(async () => {
        await hook.result.current.reconcile(key);
      });
      expect(stored()).toBe(before);
      expect(transport.mock.calls.map((call) => call[2])).toEqual([
        "POST",
        "GET",
      ]);
      expect(hook.result.current.result).toBeNull();
    },
  );
  it("rejects a wrong confirmation receipt and retains it across clearing drafts and logout", async () => {
    const originalUser = context.session.userId!;
    const raw = decisionFixture();
    raw.receipt.review.sourceVerificationId =
      "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee";
    transport.mockResolvedValue(raw);
    const hook = renderHook(() => useCandidateRequests());
    await act(async () => {
      await hook.result.current.submit(decisionRequestFixture());
    });
    expect(hook.result.current.operations[0].state).toBe("PENDING");
    const before = stored();
    act(() => {
      clearLocalDrafts();
    });
    context = { ...context, session: { authenticated: false } };
    hook.rerender();
    expect(hook.result.current.operations).toHaveLength(0);
    expect(hook.result.current.result).toBeNull();
    expect(
      localStorage.getItem(
        "yike.ui.operation.v1.candidate-request-operations." +
          encodeURIComponent(originalUser),
      ),
    ).toBe(before);
  });
  it("does not dispatch when the user changes target while the confirmation is being hashed", async () => {
    const hook = renderHook(({ variant }) => useCandidateRequests(variant), {
      initialProps: { variant: "first" },
    });
    let pending!: Promise<unknown>;
    act(() => {
      pending = hook.result.current.submit(assessmentRequestFixture());
    });
    hook.rerender({ variant: "other" });
    await act(async () => {
      await pending;
    });
    expect(transport).not.toHaveBeenCalled();
    expect(stored()).toBeNull();
  });
  it("never looks up another user's or account space's operation", async () => {
    const hook = renderHook(() => useCandidateRequests());
    await act(async () => {
      await hook.result.current.submit(assessmentRequestFixture());
    });
    const key = hook.result.current.operations[0].key;
    context = {
      ...context,
      session: {
        ...context.session,
        accountScope: { id: "other", version: 1 },
      },
    };
    hook.rerender();
    await act(async () => {
      await hook.result.current.reconcile(key);
    });
    expect(transport).toHaveBeenCalledTimes(1);
  });
  it("serializes explicit retries from two consumers and will not create a second child", async () => {
    const original = assessmentRequestFixture();
    transport.mockResolvedValue({
      kind: "failure",
      status: "FAILED",
      code: "assessment_failed",
      requestId: original.requestId,
      candidateId: candidateBinding.candidateId,
    });
    const first = renderHook(() => useCandidateRequests()),
      second = renderHook(() => useCandidateRequests());
    await act(async () => {
      await first.result.current.submit(original);
    });
    const key = first.result.current.operations[0].key;
    transport.mockImplementation(async (_op, _path, method, input) =>
      method === "GET"
        ? {
            kind: "failure",
            status: "FAILED",
            code: "assessment_failed",
            requestId: original.requestId,
            candidateId: candidateBinding.candidateId,
          }
        : {
            kind: "assessment",
            requestId: (input as { requestId: string }).requestId,
            candidateId: candidateBinding.candidateId,
            assessment: assessmentFixture(),
          },
    );
    await act(async () => {
      await Promise.all([
        first.result.current.retryAssessment(key, true),
        second.result.current.retryAssessment(key, true),
      ]);
    });
    expect(
      transport.mock.calls.filter((call) => call[2] === "POST"),
    ).toHaveLength(2);
    expect(first.result.current.operations).toHaveLength(2);
    await act(async () => {
      await first.result.current.retryAssessment(key, true);
    });
    expect(
      transport.mock.calls.filter((call) => call[2] === "POST"),
    ).toHaveLength(2);
  });
  it("retains a real 30-second timeout and ignores eventual response without issuing a retry", async () => {
    vi.useFakeTimers();
    let release!: () => void;
    transport.mockImplementationOnce(
      async () =>
        new Promise((resolve) => {
          release = () =>
            resolve({
              kind: "assessment",
              requestId: assessmentRequestFixture().requestId,
              candidateId: candidateBinding.candidateId,
              assessment: assessmentFixture(),
            });
        }),
    );
    const hook = renderHook(() => useCandidateRequests());
    let pending!: Promise<unknown>;
    act(() => {
      pending = hook.result.current.submit(assessmentRequestFixture());
    });
    await act(async () => {
      await vi.waitFor(() => expect(release).toBeTypeOf("function"));
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_001);
      await pending;
    });
    expect(hook.result.current.operations[0].state).toBe("PENDING");
    expect(hook.result.current.error).toBeTruthy();
    await act(async () => {
      release();
      await Promise.resolve();
    });
    expect(hook.result.current.result).toBeNull();
    expect(transport).toHaveBeenCalledTimes(1);
  });
});
