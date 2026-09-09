import { readFileSync } from "node:fs";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  digest,
  inputDigest,
  readBackup,
  type ManagementInput,
} from "../../src/renderer/domain/management";
import {
  configureManagementRecovery,
  selectManagementRecovery,
} from "./managementRecovery";
import { makeVisualManagement } from "./management";
import { createVisualService } from "./service";

const backup = readFileSync(
  new URL("./TEST-management.yike-backup.json", import.meta.url),
  "utf8",
);
function setup() {
  const harness = createVisualService();
  const controller = configureManagementRecovery(harness);
  return { harness, controller, api: harness.service.management! };
}
async function plan(
  api: ReturnType<typeof setup>["api"],
  kind: ManagementInput["kind"] = "restore",
) {
  const account = await api.account();
  const input: ManagementInput = {
    kind,
    spaceId: account.spaceId,
    revision: account.revision,
    deviceId: account.device.id,
  };
  if (kind === "restore") input.fileHash = await digest(backup);
  if (kind === "download-update") input.targetVersion = "0.2.1-TEST";
  return api.prepare(
    input,
    await inputDigest(input),
    kind === "restore" ? backup : undefined,
  );
}
afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe("finite TEST management lifecycle", () => {
  it("requires an explicit matching route/state/TEST identity; defaults retain unavailable writes", async () => {
    expect(selectManagementRecovery(null, "P18", "populated", false)).toBe(
      false,
    );
    expect(
      selectManagementRecovery("lifecycle", "P18", "populated", false),
    ).toBe(true);
    for (const args of [
      ["all", "P18", "populated", false],
      ["lifecycle", "P04", "populated", false],
      ["lifecycle", "P18", "error", false],
      ["lifecycle", "P18", "populated", true],
    ] as const)
      expect(() =>
        selectManagementRecovery(args[0], args[1], args[2], args[3]),
      ).toThrow(/TEST/);
    await expect(
      makeVisualManagement("populated").exportData("csv"),
    ).rejects.toMatchObject({ status: 501 });
  });
  it("validates scope, device, revision and digest before creating a plan", async () => {
    const { api } = setup();
    const account = await api.account();
    const valid: ManagementInput = {
      kind: "bind-device",
      spaceId: account.spaceId,
      revision: account.revision,
      deviceId: account.device.id,
    };
    for (const change of [
      { spaceId: "other" },
      { revision: "old" },
      { deviceId: "other" },
    ]) {
      const input = { ...valid, ...change };
      await expect(
        api.prepare(input, await inputDigest(input)),
      ).rejects.toThrow(/不匹配/);
    }
    await expect(api.prepare(valid, "0".repeat(64))).rejects.toThrow(/不匹配/);
  });
  it("validates backup bytes, account and TEST records rather than accepting arbitrary customer content", async () => {
    const { api } = setup();
    const a = await api.account();
    const base: ManagementInput = {
      kind: "restore",
      spaceId: a.spaceId,
      revision: a.revision,
      deviceId: a.device.id,
    };
    await expect(
      api.prepare(
        { ...base, fileHash: "0".repeat(64) },
        await inputDigest({ ...base, fileHash: "0".repeat(64) }),
        backup,
      ),
    ).rejects.toThrow(/摘要/);
    for (const content of [
      backup.replace("TEST-visual-space", "other-space"),
      backup.replace("TEST-restored-profile", "customer-real"),
      backup.replace('"name":', '"password":'),
    ]) {
      const input = { ...base, fileHash: await digest(content) };
      await expect(
        api.prepare(input, await inputDigest(input), content),
      ).rejects.toThrow();
    }
  });
  it("binds UNKNOWN to the original request and requires an explicit authoritative query to settle", async () => {
    const { api, controller, harness } = setup();
    const p = await plan(api);
    const p2 = await plan(api, "bind-device");
    const original = await api.execute(p.id, "TEST-request");
    expect(original.status).toBe("UNKNOWN");
    expect(await api.execute(p.id, "TEST-request")).toEqual(original);
    await expect(api.execute(p2.id, "TEST-request")).rejects.toThrow(
      /另一个计划/,
    );
    await expect(api.execute(p.id, "TEST-second")).rejects.toThrow(/不得另发/);
    expect((await api.operation("TEST-request")).status).toBe("UNKNOWN");
    controller.setQueryMode("FAILED");
    expect((await api.operation("TEST-request")).status).toBe("FAILED");
    controller.setQueryMode("SUCCEEDED");
    expect((await api.operation("TEST-request")).status).toBe("FAILED");
    expect(
      readBackup((await api.exportData("backup-json")).content).data.profiles[0]
        .id,
    ).toBe("TEST-backup-profile");
    expect(
      harness.events.filter((e) => e.operation === "management.TEST.execute"),
    ).toHaveLength(1);
  });
  it("applies a restore once to memory only when the TEST original receipt is confirmed successful", async () => {
    const { api, controller } = setup();
    const p = await plan(api);
    await api.execute(p.id, "TEST-restore");
    expect((await api.account()).revision).toBe("TEST-r1");
    controller.setQueryMode("SUCCEEDED");
    expect((await api.operation("TEST-restore")).status).toBe("SUCCEEDED");
    expect((await api.account()).revision).toBe("TEST-r2");
    await api.operation("TEST-restore");
    expect((await api.account()).revision).toBe("TEST-r2");
    expect(
      readBackup((await api.exportData("backup-json")).content).data.profiles[0]
        .id,
    ).toBe("TEST-restored-profile");
  });
  it("keeps cancellation pending until the original download receives a terminal cancellation", async () => {
    const { api, controller } = setup();
    const p = await plan(api, "download-update");
    await api.execute(p.id, "TEST-download");
    expect((await api.cancel("TEST-download")).status).toBe("PENDING");
    expect((await api.operation("TEST-download")).status).toBe("UNKNOWN");
    controller.setCancelMode("CANCELLED");
    expect((await api.cancel("TEST-download")).status).toBe("CANCELLED");
    controller.setQueryMode("SUCCEEDED");
    expect((await api.operation("TEST-download")).status).toBe("CANCELLED");
    expect((await api.updates()).download).toBe("NONE");
    const other = setup();
    const restore = await plan(other.api);
    await other.api.execute(restore.id, "TEST-restore");
    await expect(other.api.cancel("TEST-restore")).rejects.toThrow(/仅能取消/);
  });
  it("does not send stale plans, reveal another instance's requests or accept logged-out operations", async () => {
    const { api, harness } = setup();
    const p = await plan(api);
    vi.useFakeTimers();
    vi.setSystemTime(Date.parse(p.expiresAt) + 1);
    await expect(api.execute(p.id, "TEST-expired")).rejects.toThrow(/过期/);
    vi.useRealTimers();
    await expect(setup().api.operation("TEST-expired")).rejects.toThrow(
      /没有此原请求/,
    );
    await harness.service.logout();
    await expect(api.account()).rejects.toMatchObject({ code: "UNAUTHORIZED" });
    await expect(api.exportData("csv")).rejects.toMatchObject({
      code: "UNAUTHORIZED",
    });
  });
  it("only returns save receipts for issued matching TEST exports and never performs network IO", async () => {
    const network = vi
      .spyOn(globalThis, "fetch")
      .mockRejectedValue(new Error("unexpected network"));
    const { api, controller } = setup();
    const result = await api.exportData("csv");
    const input = {
      format: "csv" as const,
      name: result.name,
      content: result.content,
    };
    expect(await controller.saveExport(input)).toEqual({ status: "cancelled" });
    controller.setSaveMode("saved");
    expect(await controller.saveExport(input)).toEqual({ status: "saved" });
    controller.setSaveMode("error");
    expect(await controller.saveExport(input)).toEqual({
      status: "error",
      error: "EXPORT_FAILED",
    });
    expect(
      await controller.saveExport({ ...input, content: "customer" }),
    ).toEqual({ status: "error", error: "INVALID_EXPORT_REQUEST" });
    controller.setExecuteMode("SUCCEEDED");
    const p = await plan(api, "bind-device");
    await api.execute(p.id, "TEST-bind");
    expect(await controller.saveExport(input)).toEqual({
      status: "error",
      error: "INVALID_EXPORT_REQUEST",
    });
    expect(network).not.toHaveBeenCalled();
  });
});
