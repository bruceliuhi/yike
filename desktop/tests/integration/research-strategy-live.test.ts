import { afterEach, expect, it, vi } from "vitest";
import { randomUUID } from "node:crypto";
import { configuredService, createServiceClient } from "../../src/main/serviceClient";
import { service } from "../../src/renderer/services/client";
import { parseStrategyReceipt, parseStrategyView, strategyPrepareRequest } from "../../src/renderer/domain/researchStrategies";
import { newTaskDraft } from "../../src/renderer/domain/models";
import type { PrepareStrategyRequest, ConfirmStrategyRequest, RevokeStrategyRequest } from "../../src/shared/researchStrategies";

const base = process.env.YIKE_STRATEGY_LIVE_BASE;
afterEach(() => vi.unstubAllGlobals());

// Only the Python test provisions this isolated loopback server/PG fixture.
it.skipIf(!base)("actual renderer and fixed IPC consume real HTTP/PG strategy receipts", async () => {
  expect(process.versions.node.split(".")[0]).toBe("24");
  const token = process.env.YIKE_STRATEGY_LIVE_TOKEN!;
  const profileId = process.env.YIKE_STRATEGY_LIVE_PROFILE!;
  expect(Boolean(token && profileId)).toBe(true);
  expect(new URL(base!).hostname).toBe("127.0.0.1");
  const baseUrl = configuredService(base, { packaged: false, allowLoopbackHttp: true });
  expect(baseUrl).toBe(base);
  const actualFetch = globalThis.fetch;
  let cookie = "";
  const calls: string[] = [];
  const client = createServiceClient({
    baseUrl,
    clearSession: async () => { cookie = ""; },
    // Node has no Electron cookie jar: retain only this fixture's session cookie.
    fetch: async (url, options) => {
      expect(new URL(url).origin).toBe(base);
      calls.push(`${options.method} ${new URL(url).pathname}`);
      const headers = new Headers(options.headers);
      if (cookie) headers.set("Cookie", cookie);
      const response = await actualFetch(url, { ...options, headers });
      const session = response.headers.getSetCookie().find(value => value.startsWith("pilot_session="));
      if (session) cookie = session.split(";", 1)[0];
      expect(response.headers.get("cache-control")).toBe("no-store");
      return response;
    },
  });
  vi.stubGlobal("window", { yikeDesktop: { requestApi: client.request } });
  expect((await service.loginToken!(token)).authenticated).toBe(true);
  expect(cookie.startsWith("pilot_session=")).toBe(true);
  const strategies = service.researchStrategies!;
  expect(strategies).toBeDefined();
  const draft = newTaskDraft();
  Object.assign(draft, { name: "中文客户策略往返", profileId, platforms: ["web"],
    terms: [{ id: randomUUID(), value: "输送设备 采购", origin: "manual", edited: true }],
    exclusions: [{ id: randomUUID(), value: "招聘", origin: "manual", edited: true }] });
  const request = strategyPrepareRequest(draft, randomUUID(), { max_records: 10, max_runtime_seconds: 600 });
  expect(request.configuration.schedule).toHaveProperty("policyVersion", 1);
  const { policyVersion: _policy, ...legacySchedule } = request.configuration.schedule!;
  const legacy: PrepareStrategyRequest = { ...request, request_id: randomUUID(),
    configuration: { ...request.configuration, schedule: legacySchedule } };
  const oldPrepared = parseStrategyReceipt(await strategies.prepare(legacy), legacy);
  expect(oldPrepared.snapshot.configuration.schedule).not.toHaveProperty("policyVersion");
  const oldConfirm: ConfirmStrategyRequest = { schema_version: "strategy-confirmation-v1", request_id: randomUUID(),
    strategy_version_id: oldPrepared.strategy_version_id, configuration_sha256: oldPrepared.configuration_sha256,
    human_confirmed: true };
  const oldConfirmed = parseStrategyReceipt(await strategies.confirm(oldConfirm), oldConfirm, oldPrepared);
  // A changed policy cannot reuse the old draft revision or its confirmation.
  await expect(strategies.prepare(request)).rejects.toMatchObject({ status: 409 });
  request.request_id = randomUUID();
  request.draft_revision = 2;
  const prepared = parseStrategyReceipt(await strategies.prepare(request), request);
  expect(prepared.state).toBe("DRAFT");
  expect(prepared.snapshot.configuration.schedule).toEqual(draft.schedule);
  expect(prepared.configuration_sha256).not.toBe(oldPrepared.configuration_sha256);
  expect(parseStrategyReceipt(await strategies.getReceipt(legacy.request_id), legacy)).toEqual(oldPrepared);
  expect(parseStrategyReceipt(await strategies.getReceipt(oldConfirm.request_id), oldConfirm, oldPrepared)).toEqual(oldConfirmed);
  await expect(strategies.confirm({ ...oldConfirm, request_id: randomUUID() })).rejects.toMatchObject({ status: 409 });
  expect(parseStrategyView(await strategies.getStrategy(oldPrepared.strategy_version_id), oldPrepared).is_current).toBe(false);
  const beforeReplay = calls.length;
  expect(parseStrategyReceipt(await strategies.prepare(request), request)).toEqual(prepared);
  expect(calls).toHaveLength(beforeReplay + 1);
  const confirm: ConfirmStrategyRequest = {
    schema_version: "strategy-confirmation-v1", request_id: randomUUID(),
    strategy_version_id: prepared.strategy_version_id, configuration_sha256: prepared.configuration_sha256,
    human_confirmed: true,
  };
  const beforeConflict = calls.length;
  await expect(strategies.confirm({ ...confirm, configuration_sha256: "0".repeat(64) })).rejects.toMatchObject({ status: 409 });
  expect(calls).toHaveLength(beforeConflict + 1);
  expect(parseStrategyView(await strategies.getStrategy(prepared.strategy_version_id), prepared).state).toBe("DRAFT");
  const confirmed = parseStrategyReceipt(await strategies.confirm(confirm), confirm, prepared);
  expect(confirmed.state).toBe("CONFIRMED");
  expect(parseStrategyReceipt(await strategies.getReceipt(confirm.request_id), confirm, prepared)).toEqual(confirmed);
  expect(parseStrategyView(await strategies.getStrategy(prepared.strategy_version_id), prepared)).toMatchObject({
    state: "CONFIRMED", is_current: true, profile_current: true,
  });
  const revoke: RevokeStrategyRequest = { schema_version: "strategy-confirmation-v1", request_id: randomUUID(),
    strategy_version_id: prepared.strategy_version_id };
  expect(parseStrategyReceipt(await strategies.revoke(revoke), revoke, prepared).state).toBe("REVOKED");
  expect(parseStrategyView(await strategies.getStrategy(prepared.strategy_version_id), prepared).state).toBe("REVOKED");
  // Old success is historical, not a fresh execution authorization.
  expect(parseStrategyReceipt(await strategies.getReceipt(confirm.request_id), confirm, prepared)).toEqual(confirmed);
  await service.logout();
  expect(cookie).toBe("");
  await expect(strategies.getReceipt(confirm.request_id)).rejects.toMatchObject({ status: 401 });
}, 30_000);
