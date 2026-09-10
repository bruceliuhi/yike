// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  clearSearchSuggestion,
  loadSearchSuggestion,
  saveSearchSuggestion,
  type SearchSuggestionRecord,
  type SearchSuggestionScope,
} from "../../src/renderer/pages/tasks/searchSuggestionStorage";

const scope: SearchSuggestionScope = {
  userId: "user-a",
  accountScopeId: "space-a",
  accountScopeVersion: 3,
};
const record: SearchSuggestionRecord = {
  schemaVersion: 1,
  scope,
  request: {
    request_id: "11111111-1111-4111-8111-111111111111",
    draft_id: "22222222-2222-4222-8222-222222222222",
    profile_version_id: "33333333-3333-4333-8333-333333333333",
    draft_revision: 4,
    disclosure: {
      accepted: true,
      profile_sha256: "a".repeat(64),
      model_provider: "controlled-provider",
      model_name: "controlled-model",
      policy_version: "profile-description-v1",
    },
  },
  receipt: null,
};

describe("search suggestion durable request storage", () => {
  beforeEach(() => localStorage.clear());

  it("round trips only the exact user and customer-space version", () => {
    saveSearchSuggestion(record);
    expect(loadSearchSuggestion(scope)).toEqual({ kind: "record", record });
    expect(loadSearchSuggestion({ ...scope, userId: "user-b" })).toEqual({ kind: "empty" });
    expect(loadSearchSuggestion({ ...scope, accountScopeVersion: 4 })).toEqual({ kind: "empty" });
  });

  it("reports corrupt records instead of treating them as empty", () => {
    localStorage.setItem("yike.search-suggestion.v1.user-a.space-a.3", "not-json");
    expect(loadSearchSuggestion(scope)).toEqual({ kind: "error", message: expect.stringMatching(/损坏/) });
  });

  it("fails closed when durable write or readback is unavailable", () => {
    const set = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("full", "QuotaExceededError");
    });
    expect(() => saveSearchSuggestion(record)).toThrow(/无法可靠保存/);
    set.mockRestore();
  });

  it("clears only the exact matching original request", () => {
    saveSearchSuggestion(record);
    expect(clearSearchSuggestion(scope, "different-request")).toBe(false);
    expect(loadSearchSuggestion(scope).kind).toBe("record");
    expect(clearSearchSuggestion(scope, record.request.request_id)).toBe(true);
    expect(loadSearchSuggestion(scope)).toEqual({ kind: "empty" });
  });

  it("does not overwrite a different unresolved original request", () => {
    saveSearchSuggestion(record);
    const replacement: SearchSuggestionRecord = {
      ...record,
      request: { ...record.request, request_id: "44444444-4444-4444-8444-444444444444" },
    };
    expect(() => saveSearchSuggestion(replacement)).toThrow(/已有未结束|原请求/);
    expect(loadSearchSuggestion(scope)).toEqual({ kind: "record", record });
  });
});
