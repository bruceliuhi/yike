// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { webcrypto } from "node:crypto";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { AppProvider } from "../../src/renderer/app/context";
import { SettingsPage } from "../../src/renderer/pages/Settings";
import { service as base } from "../../src/renderer/services/client";
import { downloadText } from "../../src/renderer/services/download";
import {
  readBackup,
  type AccountState,
  type ManagementInput,
  type ManagementReceipt,
} from "../../src/renderer/domain/management";
import type { ManagementService } from "../../src/renderer/services/management";
import { operationLedgerKey } from "../../src/renderer/app/operationLedger";

vi.mock("../../src/renderer/services/download", () => ({
  downloadText: vi.fn(),
  downloadErrorMessage: () => "文件保存失败",
}));
beforeEach(() => {
  vi.stubGlobal("crypto", webcrypto);
  localStorage.clear();
  vi.mocked(downloadText).mockReset().mockResolvedValue({ status: "saved" });
});
afterEach(() => {
  cleanup();
  localStorage.clear();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});
const account: AccountState = {
  userId: "management-test",
  accountScope: {id: "test-space", version: 1},
  spaceId: "test-space",
  spaceName: "TEST空间",
  revision: "r1",
  license: { status: "ACTIVE", expiresAt: "2030-01-01T00:00:00Z" },
  device: { id: "test-device", name: "TEST本机", status: "BOUND" },
};
function backup(spaceId = account.spaceId) {
  return JSON.stringify({
    product: "yike-ai",
    schemaVersion: 1,
    spaceId,
    createdAt: "2026-09-09T00:00:00Z",
    data: { profiles: [], tasks: [], opportunities: [], followups: [] },
  });
}
function mount(overrides: Partial<ManagementService> = {}) {
  let prepared: ManagementInput | undefined;
  const management: ManagementService = {
    account: vi.fn().mockResolvedValue(account),
    updates: vi.fn().mockResolvedValue({ available: false, download: "NONE" }),
    exportData: vi
      .fn()
      .mockResolvedValue({
        userId: account.userId,
        accountScope: account.accountScope,
        spaceId: account.spaceId,
        name: "customer-data",
        content: backup(),
      }),
    prepare: vi.fn(async (input, hash) => {
      prepared = input;
      return {
        id: "plan",
        kind: input.kind,
        spaceId: input.spaceId,
        revision: input.revision,
        inputHash: hash,
        expiresAt: new Date(Date.now() + 60000).toISOString(),
        summary: "TEST确认影响",
        changes: [{ label: "监控任务", added: 0, updated: 2, removed: 0 }],
      };
    }),
    execute: vi.fn(
      async (_id, requestId): Promise<ManagementReceipt> => ({
        requestId,
        kind: prepared!.kind,
        spaceId: account.spaceId,
        status: "SUCCEEDED",
      }),
    ),
    operation: vi.fn(),
    cancel: vi.fn(),
    ...overrides,
  };
  const service = {
    ...base,
    management,
    session: vi
      .fn()
      .mockResolvedValue({ authenticated: true, userId: "management-test", accountScope: account.accountScope }),
    info: vi
      .fn()
      .mockResolvedValue({
        version: "0.2.0",
        platform: "darwin",
        serviceConfigured: true,
      }),
  };
  const rendered = render(
    <AppProvider service={service}>
      <SettingsPage />
    </AppProvider>,
  );
  return { management, ...rendered };
}
async function devicePlan() {
  fireEvent.click(await screen.findByRole("button", { name: "解绑设备" }));
  fireEvent.click(screen.getByRole("button", { name: "检查影响并预览" }));
  await screen.findByText("TEST确认影响");
}
async function confirmDevice() {
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.click(
    within(screen.getByRole("dialog")).getByRole("button", {
      name: "解绑设备",
    }),
  );
}

