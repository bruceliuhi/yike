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
import { service as baseService } from "../../src/renderer/services/client";
import { MaterialsWorkspace } from "../../src/renderer/pages/profile/MaterialsWorkspace";
import { localMaterialIdentity } from "../../src/renderer/pages/profile/localMaterialIdentity";
import type { LocalMaterialDraft } from "../../src/renderer/pages/profile/LocalMaterialDrafts";
import type { Material } from "../../src/renderer/domain/materials";
import type { Profile } from "../../src/renderer/domain/models";
import type { MaterialService } from "../../src/renderer/services/materials";

const userId = "TEST-transfer-user";
const firstScope = { id: "TEST-transfer-space", version: 1 };
const profile: Profile = {
  id: "TEST-transfer-profile",
  version: 1,
  status: "DRAFT",
  description: "TEST",
  fields: {
    service: "TEST 服务",
    customer: "TEST 客户",
    regions: "上海",
    preference: "",
    exclusions: "",
  },
};
const local: LocalMaterialDraft & { purpose: "真实案例" } = {
  id: "TEST-local-material",
  name: "TEST 本机资料",
  text: "TEST 本机草稿内容",
  purpose: "真实案例",
  visibility: "internal",
  updatedAt: "2026-09-10T00:00:00Z",
};

function Panel({ api }: { api: MaterialService }) {
  const { session, refreshSession } = useApp();
  if (!session.authenticated) return null;
  return (
    <>
      <button onClick={() => void refreshSession()}>TEST 切换空间</button>
      <p>
        {session.accountScope?.id}:{session.accountScope?.version}
      </p>
      <MaterialsWorkspace
        api={api}
        profile={profile}
        currentFields={profile.fields}
        onApply={vi.fn()}
        localDrafts={[local]}
        onEditLocal={vi.fn()}
        onRemoveLocal={vi.fn()}
      />
    </>
  );
}
function mount(rows: Material[] = [], nextScope = firstScope) {
  let sessionRead = 0;
  const api: MaterialService = {
    list: vi.fn().mockResolvedValue(rows),
    mutate: vi.fn(),
    operation: vi.fn(),
    impact: vi.fn(),
  };
  const service = {
    ...baseService,
    session: vi.fn(async () => ({
      authenticated: true,
      userId,
      accountScope: ++sessionRead === 1 ? firstScope : nextScope,
    })),
  };
  render(
    <AppProvider service={service}>
      <Panel api={api} />
    </AppProvider>,
  );
  return api;
}
async function transfer() {
  const button = await screen.findByRole("button", { name: "带入当前画像" });
  await waitFor(() =>
    expect((button as HTMLButtonElement).disabled).toBe(false),
  );
  fireEvent.click(button);
}
afterEach(() => {
  cleanup();
  clearLocalDrafts();
  localStorage.clear();
  vi.restoreAllMocks();
  window.history.replaceState(null, "", "/");
});

it("已存在的目标资料带入后取消，服务端内容和引用范围保持原样", async () => {
  const id = await localMaterialIdentity(
    { userId, accountScope: firstScope },
    profile.id,
    local.id,
  );
  const existing: Material = {
    ...local,
    id,
    profileVersionId: profile.id,
    version: 7,
    name: "TEST 服务端资料",
    text: "TEST 服务端独立修改内容",
    visibility: "external",
    status: "DRAFT",
  };
  const api = mount([existing]);
  await transfer();
  const editor = await screen.findByRole("dialog", { name: "编辑资料" });
  expect(
    (within(editor).getByLabelText("资料内容") as HTMLTextAreaElement).value,
  ).toBe(local.text);
  expect(
    within(editor).getByText(
      "已从本机草稿带入，保存后同步到当前画像；原本机草稿保留。",
    ),
  ).toBeTruthy();
  expect(api.mutate).not.toHaveBeenCalled();
  fireEvent.click(within(editor).getByRole("button", { name: "取消" }));
  expect(screen.queryByRole("dialog")).toBeNull();
  const remoteRow = screen.getByText(existing.name).closest("tr")!;
  fireEvent.click(within(remoteRow).getByRole("button", { name: "编辑" }));
  const original = screen.getByRole("dialog", { name: "编辑资料" });
  expect(
    (within(original).getByLabelText("资料内容") as HTMLTextAreaElement).value,
  ).toBe(existing.text);
  expect(
    (
      within(original).getByRole("radio", {
        name: /允许对外引用/,
      }) as HTMLInputElement
    ).checked,
  ).toBe(true);
  expect(api.mutate).not.toHaveBeenCalled();
});

it("已有目标正在解析时不能带入修改或自动创建另一份资料", async () => {
  const id = await localMaterialIdentity(
    { userId, accountScope: firstScope },
    profile.id,
    local.id,
  );
  const api = mount([
    {
      ...local,
      id,
      profileVersionId: profile.id,
      version: 3,
      status: "PARSING",
    },
  ]);
  await transfer();
  await screen.findByText("这份资料正在解析，请完成后再带入修改。");
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(api.mutate).not.toHaveBeenCalled();
});

it.each([
  { id: "TEST-other-space", version: 1 },
  { id: firstScope.id, version: 2 },
])(
  "同用户切换空间 $id v$version 时，旧 SHA 结果不能打开新空间编辑器",
  async (nextScope) => {
    const digest = crypto.subtle.digest.bind(crypto.subtle);
    let release!: () => void;
    let began!: () => void;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const started = new Promise<void>((resolve) => {
      began = resolve;
    });
    // Keep the real digest and its exact bytes, delaying only delivery.
    vi.spyOn(crypto.subtle, "digest").mockImplementationOnce(
      async (algorithm, data) => {
        const result = await digest(algorithm, data);
        began();
        await gate;
        return result;
      },
    );
    const api = mount([], nextScope);
    await transfer();
    await act(async () => {
      await started;
    });
    fireEvent.click(screen.getByRole("button", { name: "TEST 切换空间" }));
    await screen.findByText(`${nextScope.id}:${nextScope.version}`);
    await waitFor(() => expect(api.list).toHaveBeenCalledTimes(2));
    await act(async () => {
      release();
    });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(api.mutate).not.toHaveBeenCalled();
    expect(
      (
        screen.getByRole("button", {
          name: "带入当前画像",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(false);
  },
);
