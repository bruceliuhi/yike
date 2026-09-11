// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { FollowupsPage } from "../../src/renderer/pages/Followups";
import { PUBLIC_SAMPLE } from "../../src/renderer/pages/Opportunities";
import { parseRoute } from "../../src/renderer/domain/routes";
import type { AppContextValue } from "../../src/renderer/app/context";
import {
  ServiceError,
  type YikeService,
} from "../../src/renderer/services/contracts";
let context: AppContextValue;
vi.mock("../../src/renderer/app/context", () => ({ useApp: () => context }));
beforeEach(() => {
  context = {
    service: {
      followups: vi.fn().mockResolvedValue([]),
      opportunities: vi.fn().mockResolvedValue([
        {
          ...PUBLIC_SAMPLE,
          id: "real-followup",
          sample: false,
          title: "真实接口测试商机",
        },
        PUBLIC_SAMPLE,
      ]),
      opportunity: vi
        .fn()
        .mockResolvedValue({
          ...PUBLIC_SAMPLE,
          id: "real-followup",
          sample: false,
          title: "真实接口测试商机",
        }),
      addFollowup: vi
        .fn()
        .mockRejectedValue(
          new ServiceError("NETWORK", "保存失败，输入已保留", 503),
        ),
    } as unknown as YikeService,
    session: { authenticated: true, userId: crypto.randomUUID() },
    route: parseRoute("#/followups?add=1"),
    navigate: vi.fn(),
    notify: vi.fn(),
    refreshSession: vi.fn(),
  };
});
afterEach(cleanup);
describe("manual followup facts", () => {
  it('keeps old manual history visible after structured service is connected',async()=>{
    context.route=parseRoute('#/followups?tab=all');
    context.service.followup={list:vi.fn().mockResolvedValue({records:[],members:[],legacyRecords:[{
      id:'legacy-id',opportunityId:'real-followup',title:'历史登记商机',status:'CONTACTED',note:'旧记录不能消失',
      createdAt:'2026-09-01T01:00:00.000Z',kind:'manual'}]}),replies:vi.fn().mockResolvedValue([]),mutate:vi.fn(),operation:vi.fn()};
    render(<FollowupsPage/>);
    await screen.findByText('历史登记商机');
    expect(screen.queryByRole('button',{name:'纠正记录'})).toBeNull();
    expect(context.service.followups).not.toHaveBeenCalled();
  });
  it("allows only customer opportunities and retains the note on save failure", async () => {
    render(<FollowupsPage />);
    await within(
      await screen.findByRole("dialog", { name: "添加跟进" }),
    ).findByRole("option", { name: "真实接口测试商机" });
    expect(
      screen.queryByRole("option", { name: PUBLIC_SAMPLE.title }),
    ).toBeNull();
    fireEvent.change(screen.getByRole("combobox", { name: "关联商机" }), {
      target: { value: "real-followup" },
    });
    fireEvent.click(screen.getByRole("radio", { name: "已联系" }));
    fireEvent.change(screen.getByRole("textbox", { name: "跟进备注" }), {
      target: { value: "今天通过电话确认了资料范围。" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存记录" }));
    await screen.findByText("保存失败，输入已保留");
    expect(
      (screen.getByRole("textbox", { name: "跟进备注" }) as HTMLTextAreaElement)
        .value,
    ).toBe("今天通过电话确认了资料范围。");
    expect(context.service.addFollowup).toHaveBeenCalledWith(
      "real-followup",
      "CONTACTED",
      "今天通过电话确认了资料范围。",
    );
    expect(context.navigate).not.toHaveBeenCalled();
  });
  it("closes the drawer only after a real service save succeeds", async () => {
    context.service.addFollowup = vi.fn().mockResolvedValue(undefined);
    render(<FollowupsPage />);
    await within(
      await screen.findByRole("dialog", { name: "添加跟进" }),
    ).findByRole("option", { name: "真实接口测试商机" });
    fireEvent.change(screen.getByRole("combobox", { name: "关联商机" }), {
      target: { value: "real-followup" },
    });
    fireEvent.click(screen.getByRole("radio", { name: "已回复" }));
    fireEvent.change(screen.getByRole("textbox", { name: "跟进备注" }), {
      target: { value: "人工登记实际回复。" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存记录" }));
    await waitFor(() =>
      expect(context.navigate).toHaveBeenCalledWith("/followups"),
    );
    expect(context.notify).toHaveBeenCalledWith("跟进事实已保存。", "success");
  });
  it("requires an authenticated customer before any write", async () => {
    context.session = { authenticated: false };
    render(<FollowupsPage />);
    await screen.findByRole("dialog", { name: "添加跟进" });
    expect(
      (screen.getByRole("button", { name: "保存记录" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    expect(context.service.addFollowup).not.toHaveBeenCalled();
  });
});
