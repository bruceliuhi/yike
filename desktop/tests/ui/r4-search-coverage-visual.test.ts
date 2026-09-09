import { expect, it, vi } from "vitest";
import { configureCoverageVisual } from "../visual/r4-search-coverage";
import { configureBriefVisual } from "../visual/r4-opportunity-brief";
import { createVisualService } from "../visual/service";
import { monitor, profile, TEST_USER } from "../visual/fixtures";
import {
  parseCoverageSnapshot,
  type SearchCoverageQuery,
} from "../../src/renderer/domain/searchCoverage";
import {
  briefBusinessDay,
  parseOpportunityBrief,
  type BriefQuery,
} from "../../src/renderer/domain/opportunityBrief";

function setup(state: "populated" | "empty" | "error" = "populated") {
  const harness = createVisualService();
  harness.service.session = async () => ({
    authenticated: true,
    userId: TEST_USER,
    accountScope: { id: "TEST-scope", version: 1 },
  });
  configureCoverageVisual(harness.service, state);
  configureBriefVisual(harness.service, state);
  const coverage: SearchCoverageQuery = {
    contractVersion: 1,
    requestId: "TEST-query",
    taskId: monitor.id,
    profileId: profile.id,
    profileVersion: profile.version,
    expectedScope: {
      userId: TEST_USER,
      accountScopeId: "TEST-scope",
      scopeVersion: 1,
    },
  };
  const brief: BriefQuery = {
    contractVersion: 1,
    requestId: "TEST-query",
    profileId: profile.id,
    profileVersion: profile.version,
    userId: TEST_USER,
    accountScopeId: "TEST-scope",
    scopeVersion: 1,
    businessDate: briefBusinessDay(Date.now(), "Asia/Shanghai"),
    timezone: "Asia/Shanghai",
  };
  return { harness, coverage, brief };
}
it.each(["populated", "empty"] as const)(
  "provides bounded %s TEST snapshots using current verified scope and no external IO",
  async (state) => {
    const network = vi
      .spyOn(globalThis, "fetch")
      .mockRejectedValue(new Error("forbidden"));
    try {
      const { harness, coverage, brief } = setup(state);
      const a = parseCoverageSnapshot(
        await harness.service.searchCoverage!.query(coverage),
        coverage,
      );
      const b = parseOpportunityBrief(
        await harness.service.opportunityBrief!.query(brief),
        brief,
      );
      expect(a.accountScopeId).toBe("TEST-scope");
      expect(Date.parse(a.expiresAt)).toBeGreaterThan(Date.now());
      expect(b.accountScopeId).toBe("TEST-scope");
      expect(Date.parse(b.expiresAt)).toBeGreaterThan(Date.now());
      expect(network).not.toHaveBeenCalled();
      expect(
        harness.events.some((event) =>
          /send|startTask|taskAction|save|add/.test(event.operation),
        ),
      ).toBe(false);
    } finally {
      network.mockRestore();
    }
  },
);
it("retains error states and rejects different accounts or public samples before producing data", async () => {
  const { harness, coverage, brief } = setup("error");
  await expect(
    harness.service.searchCoverage!.query(coverage),
  ).rejects.toMatchObject({ code: "TEST_READ_FAILED" });
  await expect(
    harness.service.opportunityBrief!.query(brief),
  ).rejects.toMatchObject({ code: "TEST_READ_FAILED" });
  await expect(
    harness.service.searchCoverage!.query({ ...coverage, taskId: "sample" }),
  ).rejects.toMatchObject({ code: "FORBIDDEN" });
  await expect(
    harness.service.opportunityBrief!.query({
      ...brief,
      accountScopeId: "OTHER",
    }),
  ).rejects.toMatchObject({ code: "FORBIDDEN" });
  harness.service.session = async () => ({ authenticated: false });
  await expect(
    harness.service.searchCoverage!.query(coverage),
  ).rejects.toMatchObject({ code: "FORBIDDEN" });
});
