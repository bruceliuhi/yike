import { describe, expect, it } from "vitest";
import { createVisualService } from "./service";
import { configureStrategyVisual } from "./strategy";
import { strategyPrepareRequest, parseStrategyReceipt, parseStrategyView } from "../../src/renderer/domain/researchStrategies";

describe("isolated strategy preview fixture", () => {
  it("returns strictly bound receipts without enabling execution", async () => {
    const harness = createVisualService();
    const draft = configureStrategyVisual(harness.service);
    const api = harness.service.researchStrategies!;
    const request = strategyPrepareRequest(draft, crypto.randomUUID(), { max_records: 37, max_runtime_seconds: 913 });
    const prepared = parseStrategyReceipt(await api.prepare(request), request);
    const confirm = { schema_version: "strategy-confirmation-v1" as const, request_id: crypto.randomUUID(),
      strategy_version_id: prepared.strategy_version_id, configuration_sha256: prepared.configuration_sha256, human_confirmed: true as const };
    parseStrategyReceipt(await api.confirm(confirm), confirm, prepared);
    expect(parseStrategyView(await api.getStrategy(prepared.strategy_version_id), prepared).state).toBe("CONFIRMED");
    await expect(harness.service.startTask(draft, "TEST-start")).rejects.toThrow();
    await expect(api.getReceipt(crypto.randomUUID())).rejects.toMatchObject({ status: 404, code: "request_not_found" });
  });
});
