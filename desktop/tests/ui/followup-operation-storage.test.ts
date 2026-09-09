// @vitest-environment jsdom
import { beforeEach, expect, it } from "vitest";
import {
  followupOwner,
  readFollowupOperations,
  storeFollowupOperation,
  finishFollowupOperation,
  followupOperationStorageKey,
} from "../../src/renderer/pages/followups/followupOperationStorage";
import { followupKey } from "../../src/renderer/domain/followup";
import { operationLedgerKey } from "../../src/renderer/app/operationLedger";
const owner = followupOwner({
  authenticated: true,
  userId: "TEST-user",
  accountScope: { id: "TEST-A", version: 1 },
});
const b = {
  opportunityId: "TEST-opp",
  profileVersionId: "TEST-profile",
  action: "create" as const,
  targetId: "",
  targetRevision: 0,
  requestId: "TEST-request",
};
beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
});
it("separates spaces and requires the exact original space version to settle", () => {
  storeFollowupOperation(owner, b);
  const other = { ...owner, accountScope: { id: "TEST-B", version: 1 } };
  expect(readFollowupOperations(other)).toEqual({
    pending: null,
    historical: [],
  });
  expect(() => finishFollowupOperation(other, b)).toThrow();
  const version = { ...owner, accountScope: { id: "TEST-A", version: 2 } };
  expect(readFollowupOperations(version).historical[0]).toEqual({
    binding: b,
    accountScope: owner.accountScope,
  });
  expect(() =>
    storeFollowupOperation(version, { ...b, requestId: "TEST-new" }),
  ).toThrow();
  expect(readFollowupOperations(owner).pending).toEqual(b);
});
it("keeps scope-less history unbound instead of adopting it when scope becomes available", () => {
  const missing = { ...owner, accountScope: null };
  storeFollowupOperation(missing, b);
  expect(readFollowupOperations(owner).historical[0].accountScope).toBeNull();
  expect(() => storeFollowupOperation(owner, b)).toThrow();
});
it("preserves old session-only operations durably without assigning any current scope", () => {
  const old = "yike.ui.draft.v1.followup-operations." + owner.userId;
  sessionStorage.setItem(old, JSON.stringify({ [followupKey(b)]: "PENDING" }));
  expect(readFollowupOperations(owner).historical[0].accountScope).toBe(
    "unbound",
  );
  sessionStorage.clear();
  expect(
    readFollowupOperations({
      ...owner,
      accountScope: { id: "TEST-B", version: 2 },
    }).historical[0].binding,
  ).toEqual(b);
  expect(
    JSON.parse(
      localStorage.getItem(
        operationLedgerKey("followup-operations", owner.userId),
      )!,
    ),
  ).toEqual({ [followupKey(b)]: "PENDING" });
});
it("does not erase a replaced request or accept forged owner metadata", () => {
  storeFollowupOperation(owner, b);
  const key = followupOperationStorageKey(owner);
  const stored = JSON.parse(localStorage.getItem(key)!);
  localStorage.setItem(
    key,
    JSON.stringify({ ...stored, pending: { ...b, requestId: "TEST-other" } }),
  );
  expect(() => finishFollowupOperation(owner, b)).toThrow();
  expect(readFollowupOperations(owner).pending?.requestId).toBe("TEST-other");
  localStorage.setItem(
    key,
    JSON.stringify({ ...stored, owner: { ...owner, userId: "TEST-other" } }),
  );
  expect(() => readFollowupOperations(owner)).toThrow();
});
it("does not confuse dotted user IDs while inspecting another user ledger", () => {
  storeFollowupOperation({ ...owner, userId: "TEST-user.child" }, b);
  expect(readFollowupOperations(owner)).toEqual({
    pending: null,
    historical: [],
  });
});