describe("P18 available management contracts", () => {
  it("exports customer CSV while unverified commercial device stays explicitly unknown", async () => {
    mount({account:vi.fn().mockResolvedValue({...account,device:null}),
      exportData:vi.fn().mockResolvedValue({userId:account.userId,accountScope:account.accountScope,spaceId:account.spaceId,name:'意客AI-客户商机.csv',content:'商机标题\r\n测试商机\r\n'})});
    await screen.findByText('已激活');
    await screen.findByText('未取得商业设备绑定状态');
    fireEvent.click(screen.getByRole('button',{name:'导出数据'}));
    expect(screen.getByText(/仅导出当前账号可见的已纳入商机公开业务字段/)).toBeVisible();
    expect(screen.getByText(/完整证据请回到产品内查看/)).toBeVisible();
    fireEvent.click(await screen.findByRole('button',{name:'生成并保存 CSV'}));
    await waitFor(()=>expect(downloadText).toHaveBeenCalledWith({format:'csv',name:'意客AI-客户商机.csv',content:'商机标题\r\n测试商机\r\n'}));
  });
  it("does not treat unknown device status as permission to prepare a binding", async () => {
    const {management}=mount({account:vi.fn().mockResolvedValue({...account,device:null})});
    await screen.findByText('已激活');
    fireEvent.click(screen.getByRole('button',{name:'绑定设备'}));
    fireEvent.click(screen.getByRole('button',{name:'检查影响并预览'}));
    await screen.findByText('账号与数据管理服务尚未接通，当前没有执行更改。');
    expect(management.prepare).not.toHaveBeenCalled();
    expect(management.execute).not.toHaveBeenCalled();
  });
  it("keeps a timed-out management request locked until the original receipt is checked", async () => {
    const { management } = mount({execute: vi.fn(() => new Promise<ManagementReceipt>(() => {}))});
    await devicePlan();
    vi.useFakeTimers();
    await confirmDevice();
    await act(async () => { await vi.advanceTimersByTimeAsync(30_001); });
    expect(screen.getByText(/操作结果尚未确认，已保留原请求/)).toBeVisible();
    expect(management.execute).toHaveBeenCalledTimes(1);
    const pending = JSON.parse(localStorage.getItem(operationLedgerKey("management-operations", "management-test"))!);
    expect(Object.values(pending)).toEqual(["unbind-device"]);
    expect(within(screen.getByRole("dialog")).getByRole("button", {name: "解绑设备"})).toBeDisabled();
  });
  it("shows verified license and requires impact confirmation before unbinding", async () => {
    const { management } = mount();
    await screen.findByText("已激活");
    await devicePlan();
    expect(
      within(screen.getByRole("dialog")).getByRole("button", {
        name: "解绑设备",
      }),
    ).toBeDisabled();
    expect(management.execute).not.toHaveBeenCalled();
    await confirmDevice();
    await screen.findByText("解绑设备已完成。");
    expect(management.execute).toHaveBeenCalledTimes(1);
    expect(
      JSON.parse(
        localStorage.getItem(
          operationLedgerKey("management-operations", "management-test"),
        )!,
      ),
    ).toEqual({});
  });
  it("retains original request across closing and only unlocks matching authoritative receipt", async () => {
    const { management } = mount({
      execute: vi.fn().mockRejectedValue(new Error("connection lost")),
    });
    await devicePlan();
    await confirmDevice();
    await screen.findByText(/操作结果尚未确认，已保留原请求/);
    const id = Object.keys(
      JSON.parse(
        localStorage.getItem(
          operationLedgerKey("management-operations", "management-test"),
        )!,
      ),
    )[0];
    fireEvent.click(
      within(screen.getByRole("dialog")).getByRole("button", { name: "关闭" }),
    );
    vi.mocked(management.operation).mockResolvedValue({
      requestId: id,
      kind: "unbind-device",
      spaceId: "other-space",
      status: "SUCCEEDED",
    });
    fireEvent.click(screen.getByRole("button", { name: "核对原操作" }));
    await screen.findByText(/操作回执与当前客户空间或请求不匹配/);
    expect(
      localStorage.getItem(
        operationLedgerKey("management-operations", "management-test"),
      ),
    ).toContain(id);
    vi.mocked(management.operation).mockResolvedValue({
      requestId: id,
      kind: "unbind-device",
      spaceId: account.spaceId,
      status: "FAILED",
      message: "TEST未执行",
    });
    fireEvent.click(screen.getByRole("button", { name: "核对原操作" }));
    await screen.findByText("TEST未执行");
    expect(management.execute).toHaveBeenCalledTimes(1);
    expect(
      JSON.parse(
        localStorage.getItem(
          operationLedgerKey("management-operations", "management-test"),
        )!,
      ),
    ).toEqual({});
  });
  it("rejects stale or mismatched impact previews", async () => {
    const { management } = mount({
      prepare: vi
        .fn()
        .mockResolvedValue({
          id: "bad",
          kind: "unbind-device",
          spaceId: account.spaceId,
          revision: "old",
          inputHash: "a".repeat(64),
          expiresAt: "2000-01-01T00:00:00Z",
          summary: "unsafe",
          changes: [],
        }),
    });
    fireEvent.click(await screen.findByRole("button", { name: "解绑设备" }));
    fireEvent.click(screen.getByRole("button", { name: "检查影响并预览" }));
    await screen.findByText(/确认预览已失效或与当前操作不匹配/);
    expect(screen.queryByRole("checkbox")).toBeNull();
    expect(management.execute).not.toHaveBeenCalled();
  });
  it("does not dispatch when durable operation storage fails", async () => {
    const { management } = mount();
    await devicePlan();
    const original = Storage.prototype.setItem;
    const failure = vi
      .spyOn(Storage.prototype, "setItem")
      .mockImplementation(function (this: Storage, key, value) {
        if (key.includes("management-operations")) throw new Error("quota");
        original.call(this, key, value);
      });
    await confirmDevice();
    await screen.findByText(/操作确认记录暂时无法可靠保存/);
    expect(management.execute).not.toHaveBeenCalled();
    failure.mockRestore();
  });
  it("saves backups only after the real save receipt and handles cancellation", async () => {
    const { management } = mount();
    await screen.findByText("已激活");
    fireEvent.click(screen.getByRole("button", { name: "备份与恢复" }));
    vi.mocked(downloadText).mockResolvedValueOnce({ status: "cancelled" });
    fireEvent.click(screen.getByRole("button", { name: "保存客户数据备份" }));
    await waitFor(() => expect(downloadText).toHaveBeenCalledTimes(1));
    expect(screen.queryByText("客户数据备份已保存。")).toBeNull();
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "保存客户数据备份" }),
      ).not.toBeDisabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: "保存客户数据备份" }));
    await screen.findByText("客户数据备份已保存。");
    expect(management.execute).not.toHaveBeenCalled();
  });
  it("rejects a backup from another space before any file download", async () => {
    mount({
      exportData: vi
        .fn()
        .mockResolvedValue({
          userId: account.userId,
          accountScope: account.accountScope,
          spaceId: account.spaceId,
          name: "backup",
          content: backup("other-space"),
        }),
    });
    await screen.findByText("已激活");
    fireEvent.click(screen.getByRole("button", { name: "备份与恢复" }));
    fireEvent.click(screen.getByRole("button", { name: "保存客户数据备份" }));
    await screen.findByText("备份与当前客户空间不匹配。");
    expect(downloadText).not.toHaveBeenCalled();
  });
  it("previews the selected backup and binds its hash before restoring", async () => {
    const { management } = mount();
    await screen.findByText("已激活");
    fireEvent.click(screen.getByRole("button", { name: "备份与恢复" }));
    const content = backup();
    const file = new File([content], "TEST.yike-backup.json", {
      type: "application/json",
    });
    Object.defineProperty(file, "text", {
      value: () => Promise.resolve(content),
    });
    fireEvent.change(
      screen.getByLabelText("客户数据备份", { selector: "input" }),
      { target: { files: [file] } },
    );
    await screen.findByText("已选择：TEST.yike-backup.json");
    fireEvent.click(screen.getByRole("button", { name: "检查影响并预览" }));
    await screen.findByText("TEST确认影响");
    const [input, inputHash, passedContent] = vi.mocked(management.prepare).mock
      .calls[0];
    expect(input.kind).toBe("restore");
    expect(input.fileHash).toMatch(/^[a-f0-9]{64}$/);
    expect(inputHash).toMatch(/^[a-f0-9]{64}$/);
    expect(passedContent).toBe(content);
    expect(management.execute).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "恢复客户数据" }));
    await screen.findByText("恢复客户数据已完成。");
  });
  it("shows update download failure and the available rollback path", async () => {
    const { management } = mount({
      updates: vi
        .fn()
        .mockResolvedValue({
          available: true,
          version: "0.3.0",
          notes: "TEST release notes",
          download: "FAILED",
          rollbackVersion: "0.1.9",
        }),
    });
    await screen.findByText("已激活");
    fireEvent.click(screen.getByRole("button", { name: "检查更新" }));
    await screen.findByText("安装包下载失败，可重新检查后重试。");
    await screen.findByText("回退至上一版本");
    expect(management.execute).not.toHaveBeenCalled();
  });
});

it("backup parser rejects credentials, unknown versions and invalid JSON", () => {
  expect(readBackup(backup()).spaceId).toBe(account.spaceId);
  expect(() => readBackup("not json")).toThrow("无法读取此备份，请重新选择意客AI导出的备份文件。");
  expect(() =>
    readBackup(backup().replace('"schemaVersion":1', '"schemaVersion":2')),
  ).toThrow(/版本/);
  for (const key of [
    "access_token",
    "client_secret",
    "YIKE_PILOT_ADMIN_DATABASE_URL",
    "platform_session",
    "openai_api_key",
  ]) {
    const privateFile = JSON.parse(backup());
    privateFile.data.profiles.push({ [key]: "TEST-only" });
    expect(() => readBackup(JSON.stringify(privateFile))).toThrow(/凭据/);
  }
});
