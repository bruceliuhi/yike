import { expect, it } from "vitest";
import {
  briefBusinessDay,
  nextBriefDay,
  briefTarget,
  parseOpportunityBrief,
} from "../../src/renderer/domain/opportunityBrief";
import { briefFixture, briefQuery } from "./r4-opportunity-brief-fixtures";

it("binds one account/profile/day and does not sum repeated opportunities across groups", () => {
  const value = parseOpportunityBrief(briefFixture(), briefQuery);
  expect(value.groups.contact.items[0].opportunityId).toBe(
    value.groups.followup.items[0].opportunityId,
  );
  expect(value).not.toHaveProperty("newCustomers");
});
it("allows bounded clock skew but rejects future data and preserves expired history", () => {
  const value = briefFixture();
  const generated = Date.parse(value.generatedAt);
  expect(() =>
    parseOpportunityBrief(value, briefQuery, generated - 5001),
  ).toThrow();
  expect(parseOpportunityBrief(value, briefQuery, generated - 5000)).toEqual(value);
  expect(parseOpportunityBrief(value, briefQuery, generated - 545)).toEqual(value);
  expect(parseOpportunityBrief(value, briefQuery, generated + 120_000)).toEqual(
    value,
  );
});
it.each([
  "requestId",
  "userId",
  "accountScopeId",
  "profileId",
  "businessDate",
  "timezone",
] as const)("refuses changed %s", (field) => {
  const other =
    field === "businessDate"
      ? "2026-09-10"
      : field === "timezone"
        ? "UTC"
        : "OTHER";
  expect(() =>
    parseOpportunityBrief({ ...briefFixture(), [field]: other }, briefQuery),
  ).toThrow();
});
it.each(["profileVersion", "scopeVersion"] as const)(
  "refuses a changed %s",
  (field) => {
    expect(() =>
      parseOpportunityBrief({ ...briefFixture(), [field]: 2 }, briefQuery),
    ).toThrow();
  },
);
it("requires coherent coverage, group counts, known sources and excludes all sample IDs", () => {
  const bad = [
    (value: ReturnType<typeof briefFixture>) => {
      value.groups.contact.total = 2;
    },
    (value: ReturnType<typeof briefFixture>) => {
      value.groups.contact.items[0].opportunityId = "sample:public";
    },
    (value: ReturnType<typeof briefFixture>) => {
      value.groups.contact.items[0].profileVersion = 2;
    },
    (value: ReturnType<typeof briefFixture>) => {
      value.groups.contact.items[0].basis.kind = "MANUAL_FOLLOWUP";
    },
    (value: ReturnType<typeof briefFixture>) => {
      value.coverage = "NOT_CHECKED";
    },
    (value: ReturnType<typeof briefFixture>) => {
      value.lastCompletedCheckAt = null;
    },
    (value: ReturnType<typeof briefFixture>) => {
      value.uncheckedScope = ["未查方向"];
    },
  ];
  for (const change of bad) {
    const value = briefFixture();
    change(value);
    expect(() => parseOpportunityBrief(value, briefQuery)).toThrow();
  }
});
it("provides exact existing navigation, while unavailable objects cannot open another record", () => {
  const item = briefFixture().groups.contact.items[0];
  expect(briefTarget("contact", item)).toBe("/opportunities/TEST-opportunity");
  expect(briefTarget("followup", item)).toBe(
    "/followups?tab=todo&opportunity=TEST-opportunity",
  );
  expect(
    briefTarget("changes", { ...item, validity: "TARGET_MISSING" }),
  ).toBeNull();
});
it("computes the explicit business date in the requested zone, including near midnight", () => {
  const instant = Date.parse("2026-09-09T16:30:00Z");
  expect(briefBusinessDay(instant, "Asia/Shanghai")).toBe("2026-09-10");
  expect(briefBusinessDay(instant, "UTC")).toBe("2026-09-09");
  expect(
    new Date(
      nextBriefDay(Date.parse("2026-09-09T15:59:59Z"), "Asia/Shanghai"),
    ).toISOString(),
  ).toBe("2026-09-09T16:00:00.000Z");
  expect(
    nextBriefDay(Date.parse("2026-03-08T05:00:00Z"), "America/New_York") -
      Date.parse("2026-03-08T05:00:00Z"),
  ).toBe(23 * 60 * 60 * 1000);
});
