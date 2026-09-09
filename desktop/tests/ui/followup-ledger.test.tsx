// @vitest-environment jsdom
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import {
  useOperationLedger,
  operationLedgerKey,
} from "../../src/renderer/app/operationLedger";
import {
  followupKey,
  bindingFromKey,
  readReceipt,
  type FollowupBinding,
} from "../../src/renderer/domain/followup";
import { clearLocalDrafts } from "../../src/renderer/app/hooks";
const binding: FollowupBinding = {
  opportunityId: "TEST-opp",
  profileVersionId: "TEST-version",
  action: "create",
  targetId: "",
  targetRevision: 0,
  requestId: "TEST-request",
};
beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
});
afterEach(cleanup);
it("accepts a six-part followup identity and preserves it through draft cleanup", () => {
  const user = crypto.randomUUID();
  const hook = renderHook(() =>
    useOperationLedger("followup-operations", user),
  );
  act(() => hook.result.current[1]({ [followupKey(binding)]: "PENDING" }));
  act(() => clearLocalDrafts());
  expect(
    JSON.parse(
      localStorage.getItem(operationLedgerKey("followup-operations", user))!,
    ),
  ).toEqual({ [followupKey(binding)]: "PENDING" });
  expect(bindingFromKey(followupKey(binding))).toEqual(binding);
});
it.each([
  "wrong action",
  "negative revision",
  "empty request",
  "wrong status",
  "oversized combined key",
])("rejects %s before dispatch", (kind) => {
  const hook = renderHook(() =>
    useOperationLedger("followup-operations", crypto.randomUUID()),
  );
  const value = { ...binding };
  if (kind === "wrong action") value.action = "bad" as never;
  if (kind === "negative revision") value.targetRevision = -1;
  if (kind === "empty request") value.requestId = "";
  if (kind === "oversized combined key") {
    value.opportunityId = "x".repeat(512);
    value.profileVersionId = "y".repeat(512);
  }
  const dispatch = vi.fn();
  expect(() =>
    act(() => {
      hook.result.current[1]({
        [followupKey(value)]: kind === "wrong status" ? "SENT" : "PENDING",
      });
      dispatch();
    }),
  ).toThrow();
  expect(dispatch).not.toHaveBeenCalled();
});
it("rejects unconfirmed or identity-mismatched terminal receipts", () => {
  expect(() => readReceipt({ binding, status: "FAILED" }, binding)).toThrow();
  expect(() =>
    readReceipt(
      {
        binding: { ...binding, profileVersionId: "other" },
        status: "FAILED",
        confirmed: true,
      },
      binding,
    ),
  ).toThrow();
});
