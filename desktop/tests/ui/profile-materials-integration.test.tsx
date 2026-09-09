// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { AppProvider, useApp } from "../../src/renderer/app/context";
import { clearLocalDrafts } from "../../src/renderer/app/hooks";
import { ProfilePage } from "../../src/renderer/pages/Profile";
import { service as baseService } from "../../src/renderer/services/client";
import type { Profile } from "../../src/renderer/domain/models";
import type { Material } from "../../src/renderer/domain/materials";
import type { MaterialService } from "../../src/renderer/services/materials";
const profile: Profile = {
  id: "profile-entry-test",
  version: 1,
  status: "CONFIRMED",
  description: "TEST 画像",
  fields: {
    service: "原人工服务",
    customer: "企业采购",
    regions: "上海",
    preference: "保留人工偏好",
    exclusions: "保留排除项",
  },
};
const material: Material = {
  id: "entry-material",
  version: 1,
  profileVersionId: profile.id,
  name: "TEST 可用资料",
  text: "人工核实服务",
  purpose: "产品介绍",
  visibility: "internal",
  status: "READY",
  updatedAt: "2026-09-09T00:00:00Z",
  extraction: {
    id: "extract-test",
    materialVersion: 1,
    fields: { service: "人工核实服务" },
    evidence: [{ field: "service", quote: "人工核实服务" }],
  },
};
function ChangeTestSpace() {
  const {refreshSession} = useApp();
  return <button onClick={() => void refreshSession()}>TEST 切换空间</button>;
}
afterEach(() => {
  cleanup();
  clearLocalDrafts();
  localStorage.clear();
  window.history.replaceState(null, "", "/");
  vi.useRealTimers();
});
it("真实 ProfilePage 同用户换空间不显示旧人工稿，切回原空间保留其草稿", async () => {
  window.history.replaceState(null, "", "#/profile");
  const user = {authenticated: true, userId: "TEST-scoped-profile"};
  let activeSpace = "TEST-space-a", sessionReads = 0;
  const service = {
    ...baseService,
    session: vi.fn(async () => {
      activeSpace = ++sessionReads === 2 ? "TEST-space-b" : "TEST-space-a";
      return {...user, accountScope: {id: activeSpace, version: 1}};
    }),
    profiles: vi.fn(async () => [activeSpace === "TEST-space-a" ? profile : {...profile, fields: {...profile.fields, service: "TEST B 服务"}}]),
    saveProfile: vi.fn(),
    confirmProfile: vi.fn(),
  };
  render(<AppProvider service={service}><ChangeTestSpace /><ProfilePage /></AppProvider>);
  await waitFor(() => expect((screen.getByLabelText("服务内容", {selector: "input"}) as HTMLInputElement).value).toBe("原人工服务"));
  fireEvent.change(screen.getByLabelText("服务内容", {selector: "input"}), {target: {value: "TEST A 未保存人工稿"}});
  fireEvent.click(screen.getByRole("button", {name: "TEST 切换空间"}));
  await waitFor(() => expect((screen.getByLabelText("服务内容", {selector: "input"}) as HTMLInputElement).value).toBe("TEST B 服务"));
  fireEvent.click(screen.getByRole("button", {name: "TEST 切换空间"}));
  await waitFor(() => expect((screen.getByLabelText("服务内容", {selector: "input"}) as HTMLInputElement).value).toBe("TEST A 未保存人工稿"));
  expect(service.saveProfile).not.toHaveBeenCalled();
  expect(service.confirmProfile).not.toHaveBeenCalled();
});

it("真实 ProfilePage 入口选资料、确认填入和回业务描述，保持其余人工字段且不自动保存确认", async () => {
  window.history.replaceState(null, "", "#/profile?tab=materials");
  const materials: MaterialService = {
    list: vi.fn().mockResolvedValue([material]),
    mutate: vi.fn(),
    operation: vi.fn(),
    impact: vi.fn(),
  };
  const service = {
    ...baseService,
    session: vi
      .fn()
      .mockResolvedValue({ authenticated: true, userId: "entry-user" }),
    profiles: vi.fn().mockResolvedValue([profile]),
    saveProfile: vi.fn(),
    confirmProfile: vi.fn(),
    materials,
  };
  render(
    <AppProvider service={service}>
      <ProfilePage />
    </AppProvider>,
  );
  await screen.findByText("TEST 可用资料");
  expect(materials.list).toHaveBeenCalledWith(profile.id);
  fireEvent.click(screen.getByRole("button", { name: "用于画像" }));
  fireEvent.click(screen.getByLabelText("已核对当前画像，确认替换所选字段"));
  fireEvent.click(
    within(screen.getByRole("dialog")).getByRole("button", {
      name: "填入画像草稿",
    }),
  );
  await screen.findByText("所选提取内容已填入画像草稿，尚未保存或确认。");
  fireEvent.click(screen.getByRole("tab", { name: "业务描述" }));
  const leaving = await screen.findByRole("dialog", { name: "离开当前页面？" });
  fireEvent.click(within(leaving).getByRole("button", { name: "继续离开" }));
  await waitFor(() =>
    expect(
      (
        screen.getByLabelText("服务内容", {
          selector: "input",
        }) as HTMLInputElement
      ).value,
    ).toBe("人工核实服务"),
  );
  expect(
    (
      screen.getByLabelText("项目偏好", {
        selector: "textarea",
      }) as HTMLTextAreaElement
    ).value,
  ).toBe("保留人工偏好");
  expect(screen.getByText("未保存修改")).toBeTruthy();
  expect(service.saveProfile).not.toHaveBeenCalled();
  expect(service.confirmProfile).not.toHaveBeenCalled();
});
it("画像保存迟到回执不能恢复卸载后的客户草稿", async () => {
  let resolve!: (value: Profile) => void;
  const promise = new Promise<Profile>((done) => {
    resolve = done;
  });
  window.history.replaceState(null, "", "#/profile");
  const service = {
    ...baseService,
    session: vi
      .fn()
      .mockResolvedValue({ authenticated: true, userId: "entry-user" }),
    profiles: vi.fn().mockResolvedValue([profile]),
    saveProfile: vi.fn().mockReturnValue(promise),
  };
  const view = render(
    <AppProvider service={service}>
      <ProfilePage />
    </AppProvider>,
  );
  await screen.findByText("修改后需保存并重新确认；已有任务仍保留原画像版本。");
  fireEvent.change(screen.getByLabelText("服务地区", { selector: "input" }), {
    target: { value: "杭州" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存草稿" }));
  await waitFor(() => expect(service.saveProfile).toHaveBeenCalledOnce());
  view.unmount();
  clearLocalDrafts();
  await act(async () =>
    resolve({ ...profile, fields: { ...profile.fields, regions: "杭州" } }),
  );
  expect(
    sessionStorage.getItem("yike.ui.draft.v1.profile.entry-user"),
  ).toBeNull();
});
