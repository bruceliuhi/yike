// @vitest-environment jsdom
import {afterEach, describe, expect, it, vi} from "vitest";
import {service} from "../../src/renderer/services/client";
import {decodeConnectionRegistry, mergeConnectionRead} from "../../src/renderer/services/connectionRegistry";
import {disconnectTarget} from "../../src/renderer/domain/connectionDisconnect";
import {startBlockers} from "../../src/renderer/domain/task";
import {newTaskDraft} from "../../src/renderer/domain/models";
import {validatedOperation} from "../../src/main/servicePolicy";
import type {YikeDesktopApi} from "../../src/shared/contracts";
const host = window as unknown as {yikeDesktop?: YikeDesktopApi};
const row = (patch: Record<string, unknown> = {}) => ({connection_id: "TEST-connection", device_id: "TEST-device", account_public_id: "TEST-account", platform: "XIAOHONGSHU", status: "CONNECTED", connection_version: 3, connected_at: "2026-09-09T00:00:00+00:00", disconnected_at: null, ...patch});
afterEach(() => { delete host.yikeDesktop; vi.unstubAllGlobals(); });
describe("authenticated connection registry transport", () => {
  it("uses a fixed GET with no caller-controlled path, identity or headers", () => {
    expect(validatedOperation({operation: "connections.list"})).toEqual({path: "/api/ui/connections", method: "GET", logout: false});
    for (const payload of [{tenant_id: "other"}, {connection_id: "other"}, {url: "/admin"}, {headers: {authorization: "test"}}, []])
      expect(validatedOperation({operation: "connections.list", payload})).toBeNull();
  });
  it("reads browser HTTP registrations and never derives capabilities from CONNECTED", async () => {
    const get = vi.fn().mockResolvedValue(new Response(JSON.stringify({items: [row({capabilities: ["search", "send"], session_ref: "TEST-private-ref"})]}), {headers: {"content-type": "application/json"}}));
    vi.stubGlobal("fetch", get);
    const result = await service.connections();
    expect(get).toHaveBeenCalledWith("/api/ui/connections", expect.objectContaining({method: "GET", body: undefined, credentials: "same-origin", redirect: "error"}));
    expect(result[0]).toMatchObject({platform: "xhs", status: "CONNECTED", capabilities: [], registration: {connectionId: "TEST-connection", deviceId: "TEST-device", version: 3}});
    expect(JSON.stringify(result)).not.toContain("TEST-private-ref");
  });
  it("uses the native fixed-operation bridge and preserves authentication failures", async () => {
    const api = vi.fn().mockResolvedValueOnce({ok: true, status: 200, data: {items: [row({status: "UNVERIFIED"})]}}).mockResolvedValue({ok: false, status: 401, error: "invalid_session"});
    host.yikeDesktop = {requestApi: api} as unknown as YikeDesktopApi;
    expect((await service.connections())[0].status).toBe("UNVERIFIED");
    expect(api).toHaveBeenCalledWith({operation: "connections.list", payload: undefined});
    await expect(service.connections()).rejects.toMatchObject({status: 401, code: "invalid_session"});
  });
  it("maps only explicit server platform identifiers and keeps distinct devices", () => {
    const rows = ["XIAOHONGSHU", "DOUYIN", "BILIBILI", "ZHIHU", "PUBLIC_WEB"].map((platform, i) => row({platform, connection_id: `TEST-${i}`}));
    rows.push(row({connection_id: "TEST-other-device", device_id: "TEST-device-two"}));
    const result = decodeConnectionRegistry({items: rows});
    expect(result.map(r => r.platform)).toEqual(["xhs", "douyin", "bilibili", "zhihu", "web", "xhs"]);
    expect(result[5].registration?.deviceId).toBe("TEST-device-two");
  });
  it.each([
    {}, {items: null}, {items: [row(), row()]}, {items: [row({connection_version: 0})]},
    {items: [row({connection_version: "3"})]}, {items: [row({connection_version: 3.5})]},
    {items: [row({status: "READY"})]}, {items: [row({platform: "xhs"})]},
    {items: [row({device_id: ""})]}, {items: [row({account_public_id: "TEST\naccount"})]},
    {items: [row({connected_at: "tomorrow"})]}, {items: [row({disconnected_at: ""})]},
  ])("rejects incomplete registry responses instead of reporting an empty account list (%#)", input => {
    expect(() => decodeConnectionRegistry(input)).toThrow(/连接列表响应不完整/);
  });
  it("accepts a truly empty list and never enables legacy task or disconnect operations", () => {
    expect(decodeConnectionRegistry({items: []})).toEqual([]);
    const [registered] = decodeConnectionRegistry({items: [row()]});
    expect(() => disconnectTarget(registered)).toThrow(/连接版本/);
    const draft = {...newTaskDraft(), platforms: ["xhs"] as const, accounts: {xhs: "TEST-account"}};
    expect(startBlockers({...draft, platforms: [...draft.platforms]}, [], [{...registered, capabilities: ["search", "read", "monitor"]}], true)).toContain("小红书 需连接并选择有效账号或确认读取范围。");
  });
  it("preserves other registrations during legacy checks and exact connection updates", () => {
    const registered = decodeConnectionRegistry({items: [row(), row({connection_id: "TEST-other", device_id: "TEST-device-two"})]});
    const legacy = {platform: "xhs" as const, status: "CONNECTED" as const, accountId: "TEST-account", capabilities: []};
    const mixed = mergeConnectionRead(registered, legacy);
    expect(mixed).toHaveLength(3);
    const changed = {...registered[0], status: "EXPIRED" as const};
    const merged = mergeConnectionRead(mixed, changed);
    expect(merged).toHaveLength(3);
    expect(merged.find(r => r.registration?.connectionId === "TEST-other")?.status).toBe("CONNECTED");
    expect(merged.filter(r => r.registration?.connectionId === "TEST-connection")).toEqual([changed]);
  });
});
