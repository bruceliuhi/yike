// @vitest-environment jsdom
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { AppProvider } from "../../src/renderer/app/context";
import { FollowupsPage } from "../../src/renderer/pages/Followups";
import { PUBLIC_SAMPLE } from "../../src/renderer/pages/Opportunities";
import { service as base } from "../../src/renderer/services/client";
import { clearLocalDrafts } from "../../src/renderer/app/hooks";
beforeEach(() => {
  clearLocalDrafts();
  sessionStorage.clear();
  localStorage.clear();
  history.replaceState(null, "", "#/followups?add=1");
});
afterEach(() => {
  cleanup();
  clearLocalDrafts();
});
function mount() {
  const service = {
    ...base,
    followup: undefined,
    session: vi
      .fn()
      .mockResolvedValue({ authenticated: true, userId: crypto.randomUUID() }),
    opportunities: vi
      .fn()
      .mockResolvedValue([
        { ...PUBLIC_SAMPLE, id: "TEST-opp", sample: false, title: "TEST商机" },
      ]),
    followups: vi.fn().mockResolvedValue([]),
    addFollowup: vi.fn().mockResolvedValue(undefined),
  };
  render(
    <AppProvider service={service}>
      <FollowupsPage />
    </AppProvider>,
  );
  return service;
}
async function fill() {
  await screen.findByRole("option", { name: "TEST商机" });
  fireEvent.change(screen.getByRole("combobox", { name: "关联商机" }), {
    target: { value: "TEST-opp" },
  });
  fireEvent.click(screen.getByRole("radio", { name: "已联系" }));
  fireEvent.change(screen.getByRole("textbox", { name: "跟进备注" }), {
    target: { value: "TEST必须保留的内容" },
  });
}
it("returns to the list only after saving and does not ask to abandon the just-saved form", async () => {
  const service = mount();
  await fill();
  fireEvent.click(screen.getByRole("button", { name: "保存记录" }));
  await waitFor(() =>
    expect(screen.queryByRole("dialog", { name: "添加跟进" })).toBeNull(),
  );
  expect(location.hash).toBe("#/followups");
  expect(screen.queryByRole("dialog", { name: "离开当前页面？" })).toBeNull();
  expect(service.addFollowup).toHaveBeenCalledOnce();
});
it("explicit keep-and-close navigates via real hashchange and reopening restores the unsaved draft", async () => {
  const service = mount();
  await fill();
  fireEvent.click(screen.getByRole("button", { name: "取消" }));
  await screen.findByRole("dialog", { name: "保留未保存内容并关闭？" });
  fireEvent.click(screen.getByRole("button", { name: "保留并关闭" }));
  await waitFor(() =>
    expect(screen.queryByRole("dialog", { name: "添加跟进" })).toBeNull(),
  );
  expect(screen.queryByRole("dialog", { name: "离开当前页面？" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "添加跟进" }));
  await screen.findByDisplayValue("TEST必须保留的内容");
  expect(service.addFollowup).not.toHaveBeenCalled();
});
