import { describe, expect, it } from "vitest";
import {
  coveragePlan,
  parseCoverageSnapshot,
} from "../../src/renderer/domain/searchCoverage";
import { coverageFixture, coverageQuery } from "./r4-search-coverage-fixtures";

describe("R4 immutable coverage window", () => {
  it("rejects future-generated data while preserving an expired window for labelled history", () => {
    const value = coverageFixture();
    const generated = Date.parse(value.generatedAt);
    expect(() =>
      parseCoverageSnapshot(value, coverageQuery, generated - 1),
    ).toThrow();
    expect(
      parseCoverageSnapshot(
        value,
        coverageQuery,
        Date.parse(value.expiresAt) + 1,
      ),
    ).toEqual(value);
  });
  it("keeps coverage and screening independent, preserves unknown values and uses no global sum", () => {
    const value = parseCoverageSnapshot(coverageFixture(), coverageQuery);
    expect(value.coverage).toBe("PARTIAL");
    expect(value.units[0].counts.independentSources).toBeNull();
    expect(value.units[2].screening).toBe("ALL_EXCLUDED");
    expect(value.units[3].counts.independentSources).toBe(0);
    expect(value).not.toHaveProperty("total");
  });
  it.each([
    "requestId",
    "taskId",
    "profileId",
    "userId",
    "accountScopeId",
  ] as const)("rejects a different %s", (field) => {
    expect(() =>
      parseCoverageSnapshot(
        { ...coverageFixture(), [field]: "OTHER" },
        coverageQuery,
      ),
    ).toThrow(/不一致/);
  });
  it.each(["profileVersion", "scopeVersion"] as const)(
    "rejects changed %s",
    (field) => {
      expect(() =>
        parseCoverageSnapshot(
          { ...coverageFixture(), [field]: 2 },
          coverageQuery,
        ),
      ).toThrow(/不一致/);
    },
  );
  it("rejects samples, duplicate units, unsupported versions, incomplete or invalid window metadata", () => {
    const value = coverageFixture();
    for (const row of [
      { ...value, audience: "SAMPLE" },
      { ...value, contractVersion: 2 },
      { ...value, runId: "sample:1" },
      { ...value, units: [...value.units, value.units[0]] },
      { ...value, window: { ...value.window, end: value.window.start } },
      { ...value, window: { ...value.window, timezone: "NOT_A_ZONE" } },
      { ...value, deduplicationVersion: "" },
    ])
      expect(() => parseCoverageSnapshot(row, coverageQuery)).toThrow();
  });
  it("does not accept completed/empty claims while a platform or human review remains unresolved", () => {
    for (const adjust of [
      (value: ReturnType<typeof coverageFixture>) => {
        value.coverage = "COMPLETE";
      },
      (value: ReturnType<typeof coverageFixture>) => {
        value.screening = "NO_QUALIFIED";
      },
      (value: ReturnType<typeof coverageFixture>) => {
        value.units[2].counts.pendingReviews = 1;
      },
      (value: ReturnType<typeof coverageFixture>) => {
        value.units[2].exclusions = [];
      },
      (value: ReturnType<typeof coverageFixture>) => {
        value.units[2].unchecked = ["尚未覆盖"];
      },
      (value: ReturnType<typeof coverageFixture>) => {
        value.units[2].stopReason = "ACCESS_FAILED";
      },
      (value: ReturnType<typeof coverageFixture>) => {
        value.units[0].unchecked = [];
      },
    ]) {
      const value = coverageFixture();
      adjust(value);
      expect(() => parseCoverageSnapshot(value, coverageQuery)).toThrow();
    }
  });
  it("requires bound exclusion evidence and refuses unsafe source URLs", () => {
    const value = coverageFixture();
    value.units[2].exclusions[0].evidence = [];
    expect(() => parseCoverageSnapshot(value, coverageQuery)).toThrow();
    const sample = coverageFixture();
    sample.units[2].exclusions[0].evidence[0].sourceId = "sample:public";
    expect(() => parseCoverageSnapshot(sample, coverageQuery)).toThrow(/样例/);
    value.units[0].evidence[0].url = "javascript:alert(1)";
    expect(() => parseCoverageSnapshot(value, coverageQuery)).toThrow();
  });
  it("quotes no prices and offers only typed plans for verified recoverability", () => {
    const value = coverageFixture();
    expect(coveragePlan(value, value.units[1])).toBeNull();
    value.usage = {
      unit: "SOUBEI",
      ruleVersion: "TEST-rule",
      budgetRevision: 2,
      maximum: 30,
      estimated: null,
      actual: null,
      settlement: "UNKNOWN",
    };
    expect(coveragePlan(value, value.units[1])).toMatchObject({
      kind: "ADJUST_LIMIT",
      runId: "TEST-run",
      windowId: "TEST-window",
      budgetRevision: 2,
    });
    value.units[1].recovery = "TERMINAL";
    expect(coveragePlan(value, value.units[1])?.kind).toBe("NEW_DRAFT");
    value.units[1].recovery = "UNKNOWN";
    expect(coveragePlan(value, value.units[1])).toBeNull();
  });
  it("rejects claims exceeding the authorized maximum and settled usage without actual units", () => {
    const value = coverageFixture();
    value.usage = {
      unit: "SOUBEI",
      ruleVersion: "TEST-rule",
      budgetRevision: 1,
      maximum: 10,
      estimated: null,
      actual: 11,
      settlement: "PENDING",
    };
    expect(() => parseCoverageSnapshot(value, coverageQuery)).toThrow(/搜贝/);
    value.usage.actual = null;
    value.usage.settlement = "SETTLED";
    expect(() => parseCoverageSnapshot(value, coverageQuery)).toThrow(/搜贝/);
  });
});
