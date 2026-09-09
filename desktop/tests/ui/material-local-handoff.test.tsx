// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import {
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
import type { Profile, ProfileFields } from "../../src/renderer/domain/models";
import type { MaterialService } from "../../src/renderer/services/materials";

function AuthenticatedProfile() {
  const { session } = useApp();
  return session.authenticated ? <ProfilePage /> : null;
}

afterEach(() => {
  cleanup();
  clearLocalDrafts();
  localStorage.clear();
  window.history.replaceState(null, "", "/");
});

it("保存首个画像后仍可编辑本机资料，并由人工带入当前画像后再同步", async () => {
  window.history.replaceState(null, "", "#/profile?tab=materials");
  const fields: ProfileFields = {
    service: "TEST 企业软件开发",
    customer: "TEST 企业采购",
    regions: "上海",
    preference: "",
    exclusions: "",
  };
  const saved: Profile = {
    id: "TEST-first-profile",
    version: 1,
    status: "DRAFT",
    description: "TEST 首个画像",
    fields,
  };
  const materials: MaterialService = {
    list: vi.fn().mockResolvedValue([]),
    mutate: vi.fn<MaterialService["mutate"]>(async (request) => {
      if (request.change.kind !== "save")
        throw new Error("TEST only accepts an explicit material save");
      return {
        requestId: request.requestId,
        profileVersionId: request.profileVersionId,
        materialId: request.change.materialId,
        kind: "save",
        status: "SUCCEEDED",
        record: {
          ...request.change.input,
          id: request.change.materialId,
          profileVersionId: request.profileVersionId,
          version: (request.change.expectedVersion ?? 0) + 1,
          status: "DRAFT",
          updatedAt: new Date().toISOString(),
        },
      };
    }),
    operation: vi.fn(),
    impact: vi.fn(),
  };
  const service = {
    ...baseService,
    session: vi.fn().mockResolvedValue({
      authenticated: true,
      userId: "TEST-local-material-user",
      accountScope: { id: "TEST-local-material-space", version: 1 },
    }),
    profiles: vi.fn().mockResolvedValue([]),
    saveProfile: vi.fn().mockResolvedValue(saved),
    materials,
  };
  render(
    <AppProvider service={service}>
      <AuthenticatedProfile />
    </AppProvider>,
  );

  fireEvent.click(await screen.findByRole("button", { name: "添加资料" }));
  let editor = screen.getByRole("dialog", { name: "添加资料" });
  fireEvent.change(within(editor).getByLabelText("资料名称"), {
    target: { value: "TEST 首次准备的案例" },
  });
  fireEvent.change(within(editor).getByLabelText("资料内容"), {
    target: { value: "TEST 仅用于内部判断的原始案例。" },
  });
  fireEvent.change(within(editor).getByLabelText("资料用途"), {
    target: { value: "真实案例" },
  });
  fireEvent.click(within(editor).getByRole("button", { name: "保存草稿" }));
  await screen.findByText("TEST 首次准备的案例");
  expect(materials.mutate).not.toHaveBeenCalled();

  fireEvent.click(screen.getByRole("tab", { name: "业务描述" }));
  for (const [label, value] of [
    ["服务内容", fields.service],
    ["目标客户", fields.customer],
    ["服务地区", fields.regions],
  ]) {
    fireEvent.change(
      await screen.findByLabelText(label, { selector: "input" }),
      {
        target: { value },
      },
    );
  }
  fireEvent.click(screen.getByRole("button", { name: "保存草稿" }));
  await screen.findByText("画像草稿已保存。");
  expect(service.saveProfile).toHaveBeenCalledWith(fields);
  fireEvent.click(screen.getByRole("tab", { name: "资料与案例" }));
  await waitFor(() => expect(materials.list).toHaveBeenCalledWith(saved.id));

  // The new customer workspace must not hide previously saved local materials.
  const localName = await screen.findByText("TEST 首次准备的案例");
  const localSection = localName.closest("details");
  if (localSection && !localSection.open)
    fireEvent.click(localSection.querySelector("summary")!);
  let localRow = localName.closest("tr");
  expect(localRow).not.toBeNull();
  expect(materials.mutate).not.toHaveBeenCalled();
  fireEvent.click(within(localRow!).getByRole("button", { name: "编辑" }));
  editor = screen.getByRole("dialog", { name: "编辑资料" });
  expect(
    (within(editor).getByLabelText("资料内容") as HTMLTextAreaElement).value,
  ).toBe("TEST 仅用于内部判断的原始案例。");
  fireEvent.change(within(editor).getByLabelText("资料内容"), {
    target: { value: "TEST 人工补充后仍仅供内部判断。" },
  });
  fireEvent.click(within(editor).getByRole("button", { name: "保存草稿" }));
  expect(materials.mutate).not.toHaveBeenCalled();

  localRow = screen.getByText("TEST 首次准备的案例").closest("tr");
  fireEvent.click(
    within(localRow!).getByRole("button", { name: "带入当前画像" }),
  );
  editor = await screen.findByRole("dialog", { name: "添加资料" });
  expect(
    (within(editor).getByLabelText("资料内容") as HTMLTextAreaElement).value,
  ).toBe("TEST 人工补充后仍仅供内部判断。");
  expect(
    (within(editor).getByLabelText("资料用途") as HTMLSelectElement).value,
  ).toBe("真实案例");
  expect(materials.mutate).not.toHaveBeenCalled();
  fireEvent.click(within(editor).getByRole("button", { name: "取消" }));
  expect(materials.mutate).not.toHaveBeenCalled();
  localRow = screen.getByText("TEST 首次准备的案例").closest("tr");
  fireEvent.click(
    within(localRow!).getByRole("button", { name: "带入当前画像" }),
  );
  editor = await screen.findByRole("dialog", { name: "添加资料" });
  fireEvent.click(within(editor).getByRole("button", { name: "保存草稿" }));
  await waitFor(() => expect(materials.mutate).toHaveBeenCalledOnce());
  expect(vi.mocked(materials.mutate).mock.calls[0][0]).toMatchObject({
    profileVersionId: saved.id,
    change: {
      kind: "save",
      expectedVersion: null,
      input: {
        name: "TEST 首次准备的案例",
        text: "TEST 人工补充后仍仅供内部判断。",
        purpose: "真实案例",
        visibility: "internal",
      },
    },
  });

  await screen.findByText("资料草稿已同步，尚未解析确认。");
  const localEntry = screen
    .getAllByText("TEST 首次准备的案例")
    .map((name) => name.closest("tr"))
    .find(
      (row) =>
        row && within(row).queryByRole("button", { name: "带入当前画像" }),
    );
  expect(localEntry).toBeTruthy();
  fireEvent.click(
    within(localEntry!).getByRole("button", { name: "带入当前画像" }),
  );
  editor = await screen.findByRole("dialog", { name: "编辑资料" });
  expect(materials.mutate).toHaveBeenCalledTimes(1);
  fireEvent.click(within(editor).getByRole("button", { name: "保存草稿" }));
  await waitFor(() => expect(materials.mutate).toHaveBeenCalledTimes(2));
  const first = vi.mocked(materials.mutate).mock.calls[0][0];
  const second = vi.mocked(materials.mutate).mock.calls[1][0];
  expect(second.profileVersionId).toBe(saved.id);
  expect(second.change.materialId).toBe(first.change.materialId);
  expect(second.change.expectedVersion).toBe(1);
});
