// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
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
import { ProfilePage } from "../../src/renderer/pages/Profile";
import { service as baseService } from "../../src/renderer/services/client";
import {
  ServiceError,
  type YikeService,
} from "../../src/renderer/services/contracts";
import type { Profile, ProfileFields } from "../../src/renderer/domain/models";

afterEach(() => {
  cleanup();
  clearLocalDrafts();
  window.history.replaceState(null, "", "/");
});
const fields: ProfileFields = {
  service: "真实填写的服务",
  customer: "企业采购",
  regions: "上海",
  preference: "第一行\n第二行",
  exclusions: "招聘",
};
function profile(status: Profile["status"] = "DRAFT"): Profile {
  return { id: "v-test", version: 1, status, fields, description: "测试画像" };
}
function mount(overrides: Partial<YikeService> = {}, path = "/profile") {
  window.history.replaceState(null, "", "#" + path);
  const service = {
    ...baseService,
    session: vi
      .fn()
      .mockResolvedValue({ authenticated: true, userId: "test-user" }),
    profiles: vi.fn().mockResolvedValue([]),
    saveProfile: vi.fn().mockResolvedValue(profile()),
    confirmProfile: vi.fn().mockResolvedValue(profile("CONFIRMED")),
    ...overrides,
  };
  render(
    <AppProvider service={service}>
      <ProfilePage />
    </AppProvider>,
  );
  return service;
}

