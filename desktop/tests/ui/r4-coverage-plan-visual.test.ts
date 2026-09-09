import { webcrypto } from "node:crypto";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { configureCoveragePlanVisual } from "../visual/r4-coverage-plan";
import { configureCoverageVisual } from "../visual/r4-search-coverage";
import { createVisualService } from "../visual/service";
import { monitor, profile, TEST_USER } from "../visual/fixtures";
import { coveragePlan } from "../../src/renderer/domain/searchCoverage";
import {
  coverageConfirmationHash,
  draftFromCoverage,
  readCoverageAdjustmentReceipt,
} from "../../src/renderer/domain/coveragePlan";
beforeEach(() => {
  vi.stubGlobal("crypto", webcrypto);
});
afterEach(() => {
  vi.unstubAllGlobals();
});
async function fixture(terminal = false) {
  const { service } = createVisualService();
  service.session = async () => ({
    authenticated: true,
    userId: TEST_USER,
    accountScope: { id: "TEST-account", version: 1 },
  });
  configureCoverageVisual(service, "populated");
  configureCoveragePlanVisual(service, "populated", { terminal });
  const snapshot = await service.searchCoverage!.query({
    contractVersion: 1,
    requestId: "TEST-query",
    taskId: monitor.id,
    profileId: profile.id,
    profileVersion: 1,
    expectedScope: {
      userId: TEST_USER,
      accountScopeId: "TEST-account",
      scopeVersion: 1,
    },
  });
  return { service, plan: coveragePlan(snapshot, snapshot.units[1])! };
}
it("keeps one adjustment UNKNOWN until the original request confirms notResumed", async () => {
  const { service, plan } = await fixture();
  const preview = await service.coveragePlans!.preview({
    requestId: "TEST-preview",
    plan,
    newMaxSoubei: 50,
  });
  const binding = {
    accountScopeId: plan.accountScopeId,
    scopeVersion: plan.scopeVersion,
    taskId: plan.taskId,
    requestId: "TEST-adjust",
    confirmationHash: await coverageConfirmationHash(preview),
  };
  expect(
    (await service.coveragePlans!.adjust({ binding, preview })).status,
  ).toBe("UNKNOWN");
  const receipt = await readCoverageAdjustmentReceipt(
    await service.coveragePlans!.reconcile(binding),
    binding,
  );
  expect(receipt.status).toBe("APPLIED");
  if (receipt.status !== "APPLIED") throw new Error();
  expect(receipt.notResumed).toBe(true);
  expect(receipt.maximum).toBe(50);
  expect(await service.coveragePlans!.reconcile(binding)).toEqual(receipt);
});
it("converts only the confirmed terminal TEST plan into a new local editable draft", async () => {
  const { service, plan } = await fixture(true);
  expect(plan.kind).toBe("NEW_DRAFT");
  const preview = await service.coveragePlans!.preview({
    requestId: "TEST-preview",
    plan,
  });
  if (preview.kind !== "NEW_DRAFT") throw new Error();
  const created = draftFromCoverage(preview);
  expect(created.id).not.toBe(preview.draft.id);
  expect(created.profileVersion).toBe(preview.draft.profileVersion);
  expect(created.platforms).toEqual(["douyin"]);
  expect(created.research?.maxSoubei).toBe(30);
});
