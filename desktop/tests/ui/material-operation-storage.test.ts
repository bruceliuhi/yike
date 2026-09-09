// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryStorage } from "../visual/isolation";
import {
  finishMaterialOperation,
  legacyMaterialOperationKey,
  materialOperationKey,
  materialOwner,
  readMaterialOperations,
  storeMaterialOperation,
  type MaterialOwner,
} from "../../src/renderer/pages/profile/materialOperationStorage";
import type { MaterialPending } from "../../src/renderer/domain/materials";

const owner: MaterialOwner = {userId: "TEST-user", accountScope: {id: "TEST-space", version: 1}};
const pending = (): MaterialPending => ({requestId: crypto.randomUUID(), profileVersionId: "TEST-profile", materialId: "TEST-material", kind: "remove", expectedVersion: 1});
beforeEach(() => vi.stubGlobal("localStorage", new MemoryStorage()));
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe("space-bound material operation storage", () => {
  it("reads and finishes the exact original request through standard Storage length/key APIs", () => {
    const original = pending();
    storeMaterialOperation(owner, original);
    expect(Object.keys(localStorage)).not.toContain(materialOperationKey(owner, original.profileVersionId));
    expect(readMaterialOperations(owner, original.profileVersionId)).toEqual({pending: original, historical: []});
    expect(() => storeMaterialOperation(owner, pending())).toThrow();
    finishMaterialOperation(owner, original);
    expect(localStorage.length).toBe(0);
  });
  it("keeps an earlier version of the same space as a visible blocker", () => {
    const original = pending();
    storeMaterialOperation(owner, original);
    const updated = {...owner, accountScope: {id: owner.accountScope!.id, version: 2}};
    expect(readMaterialOperations(updated, original.profileVersionId)).toEqual({pending: null, historical: [{requestId: original.requestId, profileVersionId: original.profileVersionId, accountScope: owner.accountScope}]});
    expect(() => storeMaterialOperation(updated, pending())).toThrow();
    expect(localStorage.length).toBe(1);
  });
  it("isolates another space and user without deleting their original requests", () => {
    const original = pending();
    storeMaterialOperation(owner, original);
    for (const other of [{...owner, accountScope: {id: "TEST-other-space", version: 1}}, {...owner, userId: "TEST-other-user"}]) {
      expect(readMaterialOperations(other, original.profileVersionId)).toEqual({pending: null, historical: []});
      storeMaterialOperation(other, pending());
    }
    expect(readMaterialOperations(owner, original.profileVersionId).pending).toEqual(original);
    expect(localStorage.length).toBe(3);
  });
  it.each(["user", "profile"] as const)("ignores another legitimate dotted %s identity after validating its complete key", (kind) => {
    const original = pending();
    const otherOwner = kind === "user" ? {...owner, userId: owner.userId + ".other"} : owner;
    const otherPending = kind === "profile" ? {...original, profileVersionId: "prefix." + original.profileVersionId} : original;
    storeMaterialOperation(otherOwner, otherPending);
    const otherKey = materialOperationKey(otherOwner, otherPending.profileVersionId);
    const saved = localStorage.getItem(otherKey);
    expect(readMaterialOperations(owner, original.profileVersionId)).toEqual({pending: null, historical: []});
    const current = pending();
    storeMaterialOperation(owner, current);
    expect(readMaterialOperations(owner, current.profileVersionId).pending).toEqual(current);
    expect(localStorage.getItem(otherKey)).toBe(saved);
    expect(localStorage.length).toBe(2);
  });
  it("does not assign or erase a v1 request while opening any current space", () => {
    const original = pending();
    const key = legacyMaterialOperationKey(owner.userId, original.profileVersionId);
    const raw = JSON.stringify(original);
    localStorage.setItem(key, raw);
    for (const accountScope of [null, owner.accountScope, {id: "TEST-other", version: 2}]) {
      const current = {...owner, accountScope};
      expect(readMaterialOperations(current, original.profileVersionId).historical[0]).toEqual({requestId: original.requestId, profileVersionId: original.profileVersionId, accountScope: "unbound"});
      expect(() => storeMaterialOperation(current, pending())).toThrow();
    }
    expect(localStorage.getItem(key)).toBe(raw);
    expect(localStorage.length).toBe(1);
  });
  it("treats a transition from an explicitly missing scope conservatively", () => {
    const original = pending();
    storeMaterialOperation({...owner, accountScope: null}, original);
    expect(readMaterialOperations(owner, original.profileVersionId).historical[0].requestId).toBe(original.requestId);
    expect(() => storeMaterialOperation(owner, pending())).toThrow();
  });
  it("rejects malformed or wrong-owner envelopes instead of erasing the lock", () => {
    const original = pending();
    const key = materialOperationKey(owner, original.profileVersionId);
    for (const raw of ["{", JSON.stringify({schemaVersion: 2, owner: {...owner, userId: "TEST-other"}, pending: original})]) {
      localStorage.setItem(key, raw);
      expect(() => readMaterialOperations(owner, original.profileVersionId)).toThrow();
      expect(() => storeMaterialOperation(owner, pending())).toThrow();
      expect(localStorage.getItem(key)).toBe(raw);
    }
  });
  it("rejects silent write failures and a mismatched terminal request", () => {
    const ignored = vi.spyOn(localStorage, "setItem").mockImplementation(() => {});
    expect(() => storeMaterialOperation(owner, pending())).toThrow("未可靠保存");
    ignored.mockRestore();
    const original = pending();
    storeMaterialOperation(owner, original);
    expect(() => finishMaterialOperation(owner, pending())).toThrow();
    expect(readMaterialOperations(owner, original.profileVersionId).pending).toEqual(original);
  });
  it("requires authenticated, explicit valid owner data", () => {
    expect(() => materialOwner({authenticated: false, userId: owner.userId})).toThrow();
    expect(() => materialOwner({authenticated: true, userId: owner.userId, accountScope: {id: "", version: 0}})).toThrow();
  });
});
