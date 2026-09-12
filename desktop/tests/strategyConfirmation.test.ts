import { describe, expect, it } from "vitest";
import { createHash, randomUUID } from "node:crypto";
import { newTaskDraft } from "../src/renderer/domain/models";
import { strategyPrepareRequest } from "../src/renderer/domain/researchStrategies";
import type { StrategyReceipt, ConfirmStrategyRequest } from "../src/shared/researchStrategies";
import * as strategyConfirmation from "../src/renderer/domain/strategyConfirmation";
import { validatedOperation } from "../src/main/servicePolicy";

function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value !== null && typeof value === "object") return `{${Object.entries(value)
    .sort(([left], [right]) => left < right ? -1 : left > right ? 1 : 0)
    .map(([key, item]) => `${JSON.stringify(key)}:${canonical(item)}`).join(",")}}`;
  return JSON.stringify(value);
}

function digest(value: unknown): string {
  return createHash("sha256").update(canonical(value)).digest("hex");
}

async function implementation() {
  return strategyConfirmation;
}
function fixture() {
  const draft = newTaskDraft();
  draft.name = "不可写入操作账本的业务原文";
  draft.profileId = randomUUID();
  draft.terms = [{ id: "term", value: "输送机采购", origin: "manual", edited: true }];
  draft.platforms = ["web"];
  const request = strategyPrepareRequest(draft, randomUUID(), { max_records: 10, max_runtime_seconds: 600 });
  const strategy = randomUUID();
  const receipt: StrategyReceipt = {
    schema_version: "strategy-confirmation-v1", request_id: request.request_id, operation: "PREPARE",
    strategy_version_id: strategy, draft_id: request.draft_id, draft_revision: request.draft_revision,
    profile_version_id: request.profile_version_id, profile_sha256: "a".repeat(64), configuration_sha256: "b".repeat(64),
    snapshot: { strategy_version_id: strategy, profile_version_id: request.profile_version_id,
      configuration: request.configuration, platforms: request.platforms,
      max_records: request.max_records, max_runtime_seconds: request.max_runtime_seconds },
    state: "DRAFT", recorded_at: "2026-09-10T00:00:00Z",
  };
  return { request, receipt, context: { userId: randomUUID(), accountScopeId: null, scopeVersion: null, fingerprint: "c".repeat(64) } };
}

