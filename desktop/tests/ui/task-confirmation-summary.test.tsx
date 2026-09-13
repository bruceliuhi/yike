// @vitest-environment jsdom
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  newTaskDraft,
  type PlatformConnection,
  type TaskDraft,
} from "../../src/renderer/domain/models";
import { TaskConfirmationSummary } from "../../src/renderer/pages/tasks/TaskConfirmationSummary";

afterEach(cleanup);

function draft(patch: Partial<TaskDraft> = {}): TaskDraft {
  return {
    ...newTaskDraft(),
    name: "TEST task",
    profileId: "TEST-profile",
    profileVersion: 1,
    platforms: ["xhs"],
    accounts: { xhs: "TEST-selected" },
    ...patch,
  };
}

function row(
  patch: Partial<PlatformConnection> = {},
): PlatformConnection {
  return {
    platform: "xhs",
    status: "CONNECTED",
    accountId: "TEST-selected",
    accountName: "Selected account",
    capabilities: ["search", "read"],
    ...patch,
  };
}

function renderSummary(
  connections: PlatformConnection[],
  value = draft(),
) {
  render(
    <TaskConfirmationSummary
      draft={value}
      connections={connections}
      deviceReady
      disabled={false}
      onEdit={vi.fn()}
    />,
  );
  return within(screen.getByRole("table"));
}

describe("task confirmation execution-account selection", () => {
  const connectionId = "11111111-1111-4111-8111-111111111111";
  const deviceId = "22222222-2222-4222-8222-222222222222";
  const accountId = "a".repeat(24);
  const boundAccount: PlatformConnection = row({
    accountId,
    accountName: "已登录的小红书账号",
    registration: { connectionId, deviceId, version: 2,
      connectedAt: "2026-09-13T00:00:00Z", disconnectedAt: null },
    foregroundBinding: { mode: "xhs-foreground-v1", platform: "XIAOHONGSHU",
      connectionId, deviceId, connectionVersion: 2, accountPublicId: accountId },
  });

  it("shows the selected registered account when its current foreground binding is valid", () => {
    const table = renderSummary([boundAccount], draft({ accounts: { xhs: accountId } }));
    expect(table.getByText("已登录的小红书账号")).toBeTruthy();
    expect(table.getByText("已连接")).toBeTruthy();
    expect(table.queryByText("所选账号（待核对）")).toBeNull();
  });

  it("does not present a stale foreground binding as a verified account", () => {
    const table = renderSummary([{ ...boundAccount,
      registration: { ...boundAccount.registration!, version: 3 },
    }], draft({ accounts: { xhs: accountId } }));
    expect(table.getByText("所选账号（待核对）")).toBeTruthy();
    expect(table.queryByText("已连接")).toBeNull();
  });

  it("shows the selected connected legacy account when a registration is first", () => {
    const table = renderSummary([
      row({
        accountId: "TEST-registered",
        accountName: "Registered account",
        capabilities: [],
        registration: {
          connectionId: "TEST-connection",
          deviceId: "TEST-device",
          version: 1,
          connectedAt: "2026-09-10T00:00:00Z",
          disconnectedAt: null,
        },
      }),
      row(),
    ]);

    expect(table.getByText("Selected account")).toBeTruthy();
    expect(table.getByText("已连接")).toBeTruthy();
    expect(table.queryByText("Registered account")).toBeNull();
    expect(table.queryByText("执行账号待核对")).toBeNull();
  });

  it.each(["EXPIRED", "DISCONNECTED"] as const)(
    "preserves the selected legacy account's %s status instead of using another connected account",
    (status) => {
      const table = renderSummary([
        row({ accountId: "TEST-other", accountName: "Other ready account" }),
        row({ status, accountName: "Selected unavailable account" }),
      ]);

      expect(table.getByText("Selected unavailable account")).toBeTruthy();
      expect(table.getByText(status === "EXPIRED" ? "登录已过期" : "未连接")).toBeTruthy();
      expect(table.queryByText("Other ready account")).toBeNull();
      expect(table.queryByText("已连接")).toBeNull();
    },
  );

  it("does not present a registration-only same-account row as execution-ready", () => {
    const table = renderSummary([
      row({
        accountName: "Registered only",
        capabilities: [],
        registration: {
          connectionId: "TEST-connection",
          deviceId: "TEST-device",
          version: 1,
          connectedAt: "2026-09-10T00:00:00Z",
          disconnectedAt: null,
        },
      }),
    ]);

    expect(table.getByText("所选账号（待核对）")).toBeTruthy();
    expect(table.queryByText(/TEST-selected/)).toBeNull();
    expect(table.getByText("待核验")).toBeTruthy();
    expect(table.queryByText("Registered only")).toBeNull();
    expect(table.queryByText("已连接")).toBeNull();
  });

  it("does not derive public-web readiness from a registration row", () => {
    const table = renderSummary(
      [
        row({
          platform: "web",
          accountId: "TEST-registered-web",
          accountName: "Registered web identity",
          capabilities: ["collect"],
          registration: {
            connectionId: "TEST-web-connection",
            deviceId: "TEST-device",
            version: 1,
            connectedAt: "2026-09-10T00:00:00Z",
            disconnectedAt: null,
          },
        }),
      ],
      draft({ platforms: ["web"], accounts: {} }),
    );

    expect(table.getByText("无需账号")).toBeTruthy();
    expect(table.getByText("范围待确认")).toBeTruthy();
    expect(table.queryByText("公开读取可用")).toBeNull();
  });
});
