// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { service } from "../../src/renderer/services/client";
import type { YikeDesktopApi } from "../../src/shared/contracts";
import type { AppContextValue } from "../../src/renderer/app/context";
import { FollowupsPage } from "../../src/renderer/pages/Followups";
import { PUBLIC_SAMPLE } from "../../src/renderer/pages/Opportunities";
import { parseRoute } from "../../src/renderer/domain/routes";

let context: AppContextValue;
vi.mock("../../src/renderer/app/context", () => ({ useApp: () => context }));
const host = window as unknown as { yikeDesktop?: YikeDesktopApi };
function respond(data: unknown) {
  const requestApi = vi.fn().mockResolvedValue({ ok: true, status: 200, data });
  host.yikeDesktop = { requestApi } as unknown as YikeDesktopApi;
  return requestApi;
}
afterEach(() => { cleanup(); delete host.yikeDesktop; vi.unstubAllGlobals(); });

describe.each(["profiles", "opportunities", "followups"] as const)("%s response boundary", method => {
  it.each([undefined, null, {}, {items: null}, {items: {}}, {items: [null]}, {items: [[]]}, {items: [{}]}, {items: ["bad"]}])("rejects malformed customer lists: %j", async body => {
    respond(body);
    await expect(service[method]()).rejects.toMatchObject({ code: "INVALID_SERVICE_RESPONSE" });
  });
  it("accepts an explicitly empty list", async () => {
    respond({items: []});
    expect(await service[method]()).toEqual([]);
  });
});

it.each([null, {}, {followup_id: ""}, {followup_id: 4}, {followup_id: " bad"}, {followup_id: "bad\nreceipt"}])("does not acknowledge an invalid followup receipt: %j", async body => {
  const request = respond(body);
  await expect(service.addFollowup("TEST-opp", "CONTACTED", "TEST note")).rejects.toMatchObject({code: "INVALID_SERVICE_RESPONSE"});
  expect(request).toHaveBeenCalledTimes(1);
});

it("accepts a persisted followup ID without changing the submitted facts", async () => {
  const request = respond({followup_id: "81802f14-2b41-4b12-8b62-8dfb73ce03e4"});
  await expect(service.addFollowup("TEST-opp", "CONTACTED", "TEST note")).resolves.toBeUndefined();
  expect(request).toHaveBeenCalledExactlyOnceWith({operation: "followups.add", payload: {opportunity_id: "TEST-opp", status: "CONTACTED", note: "TEST note"}});
});

it("keeps the entered followup and prevents a second POST after an invalid successful HTTP receipt", async () => {
  const request = respond({});
  const opportunity = {...PUBLIC_SAMPLE, id: "TEST-opp", profileVersionId: "TEST-profile", sample: false, title: "TEST 真实入口商机"};
  context = {
    service: {...service, opportunities: vi.fn().mockResolvedValue([opportunity]), opportunity: vi.fn().mockResolvedValue(opportunity), followups: vi.fn().mockResolvedValue([])},
    session: {authenticated: true, userId: crypto.randomUUID()}, route: parseRoute("#/followups?add=1"),
    navigate: vi.fn(), notify: vi.fn(), refreshSession: vi.fn(),
  };
  render(<FollowupsPage />);
  await within(await screen.findByRole("dialog", {name: "添加跟进"})).findByRole("option", {name: opportunity.title});
  fireEvent.change(screen.getByRole("combobox", {name: "关联商机"}), {target: {value: opportunity.id}});
  fireEvent.click(screen.getByRole("radio", {name: "已联系"}));
  fireEvent.change(screen.getByRole("textbox", {name: "跟进备注"}), {target: {value: "TEST 不能丢失的人工记录"}});
  fireEvent.click(screen.getByRole("button", {name: "保存记录"}));
  await screen.findByText(/保存回执不完整/);
  expect((screen.getByRole("textbox", {name: "跟进备注"}) as HTMLTextAreaElement).value).toBe("TEST 不能丢失的人工记录");
  expect((screen.getByRole("button", {name: "保存记录"}) as HTMLButtonElement).disabled).toBe(true);
  expect(context.navigate).not.toHaveBeenCalled();
  expect(context.notify).not.toHaveBeenCalledWith("跟进事实已保存。", "success");
  fireEvent.click(screen.getByRole("button", {name: "保存记录"}));
  expect(request).toHaveBeenCalledTimes(1);
});

it("shows a read error and permits retry instead of claiming there are no followups", async () => {
  const request = respond({});
  context = {
    service: {...service, opportunities: vi.fn().mockResolvedValue([])},
    session: {authenticated: true, userId: crypto.randomUUID()}, route: parseRoute("#/followups?tab=all"),
    navigate: vi.fn(), notify: vi.fn(), refreshSession: vi.fn(),
  };
  render(<FollowupsPage />);
  await screen.findByText("数据读取未完成，请重试。当前不能确认列表为空。");
  request.mockResolvedValue({ok: true, status: 200, data: {items: []}});
  fireEvent.click(screen.getByRole("button", {name: "重试"}));
  await waitFor(() => expect(screen.queryByText("数据读取未完成，请重试。当前不能确认列表为空。")).toBeNull());
  expect(request).toHaveBeenCalledTimes(2);
});