describe("业务画像和资料", () => {
  it("编辑时收起重复摘要，展开仍显示最新内容且确认弹窗完整可见", async () => {
    mount({ profiles: vi.fn().mockResolvedValue([profile()]) });
    await waitFor(() => expect(screen.queryByText("正在加载…")).toBeNull());
    const summary = screen.getByText("查看画像摘要");
    const preview = summary.closest("details");
    expect(preview).not.toBeNull();
    expect(preview!.open).toBe(false);
    fireEvent.change(screen.getByLabelText("服务地区"), { target: { value: "杭州" } });
    fireEvent.click(summary);
    expect(preview!.open).toBe(true);
    expect(within(preview!).getByText("杭州")).toBeTruthy();
    fireEvent.click(summary);
    expect(preview!.open).toBe(false);
    expect((screen.getByLabelText("服务地区") as HTMLInputElement).value).toBe("杭州");
    fireEvent.click(screen.getByRole("button", { name: "确认画像" }));
    const dialog = await screen.findByRole("dialog", { name: "确认画像版本 1" });
    expect(within(dialog).getByText(fields.service).closest("details")).toBeNull();
    expect(within(dialog).getByRole("checkbox")).toBeTruthy();
    expect((within(dialog).getByRole("button", { name: "确认画像" }) as HTMLButtonElement).disabled).toBe(true);
  });
  it("拒绝损坏的本机资料恢复数据并保持可用空态", async () => {
    sessionStorage.setItem(
      "yike.ui.draft.v1.materials.corrupt-draft-user",
      JSON.stringify([{ id: "broken", name: { invalid: true } }]),
    );
    mount({session: vi.fn().mockResolvedValue({authenticated: true, userId: "corrupt-draft-user"})}, "/profile?tab=materials");
    await waitFor(() => expect(screen.queryByText("正在加载…")).toBeNull());
    expect(await screen.findByText("暂无资料")).toBeTruthy();
    await waitFor(() =>
      expect(
        sessionStorage.getItem("yike.ui.draft.v1.materials.corrupt-draft-user"),
      ).toBeNull(),
    );
    expect(screen.queryByText("broken")).toBeNull();
  });
  it("确认后返回历史状态时不显示画像确认成功", async () => {
    mount({
      profiles: vi.fn().mockResolvedValue([profile()]),
      confirmProfile: vi.fn().mockResolvedValue(profile("REVOKED")),
    });
    await waitFor(() => expect(screen.queryByText("正在加载…")).toBeNull());
    fireEvent.click(screen.getByRole("button", { name: "确认画像" }));
    const dialog = screen.getByRole("dialog", { name: "确认画像版本 1" });
    fireEvent.click(within(dialog).getByRole("checkbox"));
    fireEvent.click(within(dialog).getByRole("button", { name: "确认画像" }));
    await screen.findAllByText("画像状态已发生变化，请取消并刷新后核对。");
    expect(screen.queryByText("画像已确认，可继续配置获客任务。")).toBeNull();
  });
  it("空客户不填假数据；示例仍未确认且必填地区缺失不能保存", async () => {
    const service = mount();
    await waitFor(() => expect(screen.queryByText("正在加载…")).toBeNull());
    expect((screen.getByLabelText("服务内容") as HTMLInputElement).value).toBe(
      "",
    );
    fireEvent.click(screen.getByRole("button", { name: "使用填写示例" }));
    expect(screen.getByText("填写示例 · 未确认")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "保存草稿" }));
    expect(screen.getByText("请填写服务地区。")).toBeTruthy();
    expect(service.saveProfile).not.toHaveBeenCalled();
    expect(service.confirmProfile).not.toHaveBeenCalled();
  });
  it("保存失败保留全部字段；确认需核验并只调用画像确认", async () => {
    const save = vi
      .fn()
      .mockRejectedValueOnce(new ServiceError("NETWORK", "保存失败，输入保留"))
      .mockResolvedValue(profile());
    const service = mount({ saveProfile: save });
    await waitFor(() => expect(screen.queryByText("正在加载…")).toBeNull());
    for (const [label, value] of [
      ["服务内容", fields.service],
      ["目标客户", fields.customer],
      ["服务地区", fields.regions],
      ["项目偏好", fields.preference],
      ["排除项", fields.exclusions],
    ])
      fireEvent.change(
        screen.getByLabelText(label, { selector: "input,textarea" }),
        { target: { value } },
      );
    fireEvent.click(screen.getByRole("button", { name: "保存草稿" }));
    await screen.findByText("保存失败，输入保留");
    expect(
      (
        screen.getByLabelText("项目偏好", {
          selector: "textarea",
        }) as HTMLTextAreaElement
      ).value,
    ).toBe(fields.preference);
    fireEvent.click(screen.getByRole("button", { name: "确认画像" }));
    const dialog = await screen.findByRole("dialog", {
      name: "确认画像版本 1",
    });
    expect(
      (
        within(dialog).getByRole("button", {
          name: "确认画像",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
    fireEvent.click(within(dialog).getByRole("checkbox"));
    fireEvent.click(within(dialog).getByRole("button", { name: "确认画像" }));
    await waitFor(() =>
      expect(service.confirmProfile).toHaveBeenCalledWith("v-test"),
    );
    expect(save).toHaveBeenLastCalledWith(fields);
    expect(screen.queryByText("任务已启动")).toBeNull();
  });
  it("已有确认版本修改后保留旧版本语义", async () => {
    mount({ profiles: vi.fn().mockResolvedValue([profile("CONFIRMED")]) });
    await screen.findByText(
      "修改后需保存并重新确认；已有任务仍保留原画像版本。",
    );
    fireEvent.change(screen.getByLabelText("服务地区"), {
      target: { value: "杭州" },
    });
    expect(screen.getByText("未保存修改")).toBeTruthy();
    fireEvent.click(screen.getByRole("tab", { name: "资料与案例" }));
    expect(
      await screen.findByRole("dialog", { name: "离开当前页面？" }),
    ).toBeTruthy();
  });
  it("资料校验、取消保护、本机保存和删除确认均可操作", async () => {
    mount({}, "/profile?tab=materials");
    await screen.findByText("暂无资料");
    fireEvent.click(screen.getByRole("button", { name: "添加资料" }));
    const drawer = await screen.findByRole("dialog", { name: "添加资料" });
    fireEvent.click(within(drawer).getByRole("button", { name: "保存草稿" }));
    expect(within(drawer).getByText("请填写资料名称和内容。")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("资料名称"), {
      target: { value: "本机测试案例" },
    });
    fireEvent.change(screen.getByLabelText("资料内容"), {
      target: { value: "真实填写的案例内容" },
    });
    fireEvent.click(within(drawer).getByRole("button", { name: "取消" }));
    const discard = screen.getByRole("dialog", { name: "放弃未保存的资料？" });
    fireEvent.click(within(discard).getByRole("button", { name: "取消" }));
    fireEvent.click(within(drawer).getByRole("button", { name: "保存草稿" }));
    await screen.findByText("本机测试案例");
    expect(screen.getByText("本机草稿")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "删除" }));
    expect(
      screen.getByRole("dialog", { name: "删除本机资料草稿？" }),
    ).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "删除草稿" }));
    await screen.findByText("暂无资料");
  });
  it("拒绝不支持的上传，不伪报文件已上传", async () => {
    mount({}, "/profile?tab=materials");
    fireEvent.click(screen.getByRole("button", { name: "添加资料" }));
    fireEvent.click(screen.getByRole("tab", { name: "上传文件" }));
    fireEvent.change(screen.getByLabelText("上传资料文件"), {
      target: { files: [new File(["fake-binary"], "document.exe")] },
    });
    expect(
      screen.getByText("请选择不超过 200 KB 的 TXT 或 Markdown 文件。"),
    ).toBeTruthy();
    expect(screen.queryByText("上传成功")).toBeNull();
  });
});
