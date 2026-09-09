import { describe, expect, it } from "vitest";
import {
  parseResearchCollection,
  parseResearchTimeline,
  parseSimilarResearch,
  researchBinding,
  type ResearchBinding,
} from "../../src/renderer/domain/opportunityResearch";
import {
  binding,
  collection,
  researchRow,
  similar,
  timeline,
} from "./r4-opportunity-research-fixtures";

describe("R4 research identity and evidence contract", () => {
  it("requires trusted session scope instead of accepting scope self-reported in a reply", () => {
    expect(researchBinding(researchRow, binding.userId)).toBeNull();
    expect(
      researchBinding(researchRow, binding.userId, { id: "TEST", version: 0 }),
    ).toBeNull();
    expect(() => parseResearchCollection(collection, binding.userId)).toThrow();
    const { accountScope: _scope, ...unscoped } = collection;
    expect(() =>
      parseResearchCollection(
        unscoped,
        binding.userId,
        Date.now(),
        binding.accountScope,
      ),
    ).toThrow();
    const { accountScope: _bindingScope, ...unscopedBinding } = binding;
    expect(() =>
      parseResearchTimeline(
        { ...timeline, binding: unscopedBinding },
        unscopedBinding as ResearchBinding,
      ),
    ).toThrow();
    expect(() =>
      parseSimilarResearch(
        { ...similar, binding: unscopedBinding },
        unscopedBinding as ResearchBinding,
        "request",
      ),
    ).toThrow();
  });
  const snapshots = [
    [
      "collection",
      (stamp: { generatedAt: string; expiresAt: string }, now: number) =>
        parseResearchCollection(
          { ...collection, ...stamp },
          binding.userId,
          now,
          binding.accountScope,
        ),
    ],
    [
      "timeline",
      (stamp: { generatedAt: string; expiresAt: string }, now: number) =>
        parseResearchTimeline({ ...timeline, ...stamp }, binding, now),
    ],
    [
      "similar",
      (stamp: { generatedAt: string; expiresAt: string }, now: number) =>
        parseSimilarResearch({ ...similar, ...stamp }, binding, "request", now),
    ],
  ] as const;
  it.each(snapshots)(
    "rejects reversed/equal/future %s snapshot timestamps, allowing bounded clock skew",
    (_name, parse) => {
      const now = Date.parse("2026-09-09T12:00:00Z");
      const expiresAt = new Date(now + 3_600_000).toISOString();
      expect(() => parse({ generatedAt: expiresAt, expiresAt }, now)).toThrow(
        "时间不一致",
      );
      expect(() =>
        parse(
          { generatedAt: new Date(now + 3_600_001).toISOString(), expiresAt },
          now,
        ),
      ).toThrow("时间不一致");
      expect(() =>
        parse(
          { generatedAt: new Date(now + 300_001).toISOString(), expiresAt },
          now,
        ),
      ).toThrow("时间不一致");
      expect(() =>
        parse(
          { generatedAt: new Date(now + 300_000).toISOString(), expiresAt },
          now,
        ),
      ).not.toThrow();
    },
  );
  it("keeps classification independent of workflow and stage", () => {
    const result = parseResearchCollection(
      collection,
      binding.userId,
      Date.now(),
      binding.accountScope,
    );
    expect(result.records[0].classification.category).toBe("OPPORTUNITY");
    expect(result.records[0].opportunity.intentStatus).toBe("READY");
  });
  it.each([
    "user",
    "source",
    "version",
    "sample",
    "duplicate",
    "quote",
    "empty evidence",
    "recognition",
    "expired",
  ])("rejects invalid collection: %s", (kind) => {
    const raw = structuredClone(collection);
    if (kind === "user") raw.userId = "other";
    if (kind === "source")
      raw.records[0].classification.evidence[0].sourceUrl += "/other";
    if (kind === "version")
      raw.records[0].classification.evidence[0].evidenceVersion = "v1";
    if (kind === "sample") raw.records[0].opportunity.sample = true;
    if (kind === "duplicate") raw.records.push(raw.records[0]);
    if (kind === "quote")
      raw.records[0].classification.evidence[0].quote = "不存在的明确采购";
    if (kind === "empty evidence") raw.records[0].classification.evidence = [];
    if (kind === "recognition")
      raw.records[0].classification.review.reviewer = "";
    if (kind === "expired") raw.expiresAt = "2020-01-01T00:00:00Z";
    expect(() =>
      parseResearchCollection(
        raw,
        binding.userId,
        Date.now(),
        binding.accountScope,
      ),
    ).toThrow();
  });
  it("accepts same-source version changes and distinguishes manual events", () => {
    const result = parseResearchTimeline(timeline, binding);
    expect(result.versions[1].access).toBe("FAILED");
    expect(result.contacts[0].kind).toBe("MANUAL");
  });
  it.each([
    "other project",
    "broken chain",
    "latest version",
    "invented difference",
    "receipt",
    "contact target",
  ])("rejects invalid timeline: %s", (kind) => {
    const raw = structuredClone(timeline);
    if (kind === "other project") raw.versions[0].sourceUrl += "/same-name";
    if (kind === "broken chain") raw.versions[1].previousVersionId = "missing";
    if (kind === "latest version") raw.binding.evidenceVersion = "v3";
    if (kind === "invented difference") raw.changes[0].to.quote = "已经关闭";
    if (kind === "receipt") raw.contacts[0].kind = "CHANNEL";
    if (kind === "contact target") raw.contacts[0].opportunityId = "other";
    expect(() => parseResearchTimeline(raw, binding)).toThrow();
  });
  it("allows unknown metering without converting it to zero", () => {
    const value = parseSimilarResearch(similar, binding, "request");
    expect(value.usage).toEqual({ status: "UNKNOWN", reason: "TEST 未接计量" });
  });
  it.each(["request", "recognition", "profile", "platform", "price"])(
    "rejects invalid similar preview: %s",
    (kind) => {
      const raw = structuredClone(similar);
      if (kind === "request") raw.requestId = "other";
      if (kind === "recognition") raw.recognition = null;
      if (kind === "profile") raw.binding.profileVersionId = "other";
      if (kind === "platform") raw.supportedPlatforms.push("web");
      if (kind === "price")
        (raw as unknown as Record<string, unknown>).usage = {
          status: "ESTIMATED",
          amount: -1,
          unit: "搜贝",
          basis: "TEST",
          measuredAt: collection.generatedAt,
        };
      expect(() => parseSimilarResearch(raw, binding, "request")).toThrow();
    },
  );
  it("never creates a research binding for samples or missing evidence", () => {
    expect(
      researchBinding({ ...researchRow, sample: true }, binding.userId),
    ).toBeNull();
    expect(
      researchBinding(
        { ...researchRow, sourceEvidenceVersion: undefined },
        binding.userId,
      ),
    ).toBeNull();
  });
  it("binds the same user's workspace and revision exactly", () => {
    const raw = { ...collection, accountScope: { id: "space-a", version: 1 } };
    expect(() =>
      parseResearchCollection(raw, binding.userId, Date.now(), {
        id: "space-a",
        version: 2,
      }),
    ).toThrow();
    expect(() =>
      parseResearchCollection(raw, binding.userId, Date.now(), {
        id: "space-b",
        version: 1,
      }),
    ).toThrow();
    expect(
      parseResearchCollection(raw, binding.userId, Date.now(), raw.accountScope)
        .accountScope,
    ).toEqual(raw.accountScope);
    expect(() =>
      parseResearchTimeline(
        {
          ...timeline,
          binding: { ...binding, accountScope: raw.accountScope },
        },
        { ...binding, accountScope: { id: "space-b", version: 1 } },
      ),
    ).toThrow();
  });
});
