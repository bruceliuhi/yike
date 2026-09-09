// @vitest-environment jsdom
// @vitest-environment-options {"url":"http://127.0.0.1:18794/"}
import "@testing-library/jest-dom/vitest";
import { webcrypto } from "node:crypto";
import { readFileSync } from "node:fs";
import { afterEach, beforeAll, beforeEach, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { AppProvider } from "../../src/renderer/app/context";
import { clearLocalDrafts } from "../../src/renderer/app/hooks";
import { operationLedgerKey } from "../../src/renderer/app/operationLedger";
import { SettingsPage } from "../../src/renderer/pages/Settings";
import { createVisualService } from "./service";
import {
  configureManagementRecovery,
  type ManagementRecoveryController,
} from "./managementRecovery";
import { ManagementRecoveryControls } from "./ManagementRecoveryControls";
import { isolateBrowser } from "./isolation";
import { TEST_USER } from "./fixtures";

let active: ManagementRecoveryController;
const isolationEvents: string[] = [];
beforeAll(() => {
  vi.stubGlobal("crypto", webcrypto);
  isolateBrowser((operation) => isolationEvents.push(operation), {
    saveExport: (input) => active.saveExport(input),
  });
});
beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  clearLocalDrafts();
  isolationEvents.length = 0;
});
afterEach(() => cleanup());
function mount() {
  const harness = createVisualService();
  active = configureManagementRecovery(harness);
  render(
    <>
      <ManagementRecoveryControls controller={active} />
      <AppProvider service={harness.service}>
        <SettingsPage />
      </AppProvider>
    </>,
  );
  return harness;
}
const pending = () =>
  JSON.parse(
    localStorage.getItem(
      operationLedgerKey("management-operations", TEST_USER),
    ) || "{}",
  );
const backup = readFileSync(
  "tests/visual/TEST-management.yike-backup.json",
  "utf8",
);

it("uses the real download path with only a TEST save bridge, preserving cancelled/saved/error UI and all isolation guards", async () => {
  const h = mount();
  await screen.findByText("未激活");
  const bridge = (window as unknown as { yikeDesktop: Record<string, unknown> })
    .yikeDesktop;
  expect(Object.keys(bridge)).toEqual(["saveExport"]);
  expect(Object.isFrozen(bridge)).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "导出数据" }));
  const save = screen.getByRole("button", { name: "生成并保存 CSV" });
  fireEvent.click(save);
  await screen.findByText("TEST 模拟取消保存，未创建文件");
  expect(screen.queryByText("客户数据导出文件已保存。")).toBeNull();
  fireEvent.change(screen.getByLabelText("TEST 保存回执"), {
    target: { value: "saved" },
  });
  fireEvent.click(save);
  await screen.findByText("客户数据导出文件已保存。");
  expect(screen.getByText("TEST 模拟保存完成，未创建文件")).toBeVisible();
  fireEvent.change(screen.getByLabelText("TEST 保存回执"), {
    target: { value: "error" },
  });
  fireEvent.click(save);
  await screen.findByText("文件未能保存，请检查保存位置后重试。");
  await expect(window.fetch("https://external.invalid")).rejects.toThrow(
    /TEST/,
  );
  expect(() => new XMLHttpRequest().open("GET", "/api/ui/session")).toThrow(
    /TEST/,
  );
  expect(window.open("https://external.invalid")).toBeNull();
  expect(isolationEvents).toEqual([
    "BLOCKED_FETCH",
    "BLOCKED_XHR",
    "BLOCKED_WINDOW_OPEN",
  ]);
  expect(
    h.events.filter((e) => e.operation === "management.TEST.save"),
  ).toHaveLength(3);
});

it("restores through the real file/preview/confirmation UI then preserves UNKNOWN across closing and clearing drafts until original query", async () => {
  const h = mount();
  await screen.findByText("未激活");
  fireEvent.click(screen.getByRole("button", { name: "备份与恢复" }));
  const file = new File([backup], "TEST-management.yike-backup.json", {
    type: "application/json",
  });
  Object.defineProperty(file, "text", { value: async () => backup });
  fireEvent.change(
    screen.getByLabelText("客户数据备份", { selector: "input" }),
    { target: { files: [file] } },
  );
  await screen.findByText("已选择：TEST-management.yike-backup.json");
  fireEvent.click(screen.getByRole("button", { name: "检查影响并预览" }));
  await screen.findByText(
    "TEST 影响预览，仅修改隔离内存，不会恢复客户数据或安装软件。",
  );
  const submit = screen.getByRole("button", { name: "恢复客户数据" });
  expect(submit).toBeDisabled();
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.click(submit);
  await screen.findByText("操作结果待确认，请核对原操作后再继续。");
  const id = Object.keys(pending())[0];
  expect(id).toBeTruthy();
  expect(submit).toBeDisabled();
  fireEvent.click(
    within(screen.getByRole("dialog")).getByRole("button", { name: "关闭" }),
  );
  clearLocalDrafts();
  expect(Object.keys(pending())).toEqual([id]);
  fireEvent.click(screen.getByRole("button", { name: "核对原操作" }));
  await waitFor(() =>
    expect(
      h.events.filter((e) => e.operation === "management.TEST.query"),
    ).toHaveLength(1),
  );
  expect(Object.keys(pending())).toEqual([id]);
  fireEvent.change(screen.getByLabelText("TEST 原请求查询"), {
    target: { value: "SUCCEEDED" },
  });
  expect(Object.keys(pending())).toEqual([id]);
  fireEvent.click(screen.getByRole("button", { name: "核对原操作" }));
  await screen.findByText("恢复客户数据已完成。");
  await waitFor(() => expect(pending()).toEqual({}));
  expect(
    h.events.filter((e) => e.operation === "management.TEST.execute"),
  ).toHaveLength(1);
});

it("offers cancellation only for the original download and does not unlock on a pending cancellation receipt", async () => {
  const h = mount();
  await screen.findByText("未激活");
  fireEvent.click(screen.getByRole("button", { name: "检查更新" }));
  await screen.findByText("发现新版本 0.2.1-TEST");
  const preview = screen.getAllByRole("button", { name: "检查影响并预览" })[0];
  fireEvent.click(preview);
  await screen.findByText(
    "TEST 影响预览，仅修改隔离内存，不会恢复客户数据或安装软件。",
  );
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.click(screen.getByRole("button", { name: "下载安装包" }));
  await screen.findByText("操作结果待确认，请核对原操作后再继续。");
  const id = Object.keys(pending())[0];
  fireEvent.click(
    within(screen.getByRole("dialog")).getByRole("button", { name: "关闭" }),
  );
  fireEvent.click(screen.getByRole("button", { name: "取消下载" }));
  await waitFor(() =>
    expect(
      h.events.filter((e) => e.operation === "management.TEST.cancel"),
    ).toHaveLength(1),
  );
  expect(Object.keys(pending())).toEqual([id]);
  fireEvent.change(screen.getByLabelText("TEST 取消回执"), {
    target: { value: "CANCELLED" },
  });
  expect(Object.keys(pending())).toEqual([id]);
  fireEvent.click(screen.getByRole("button", { name: "取消下载" }));
  await screen.findByText("原操作已取消。");
  await waitFor(() => expect(pending()).toEqual({}));
  expect(
    h.events.filter((e) => e.operation === "management.TEST.execute"),
  ).toHaveLength(1);
});
