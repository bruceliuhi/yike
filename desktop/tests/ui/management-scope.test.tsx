// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { webcrypto } from "node:crypto";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { AppProvider, useApp } from "../../src/renderer/app/context";
import {
  CustomerDataActions,
  ManagementAction,
} from "../../src/renderer/pages/settings/ManagementActions";
import { service as base } from "../../src/renderer/services/client";
import {
  unavailableManagement,
  type ManagementService,
} from "../../src/renderer/services/management";
import type { AccountState, ManagementExport } from "../../src/renderer/domain/management";
import { downloadText } from "../../src/renderer/services/download";

vi.mock("../../src/renderer/services/download", () => ({
  downloadText: vi.fn(),
  downloadErrorMessage: () => "文件保存失败",
}));
beforeEach(() => {
  vi.stubGlobal("crypto", webcrypto);
  localStorage.clear();
  vi.mocked(downloadText).mockReset();
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});
const account: AccountState = {
  userId: "TEST-scope",
  accountScope: {id: "TEST-space", version: 1},
  spaceId: "TEST-space",
  spaceName: "TEST空间",
  revision: "r1",
  license: { status: "INACTIVE", expiresAt: null },
  device: { id: "TEST-device", name: "TEST本机", status: "UNBOUND" },
};
const backup = JSON.stringify({
  product: "yike-ai",
  schemaVersion: 1,
  spaceId: account.spaceId,
  createdAt: "2026-09-09T00:00:00Z",
  data: { profiles: [], tasks: [], opportunities: [], followups: [] },
});
function SessionMarker() {
  const { session } = useApp();
  return <span>{session.authenticated ? "TEST已登录" : "TEST读取会话"}</span>;
}
function mount(overrides: Partial<ManagementService>, mode = "data") {
  const management = { ...unavailableManagement, ...overrides };
  const service = {
    ...base,
    management,
    session: vi
      .fn()
      .mockResolvedValue({ authenticated: true, userId: "TEST-scope", accountScope: account.accountScope }),
  };
  const tree = (value: AccountState) => (
    <AppProvider service={service}>
      <SessionMarker />
      {mode === "data" ? (
        <CustomerDataActions account={value} backup changed={() => {}} />
      ) : (
        <ManagementAction
          account={value}
          kind="restore"
          content={backup}
          changed={() => {}}
        />
      )}
    </AppProvider>
  );
  const rendered = render(tree(account));
  return {
    ...rendered,
    update: (value: AccountState) => rendered.rerender(tree(value)),
    management,
  };
}
it.each(["space", "revision"])(
  "does not save an old export after the %s changes",
  async (kind) => {
    let resolve!: (value: ManagementExport) => void;
    const exporting = vi.fn(
      () =>
        new Promise<ManagementExport>(
          (done) => {
            resolve = done;
          },
        ),
    );
    const view = mount({ exportData: exporting });
    await screen.findByText("TEST已登录");
    fireEvent.click(screen.getByRole("button", { name: "保存客户数据备份" }));
    await waitFor(() => expect(exporting).toHaveBeenCalledTimes(1));
    view.update({
      ...account,
      ...(kind === "space" ? { spaceId: "TEST-other" } : { revision: "r2" }),
    });
    await act(async () =>
      resolve({
        userId: account.userId,
        accountScope: account.accountScope,
        spaceId: account.spaceId,
        name: "TEST-backup",
        content: backup,
      }),
    );
    expect(downloadText).not.toHaveBeenCalled();
    expect(screen.queryByText("客户数据备份已保存。")).toBeNull();
  },
);
it("does not upload a restore preview after closing during hashing", async () => {
  let resolve!: (value: ArrayBuffer) => void;
  const hashing = vi.spyOn(webcrypto.subtle, "digest").mockImplementation(
    () =>
      new Promise<ArrayBuffer>((done) => {
        resolve = done;
      }),
  );
  const prepare = vi.fn();
  const view = mount({ prepare }, "restore");
  await screen.findByText("TEST已登录");
  fireEvent.click(screen.getByRole("button", { name: "检查影响并预览" }));
  await waitFor(() => expect(hashing).toHaveBeenCalledTimes(1));
  view.unmount();
  // Both file and input digest use the same primitive. Complete both awaits.
  await act(async () => resolve(new ArrayBuffer(32)));
  await act(async () => resolve(new ArrayBuffer(32)));
  expect(prepare).not.toHaveBeenCalled();
});
it("keeps file selection disabled while reading and releases it on completion", async () => {
  let resolve!: (value: string) => void;
  // Finish the real session initialization and its scope-reset effects before
  // selecting a file; seeing the session marker alone is not that boundary.
  await act(async () => {
    mount({});
  });
  await screen.findByText("TEST已登录");
  const file = new File([backup], "TEST.yike-backup.json", {
    type: "application/json",
  });
  Object.defineProperty(file, "text", {
    value: () =>
      new Promise<string>((done) => {
        resolve = done;
      }),
  });
  const input = screen.getByLabelText("客户数据备份", { selector: "input" });
  fireEvent.change(input, { target: { files: [file] } });
  expect(input).toBeDisabled();
  await act(async () => resolve(backup));
  // Resolving file.text() is not the UI completion signal: wait for validation
  // and the selected-file state to commit before checking the released input.
  expect(await screen.findByText("已选择：TEST.yike-backup.json")).toBeVisible();
  expect(input).not.toBeDisabled();
});