describe("strategy confirmation records and recovery", () => {
  it("recovers a legacy plain-link pending record without reopening it as a new action", async () => {
    const api = await implementation();
    const { request: current, receipt: currentReceipt, context } = fixture();
    const { publicSource: _publicSource, ...configuration } = current.configuration;
    const request = {
      ...current,
      configuration: { ...configuration, source: "links" as const, keywords: [], links: ["https://example.com/legacy"] },
      platforms: ["BILIBILI" as const],
    };
    const receipt = {
      ...currentReceipt,
      snapshot: { ...currentReceipt.snapshot, configuration: request.configuration, platforms: request.platforms },
    };
    const record = {
      version: 1 as const,
      draft_id: request.draft_id,
      context,
      prepare: { request_id: request.request_id, request_sha256: digest(request), state: "PENDING" as const },
      binding: null,
      confirm: null,
      revoke: null,
    };

    expect(await api.recoverStrategyReceipt(receipt, record)).toEqual(receipt);
    expect((await api.recordStrategyReceipt(record, receipt)).prepare.state).toBe("RECORDED");
    const changed = structuredClone(receipt);
    changed.snapshot.configuration.links = ["https://example.com/tampered"];
    await expect(api.recoverStrategyReceipt(changed, record)).rejects.toThrow();

    await expect(api.newStrategyRecord(request, context)).rejects.toThrow();
    await expect(api.strategyRetryRequest(record, request)).rejects.toThrow();
    expect(validatedOperation({ operation: "strategies.prepare", payload: request })).toBeNull();
  });

  it("hashes strict original requests independent of object key order, without normalizing values", async () => {
    const api = await implementation();
    const { request } = fixture();
    const digest = await api.strategyRequestDigest(request);
    expect(digest).toMatch(/^[a-f0-9]{64}$/);
    expect(await api.strategyRequestDigest(Object.fromEntries(Object.entries(request).reverse()))).toBe(digest);
    expect(await api.strategyRequestDigest({ ...request, max_records: 11 })).not.toBe(digest);
    await expect(api.strategyRequestDigest({ ...request, token: "private" })).rejects.toThrow();
  });

  it("saves only opaque binding and original request digests, never configuration text", async () => {
    const api = await implementation();
    const { request, context } = fixture();
    const record = await api.newStrategyRecord(request, context);
    expect(record.prepare.state).toBe("PENDING");
    expect(record.prepare.request_id).toBe(request.request_id);
    expect(record.prepare.request_sha256).toBe(await api.strategyRequestDigest(request));
    expect(JSON.stringify(record)).not.toContain(request.configuration.name);
    expect(api.validStrategyEntry(api.strategyRecordKey(record), JSON.stringify(record))).toBe(true);
    expect(api.validStrategyEntry(api.strategyRecordKey(record), JSON.stringify({ ...record, configuration: request.configuration }))).toBe(false);
  });

  it("recovers a lost draft only when its stored pre-call digest matches the actual receipt", async () => {
    const api = await implementation();
    const { request, context, receipt } = fixture();
    const record = await api.newStrategyRecord(request, context);
    expect(await api.recoverStrategyReceipt(receipt, record)).toEqual(receipt);
    const changed = structuredClone(receipt);
    changed.snapshot.configuration.keywords = ["另一类需求"];
    await expect(api.recoverStrategyReceipt(changed, record)).rejects.toThrow();
    await expect(api.recoverStrategyReceipt(receipt, { ...record, prepare: { ...record.prepare, request_sha256: "0".repeat(64) } })).rejects.toThrow();
    await expect(api.recoverStrategyReceipt(receipt, { ...record, prepare: { ...record.prepare, request_sha256: undefined } } as never)).rejects.toThrow();
  });

  it("cannot overwrite a pending confirmation; recovery uses the saved confirmation request and server binding", async () => {
    const api = await implementation();
    const { request, context, receipt } = fixture();
    const recorded = await api.recordStrategyReceipt(await api.newStrategyRecord(request, context), receipt);
    const confirm: ConfirmStrategyRequest = { schema_version: "strategy-confirmation-v1", request_id: randomUUID(),
      strategy_version_id: receipt.strategy_version_id, configuration_sha256: receipt.configuration_sha256, human_confirmed: true };
    const pending = await api.beginStrategyMutation(recorded, "CONFIRM", confirm);
    expect(pending.confirm!.state).toBe("PENDING");
    await expect(api.beginStrategyMutation(pending, "CONFIRM", { ...confirm, request_id: randomUUID() })).rejects.toThrow();
    const result = { ...receipt, request_id: confirm.request_id, operation: "CONFIRM", state: "CONFIRMED" };
    expect(await api.recoverStrategyReceipt(result, pending)).toEqual(result);
    await expect(api.recoverStrategyReceipt({ ...result, configuration_sha256: "d".repeat(64) }, pending)).rejects.toThrow();
    await expect(api.recoverStrategyReceipt({ ...result, profile_sha256: "d".repeat(64) }, pending)).rejects.toThrow();
    await expect(api.recoverStrategyReceipt({ ...result, request_id: randomUUID() }, pending)).rejects.toThrow();
    const settled = await api.recordStrategyReceipt(pending, result);
    expect(settled.confirm!.state).toBe("RECORDED");
    // A recorded operation is historical; no local "ready to execute" bit exists.
    expect(settled).not.toHaveProperty("authorized");
  });

  it("retries an unresolved operation only with exactly the original request", async () => {
    const api = await implementation();
    const { request, context } = fixture();
    const record = await api.newStrategyRecord(request, context);
    expect(await api.strategyRetryRequest(record, request)).toEqual(request);
    await expect(api.strategyRetryRequest(record, { ...request, request_id: randomUUID() })).rejects.toThrow();
    await expect(api.strategyRetryRequest(record, { ...request, max_records: 11 })).rejects.toThrow();
  });

  it("records revocation and never turns a revoked record into a new confirmation", async () => {
    const api = await implementation();
    const { request, context, receipt } = fixture();
    const recorded = await api.recordStrategyReceipt(await api.newStrategyRecord(request, context), receipt);
    const revoke = { schema_version: "strategy-confirmation-v1" as const, request_id: randomUUID(), strategy_version_id: receipt.strategy_version_id };
    const pending = await api.beginStrategyMutation(recorded, "REVOKE", revoke);
    const revoked = await api.recordStrategyReceipt(pending, { ...receipt, request_id: revoke.request_id, operation: "REVOKE", state: "REVOKED" });
    expect(revoked.revoke!.state).toBe("RECORDED");
    await expect(api.beginStrategyMutation(revoked, "CONFIRM", { schema_version: "strategy-confirmation-v1", request_id: randomUUID(),
      strategy_version_id: receipt.strategy_version_id, configuration_sha256: receipt.configuration_sha256, human_confirmed: true })).rejects.toThrow();
  });
});
