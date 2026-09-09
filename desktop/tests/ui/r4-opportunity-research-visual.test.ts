import { describe, expect, it } from "vitest";
import { configureResearchVisual } from "../visual/r4-opportunity-research";
import { createVisualService } from "../visual/service";
import {
  parseResearchCollection,
  parseResearchTimeline,
  parseSimilarResearch,
  researchBinding,
} from "../../src/renderer/domain/opportunityResearch";

function scopedService() {
  const { service } = createVisualService();
  const session = service.session;
  service.session = async () => ({
    ...(await session()),
    accountScope: { id: "TEST-space", version: 1 },
  });
  return { service };
}
describe("R4 research isolated visual adapter", () => {
  it("does not invent a trusted session scope in its isolated adapter", async () => {
    const { service } = createVisualService();
    configureResearchVisual(service, "populated");
    await expect(service.opportunityResearch!.list()).rejects.toThrow(
      "可信账户空间",
    );
  });
  it("returns strict TEST classification and same-source timeline without touching send/start methods", async () => {
    const { service } = scopedService();
    const originalSend = service.send,
      originalStart = service.startTask;
    configureResearchVisual(service, "populated");
    const session = await service.session();
    const data = parseResearchCollection(
      await service.opportunityResearch!.list(),
      session.userId!,
      Date.now(),
      session.accountScope,
    );
    expect(data.records.map((r) => r.classification.category)).toEqual([
      "OPPORTUNITY",
      "OBSERVATION",
      "EXCLUDED",
    ]);
    const row = data.records[0].opportunity,
      binding = researchBinding(row, session.userId, session.accountScope)!;
    expect(new URL(row.url).hostname.endsWith(".invalid")).toBe(true);
    expect(
      parseResearchTimeline(
        await service.opportunityResearch!.timeline(binding),
        binding,
      ).changes,
    ).toHaveLength(1);
    expect(
      parseSimilarResearch(
        await service.opportunityResearch!.similar(binding, "TEST-request"),
        binding,
        "TEST-request",
      ).eligible,
    ).toBe(true);
    expect(service.send).toBe(originalSend);
    expect(service.startTask).toBe(originalStart);
    await expect(service.opportunity("sample")).rejects.toThrow();
  });
  it("rejects mismatched caller scope, source versions and missing object ids", async () => {
    const { service } = scopedService();
    configureResearchVisual(service, "populated");
    const session = await service.session();
    const row = (await service.opportunities())[0];
    const binding = researchBinding(row, session.userId, session.accountScope)!;
    await expect(
      service.opportunityResearch!.timeline({ ...binding, userId: "other" }),
    ).rejects.toThrow();
    await expect(
      service.opportunityResearch!.similar(
        { ...binding, evidenceVersion: "old" },
        "TEST-request",
      ),
    ).rejects.toThrow();
    await expect(service.opportunity("missing")).rejects.toThrow();
  });
  it("separates empty and error states and cancels a test loading wait", async () => {
    const { service } = scopedService();
    configureResearchVisual(service, "empty");
    expect((await service.opportunityResearch!.list()).records).toEqual([]);
    configureResearchVisual(service, "error");
    await expect(service.opportunityResearch!.list()).rejects.toThrow(
      "不是空结果",
    );
    configureResearchVisual(service, "loading");
    const controller = new AbortController();
    const pending = service.opportunityResearch!.list(controller.signal);
    controller.abort();
    await expect(pending).rejects.toThrow("TEST cancelled");
  });
});
