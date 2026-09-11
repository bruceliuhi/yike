import { webcrypto } from "node:crypto";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { PUBLIC_SAMPLE } from "../../src/renderer/pages/Opportunities";
import {
  makeCoachInput,
  readCoachSuggestion,
  draftSaveKey,
  draftSaveBindingFromKey,
  draftSnapshot,
  snapshotDigest,
  readDraftSaveReceipt,
  type CoachInput,
  type CoachSuggestion,
} from "../../src/renderer/domain/shortCoach";
import type { ContactDraft } from "../../src/renderer/domain/models";
const row = {
  ...PUBLIC_SAMPLE,
  id: "TEST-coach",
  sample: false,
  sourceStatus: "OPEN",
  profileStatus: "CONFIRMED",
  profileVersionId: "TEST-profile",
  sourceEvidenceVersion: "v1",
  sourceObservedAt: "2026-09-09T08:00:00Z",
  excerpt: "TEST原文：服务范围需要核对。",
};
const draft: ContactDraft = {
  opportunityId: row.id,
  channel: "comment",
  version: 1,
  content: "TEST人工原稿",
  savedContent: "TEST人工原稿",
  recipient: "",
  accountId: "",
};
function response(input: CoachInput): CoachSuggestion {
  return {
    suggestionId: "TEST-suggestion",
    binding: input.binding,
    content: "TEST请问服务范围？",
    question: "TEST请问服务范围？",
    context: { summary: "TEST依据服务范围原文", quoteIds: ["quote-1"] },
    quotes: [
      {
        id: "quote-1",
        text: row.excerpt,
        start: 0,
        end: row.excerpt.length,
        sourceUrl: row.url,
        sourceEvidenceVersion: "v1",
      },
    ],
    checks: [
      {
        kind: "CONTEXT",
        status: "SUPPORTED",
        message: "TEST有原文依据",
        quoteIds: ["quote-1"],
      },
    ],
    createdAt: new Date(Date.now() - 1000).toISOString(),
    expiresAt: new Date(Date.now() + 60_000).toISOString(),
  };
}
beforeEach(() => vi.stubGlobal("crypto", webcrypto));
describe("R4 short coach evidence contract", () => {
  it('binds exact material provenance while preserving the legacy snapshot digest',async()=>{
    const snapshot=draftSnapshot(row,draft);
    const legacy=await snapshotDigest(snapshot);
    const ref={sourceProfileVersionId:'11111111-1111-4111-8111-111111111111',materialId:'m',materialVersion:4,extractionId:'e',quote:draft.content};
    const withRef={...snapshot,draft:{...snapshot.draft,materialReferences:[ref]}};
    expect(await snapshotDigest(withRef)).not.toBe(legacy);
    expect(await snapshotDigest({...snapshot,draft:{...snapshot.draft,materialReferences:[]}})).not.toBe(legacy);
    expect(await snapshotDigest({...withRef,draft:{...withRef.draft,materialReferences:[{...ref,materialVersion:5}]}})).not.toBe(await snapshotDigest(withRef));
    expect(await snapshotDigest(draftSnapshot(row,draft))).toBe(legacy);
    expect(()=>snapshotDigest({...withRef,draft:{...withRef.draft,materialReferences:[ref,ref]}})).toThrow();
  });
  it("accepts exact source anchors and identity without a cost/count default", async () => {
    const input = await makeCoachInput(row, draft, "scope", "TEST-request", {
      id: "TEST-space",
      version: 1,
    });
    const result = readCoachSuggestion(response(input), input);
    expect(result.binding.draftHash).toMatch(/^[a-f0-9]{64}$/);
    expect(result).not.toHaveProperty("cost");
    expect(result.quotes[0].text).toBe(input.sourceText);
  });
  it.each([
    "requestId",
    "opportunityId",
    "profileVersionId",
    "sourceEvidenceVersion",
    "draftHash",
    "channel",
    "purpose",
  ])("rejects mismatched %s", async (field) => {
    const input = await makeCoachInput(row, draft, "scope", "TEST-request", {
      id: "TEST-space",
      version: 1,
    });
    const value = response(input);
    value.binding = {
      ...value.binding,
      [field]:
        field === "draftHash"
          ? "f".repeat(64)
          : field === "channel"
            ? "dm"
            : field === "purpose"
              ? "materials"
              : "TEST-other",
    };
    expect(() => readCoachSuggestion(value, input)).toThrow();
  });
  it("rejects invented quotes, unsafe URLs, unknown anchors and expired suggestions", async () => {
    const input = await makeCoachInput(row, draft, "scope", "TEST-request", {
      id: "TEST-space",
      version: 1,
    });
    for (const change of [
      (v: CoachSuggestion) => {
        v.quotes[0].text = "TEST没有此原文";
      },
      (v: CoachSuggestion) => {
        v.quotes[0].sourceUrl = "javascript:alert(1)";
      },
      (v: CoachSuggestion) => {
        v.context.quoteIds = ["missing"];
      },
      (v: CoachSuggestion) => {
        v.expiresAt = new Date(Date.now() - 1).toISOString();
      },
    ]) {
      const value = response(input);
      change(value);
      expect(() => readCoachSuggestion(value, input)).toThrow();
    }
  });
  it.each(["CONTEXT", "PROMISE"] as const)(
    "rejects supported %s without evidence anchors",
    async (kind) => {
      const input = await makeCoachInput(row, draft, "scope", "TEST-request", {
        id: "TEST-space",
        version: 1,
      });
      const value = response(input);
      value.checks = [
        { kind, status: "SUPPORTED", message: "TEST无依据", quoteIds: [] },
      ];
      expect(() => readCoachSuggestion(value, input)).toThrow(/缺少原文依据/);
      value.checks[0].status = "NEEDS_REVIEW";
      expect(readCoachSuggestion(value, input).checks[0].status).toBe(
        "NEEDS_REVIEW",
      );
      value.checks = [
        {
          kind: "LENGTH",
          status: "SUPPORTED",
          message: "TEST字数检查",
          quoteIds: [],
        },
      ];
      expect(readCoachSuggestion(value, input).checks[0].kind).toBe("LENGTH");
    },
  );
  it("does not accept samples or unversioned source data as checked evidence", async () => {
    await expect(
      makeCoachInput({ ...row, sample: true }, draft, "scope", "id", {
        id: "TEST-space",
        version: 1,
      }),
    ).rejects.toThrow("公开研究样例");
    await expect(
      makeCoachInput(
        { ...row, sourceEvidenceVersion: undefined },
        draft,
        "scope",
        "id",
        { id: "TEST-space", version: 1 },
      ),
    ).rejects.toThrow("尚未核验");
  });
  it("accepts only a bound saved snapshot and confirmed failed receipt", async () => {
    const snapshot = draftSnapshot(row, draft);
    const binding = {
      opportunityId: row.id,
      channel: draft.channel,
      requestId: "TEST-save",
      contentHash: await snapshotDigest(snapshot),
    };
    expect(draftSaveBindingFromKey(draftSaveKey(binding))).toEqual(binding);
    await expect(
      readDraftSaveReceipt(
        { binding, status: "SUCCEEDED", confirmed: true, snapshot },
        binding,
      ),
    ).resolves.toMatchObject({ status: "SUCCEEDED" });
    await expect(
      readDraftSaveReceipt(
        { binding, status: "FAILED", confirmed: false },
        binding,
      ),
    ).rejects.toThrow();
    await expect(
      readDraftSaveReceipt(
        {
          binding,
          status: "SUCCEEDED",
          confirmed: true,
          snapshot: { ...snapshot, draft: { ...draft, content: "other" } },
        },
        binding,
      ),
    ).rejects.toThrow();
    await expect(
      readDraftSaveReceipt(
        {
          binding: { ...binding, requestId: "other" },
          status: "FAILED",
          confirmed: true,
        },
        binding,
      ),
    ).rejects.toThrow();
  });
  it.each([
    '["id","comment","req","bad"]',
    '["id","dm","req"]',
    '["","comment","req","' + "a".repeat(64) + '"]',
  ])("rejects malformed save binding %s", (key) =>
    expect(() => draftSaveBindingFromKey(key)).toThrow(),
  );
});
