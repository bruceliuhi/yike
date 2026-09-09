import { describe, expect, it } from "vitest";
import {
  decodeLibraryFacts,
  deadlineText,
  explicitInstant,
  libraryFactsFor,
  matchesLibraryFilters,
  compareDeadlines,
} from "../../src/renderer/domain/opportunityLibrary";
import type { Opportunity } from "../../src/renderer/domain/models";

const sourceUrl = "https://example.test/evidence/1";
export const factPayload = () => ({
  schema_version: 1,
  opportunity_id: "TEST-opportunity",
  source_url: sourceUrl,
  observed_at: "2026-09-09T09:00:00+08:00",
  evidence_version: "TEST-evidence-v3",
  stage: {
    status: "KNOWN",
    label: "预算询价",
    evidence_excerpt: "本次为预算编制阶段询价。",
  },
  materials_deadline: {
    status: "KNOWN",
    at: "2026-09-15T18:00:00+08:00",
    evidence_excerpt: "资料递交截止为 9月15日18:00（北京时间）。",
  },
});
export function factRow(payload = factPayload()): Opportunity {
  return {
    id: "TEST-opportunity",
    url: sourceUrl,
    sourceObservedAt: "2026-09-09T09:00:00+08:00",
    sourceEvidenceVersion: "TEST-evidence-v3",
    libraryFacts: decodeLibraryFacts(payload),
  } as Opportunity;
}
describe("P10 source-bound library facts", () => {
  it("separates an absent optional field from malformed or unbound facts", () => {
    expect(
      libraryFactsFor({ ...factRow(), libraryFacts: undefined }).status,
    ).toBe("missing");
    expect(
      decodeLibraryFacts({ ...factPayload(), schema_version: 5 }),
    ).toBeNull();
    expect(libraryFactsFor({ ...factRow(), libraryFacts: null }).status).toBe(
      "invalid",
    );
    expect(libraryFactsFor(factRow()).status).toBe("ready");
  });
  it.each([
    ["id", "OTHER"],
    ["url", "https://example.test/evidence/2"],
    ["sourceObservedAt", "2026-09-09T10:00:00+08:00"],
    ["sourceEvidenceVersion", "TEST-old"],
    ["sourceObservedAt", undefined],
    ["sourceEvidenceVersion", undefined],
  ])("rejects a mismatched current %s anchor", (key, value) => {
    expect(libraryFactsFor({ ...factRow(), [key]: value }).status).toBe(
      "invalid",
    );
  });
  it.each([
    "2026-02-30T18:00:00+08:00",
    "2026-09-15",
    "2026-09-15T18:00:00",
    "2026-09-15T24:00:00+08:00",
    "2026-09-15T18:60:00+08:00",
    "2026-09-15T18:00:00+15:00",
    "2026-09-15T18:00:00-00:00",
  ])("refuses ambiguous or invalid timestamp %s", (at) => {
    expect(explicitInstant(at)).toBe(false);
    expect(
      decodeLibraryFacts({
        ...factPayload(),
        materials_deadline: { ...factPayload().materials_deadline, at },
      }),
    ).toBeNull();
  });
  it("supports leap dates, midnight and an exact offset without local-time reinterpretation", () => {
    expect(explicitInstant("2024-02-29T00:00:00Z")).toBe(true);
    expect(explicitInstant("2026-09-16T00:00:00+08:00")).toBe(true);
    expect(deadlineText("2026-09-16T00:00:00+08:00")).toEqual({
      short: "09-16 00:00",
      full: "2026-09-16 00:00 UTC+08:00",
      zone: "2026 · UTC+08:00",
    });
    expect(deadlineText("2026-09-16T18:00:59.500+08:00").full).toBe(
      "2026-09-16 18:00:59.500 UTC+08:00",
    );
  });
  it("rejects unknown state enums and credentials in a source URL", () => {
    expect(
      decodeLibraryFacts({
        ...factPayload(),
        stage: { ...factPayload().stage, status: "MAGIC_READY" },
      }),
    ).toBeNull();
    expect(
      decodeLibraryFacts({
        ...factPayload(),
        source_url: "https://user:secret@example.test/",
      }),
    ).toBeNull();
  });
  it("does not derive business stage or deadline from followup, intent or prose", () => {
    const row = {
      ...factRow(),
      libraryFacts: undefined,
      intentStatus: "QUOTED",
      actionSignal: "2026-09-15 18:00截止",
    };
    expect(libraryFactsFor(row)).toEqual({ status: "missing" });
    expect(matchesLibraryFilters(row, "known:预算询价", "all", 0)).toBe(false);
  });
  it("keeps unknown, missing, invalid and explicitly unstated deadlines separate", () => {
    const missing = { ...factRow(), libraryFacts: undefined };
    const invalid = { ...factRow(), libraryFacts: null };
    const unknown = factRow();
    unknown.libraryFacts = decodeLibraryFacts({
      ...factPayload(),
      stage: { status: "UNKNOWN" },
      materials_deadline: { status: "UNKNOWN" },
    });
    const unstated = factRow();
    unstated.libraryFacts = decodeLibraryFacts({
      ...factPayload(),
      materials_deadline: {
        status: "NOT_STATED",
        evidence_excerpt: "本公告未列资料截止时间。",
      },
    });
    expect(matchesLibraryFilters(missing, "missing", "missing", 0)).toBe(true);
    expect(matchesLibraryFilters(invalid, "unverified", "unverified", 0)).toBe(
      true,
    );
    expect(matchesLibraryFilters(unknown, "unverified", "unverified", 0)).toBe(
      true,
    );
    expect(matchesLibraryFilters(unstated, "all", "unstated", 0)).toBe(true);
    expect(matchesLibraryFilters(missing, "all", "unstated", 0)).toBe(false);
  });
  it("uses exact instants across midnight and puts absent deadlines after known ones", () => {
    const row = factRow();
    const at = Date.parse(factPayload().materials_deadline.at);
    expect(
      matchesLibraryFilters(row, "known:预算询价", "upcoming", at - 1),
    ).toBe(true);
    expect(matchesLibraryFilters(row, "all", "upcoming", at)).toBe(false);
    expect(matchesLibraryFilters(row, "all", "overdue", at)).toBe(true);
    expect(matchesLibraryFilters(row, "all", "week", at - 7 * 86400000)).toBe(
      true,
    );
    expect(
      matchesLibraryFilters(row, "all", "week", at - 7 * 86400000 - 1),
    ).toBe(false);
    expect(
      compareDeadlines(row, { ...row, libraryFacts: undefined }),
    ).toBeLessThan(0);
    expect(
      compareDeadlines({ ...row, libraryFacts: undefined }, row),
    ).toBeGreaterThan(0);
  });
});
