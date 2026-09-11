// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { clearLocalDrafts } from "../../src/renderer/app/hooks";
import { MaterialsWorkspace } from "../../src/renderer/pages/profile/MaterialsWorkspace";
import { MaterialEditor } from "../../src/renderer/pages/profile/MaterialEditor";
import { MaterialExtraction } from "../../src/renderer/pages/profile/MaterialExtraction";
import { legacyMaterialOperationKey } from "../../src/renderer/pages/profile/materialOperationStorage";
import { MemoryStorage } from "../visual/isolation";
import {
  parseMaterialReceipt,
  parseMaterials,
  type Material,
  type MaterialPending,
  type MaterialReceipt,
  type MaterialRequest,
} from "../../src/renderer/domain/materials";
import type { MaterialService } from "../../src/renderer/services/materials";
import type { Profile, ProfileFields, Session } from "../../src/renderer/domain/models";

const context = vi.hoisted(() => ({
  session: { authenticated: true, userId: "material-test-user" } as Session,
  notify: vi.fn(),
}));
vi.mock("../../src/renderer/app/context", () => ({ useApp: () => context }));
const fields: ProfileFields = {
  service: "人工服务",
  customer: "企业采购",
  regions: "上海",
  preference: "人工偏好",
  exclusions: "招聘",
};
const profile: Profile = {
  id: "profile-test",
  version: 1,
  status: "DRAFT",
  fields,
  description: "隔离测试画像",
};
function row(status: Material["status"] = "DRAFT", version = 1): Material {
  return {
    id: "material-test",
    profileVersionId: profile.id,
    version,
    name: "TEST 资料",
    text: "展台设计与搭建，服务企业采购。",
    purpose: "产品介绍",
    visibility: "external",
    status,
    updatedAt: "2026-09-09T00:00:00Z",
    ...(["READY", "REVIEW_REQUIRED"].includes(status)
      ? {
          extraction: {
            id: "extraction-test",
            materialVersion: version,
            fields: { service: "展台设计与搭建", customer: "企业采购" },
            evidence: [
              { field: "service" as const, quote: "展台设计与搭建" },
              { field: "customer" as const, quote: "企业采购" },
            ],
          },
        }
      : {}),
  };
}
function receipt(
  request: MaterialRequest,
  record?: Material,
  status: MaterialReceipt["status"] = "SUCCEEDED",
): MaterialReceipt {
  return {
    requestId: request.requestId,
    profileVersionId: request.profileVersionId,
    materialId: request.change.materialId,
    kind: request.change.kind,
    status,
    ...(record ? { record } : {}),
  };
}
function adapter(rows: Material[] = []): MaterialService {
  return {
    list: vi.fn().mockResolvedValue(rows),
    mutate: vi.fn(),
    operation: vi.fn(),
    impact: vi
      .fn()
      .mockImplementation(async (_profileId, materialId, version, action) => ({
        profileVersionId: profile.id,
        materialId,
        version,
        action,
        token: "impact-test",
        expiresAt: new Date(Date.now() + 60000).toISOString(),
        references: [{ kind: "draft", label: "TEST 待确认草稿" }],
      })),
  };
}
function mount(api: MaterialService, onApply = vi.fn()) {
  return {
    ...render(
      <MaterialsWorkspace
        api={api}
        profile={profile}
        currentFields={fields}
        onApply={onApply}
      />,
    ),
    onApply,
  };
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { resolve, promise };
}
async function add() {
  fireEvent.click(await screen.findByRole("button", { name: "添加资料" }));
  fireEvent.change(screen.getByLabelText("资料名称"), {
    target: { value: "TEST 新资料" },
  });
  fireEvent.change(screen.getByLabelText("资料内容"), {
    target: { value: "TEST 人工填写内容" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存草稿" }));
}
const locks = () =>
  Array.from({length: localStorage.length}, (_, index) => localStorage.key(index)!).filter((key) =>
    key?.startsWith("yike.ui.material-operation."),
  );
beforeEach(() => {
  context.session = { authenticated: true, userId: "material-test-user" };
  context.notify.mockClear();
  localStorage.clear();
});
afterEach(() => {
  cleanup();
  clearLocalDrafts();
  localStorage.clear();
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("P04 客户空间资料生命周期", () => {
  it("标准 MemoryStorage 下 UNKNOWN 重开只能核对原请求并可靠释放原锁", async () => {
    vi.stubGlobal("localStorage", new MemoryStorage());
    const api = adapter([row()]);
    vi.mocked(api.mutate).mockRejectedValue(new Error("TEST 结果未知"));
    const view = mount(api);
    fireEvent.click(await screen.findByRole("button", { name: "解析资料" }));
    await screen.findByText("TEST 结果未知");
    const submitted = vi.mocked(api.mutate).mock.calls[0][0];
    view.unmount();
    mount(api);
    await screen.findByText("TEST 资料");
    expect((screen.getByRole("button", { name: "解析资料" }) as HTMLButtonElement).disabled).toBe(true);
    vi.mocked(api.operation).mockResolvedValue(receipt(submitted, row("PARSING", 2)));
    fireEvent.click(screen.getByRole("button", { name: "核对原资料操作" }));
    await screen.findByText("解析中");
    expect(api.operation).toHaveBeenLastCalledWith(profile.id, submitted.requestId);
    expect(api.mutate).toHaveBeenCalledTimes(1);
    expect(locks()).toHaveLength(0);
  });

  it("同用户切换空间立即关闭旧的已确认移除影响弹窗", async () => {
    context.session.accountScope = { id: "TEST-space-a", version: 1 };
    const api = adapter([row("READY")]);
    const view = mount(api);
    fireEvent.click(await screen.findByRole("button", { name: "移除" }));
    await screen.findByLabelText("已核对引用影响");
    fireEvent.click(screen.getByLabelText("已核对引用影响"));
    expect((screen.getByRole("button", { name: "确认移除" }) as HTMLButtonElement).disabled).toBe(false);
    context.session = { ...context.session, accountScope: { id: "TEST-space-b", version: 1 } };
    view.rerender(<MaterialsWorkspace api={api} profile={profile} currentFields={fields} onApply={vi.fn()} />);
    expect(screen.queryByRole("dialog", { name: "移除资料？" })).toBeNull();
    expect(api.mutate).not.toHaveBeenCalled();
  });

  it("同用户切换空间后不提供旧空间原请求核对入口", async () => {
    context.session.accountScope = { id: "TEST-space-a", version: 1 };
    const api = adapter([row()]);
    vi.mocked(api.mutate).mockRejectedValue(new Error("TEST 结果未知"));
    const view = mount(api);
    fireEvent.click(await screen.findByRole("button", { name: "解析资料" }));
    await screen.findByText("TEST 结果未知");
    expect(locks()).toHaveLength(1);
    context.session = { ...context.session, accountScope: { id: "TEST-space-b", version: 1 } };
    view.rerender(<MaterialsWorkspace api={api} profile={profile} currentFields={fields} onApply={vi.fn()} />);
    await screen.findByText("TEST 资料");
    expect(screen.queryByRole("button", { name: "核对原资料操作" })).toBeNull();
    expect(api.operation).not.toHaveBeenCalled();
    expect(locks()).toHaveLength(1);
  });

  it("同一空间版本变化保留旧请求身份，不能查询或再次提交", async () => {
    context.session.accountScope = { id: "TEST-space-a", version: 1 };
    const api = adapter([row()]);
    vi.mocked(api.mutate).mockRejectedValue(new Error("TEST 结果未知"));
    const view = mount(api);
    fireEvent.click(await screen.findByRole("button", { name: "解析资料" }));
    await screen.findByText("TEST 结果未知");
    const request = vi.mocked(api.mutate).mock.calls[0][0];
    context.session = { ...context.session, accountScope: { id: "TEST-space-a", version: 2 } };
    view.rerender(<MaterialsWorkspace api={api} profile={profile} currentFields={fields} onApply={vi.fn()} />);
    await screen.findByText("TEST 资料");
    fireEvent.click(screen.getByText("查看原资料操作身份"));
    expect((screen.getByLabelText("旧资料操作请求ID") as HTMLInputElement).value).toBe(request.requestId);
    expect(screen.queryByRole("button", { name: "核对原资料操作" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "解析资料" }));
    expect(api.mutate).toHaveBeenCalledTimes(1);
    expect(api.operation).not.toHaveBeenCalled();
    expect(locks()).toHaveLength(1);
  });

  it("v1 未知记录不自动归属当前空间，清草稿重开仍提供原请求ID且不派发", async () => {
    const pending: MaterialPending = { requestId: crypto.randomUUID(), profileVersionId: profile.id, materialId: "material-test", kind: "parse", expectedVersion: 1 };
    const key = legacyMaterialOperationKey(context.session.userId!, profile.id);
    const saved = JSON.stringify(pending);
    localStorage.setItem(key, saved);
    context.session.accountScope = { id: "TEST-space-a", version: 1 };
    const api = adapter([row()]);
    const view = mount(api);
    await screen.findByText("TEST 资料");
    fireEvent.click(screen.getByText("查看原资料操作身份"));
    expect((screen.getByLabelText("旧资料操作请求ID") as HTMLInputElement).value).toBe(pending.requestId);
    clearLocalDrafts();
    view.unmount();
    mount(api);
    await screen.findByText("TEST 资料");
    fireEvent.click(screen.getByRole("button", { name: "解析资料" }));
    fireEvent.click(screen.getByRole("button", { name: "重新读取操作记录" }));
    expect(api.mutate).not.toHaveBeenCalled();
    expect(api.operation).not.toHaveBeenCalled();
    expect(localStorage.getItem(key)).toBe(saved);
    expect(locks()).toHaveLength(1);
  });

  it("同用户换空间后迟到的核对回执不清旧锁、不更新或通知新空间", async () => {
    context.session.accountScope = { id: "TEST-space-a", version: 1 };
    const api = adapter([row()]);
    vi.mocked(api.mutate).mockRejectedValue(new Error("TEST 结果未知"));
    const result = deferred<MaterialReceipt>();
    vi.mocked(api.operation).mockReturnValue(result.promise);
    const view = mount(api);
    fireEvent.click(await screen.findByRole("button", { name: "解析资料" }));
    await screen.findByText("TEST 结果未知");
    const request = vi.mocked(api.mutate).mock.calls[0][0];
    fireEvent.click(screen.getByRole("button", { name: "核对原资料操作" }));
    await waitFor(() => expect(api.operation).toHaveBeenCalledOnce());
    context.session = { ...context.session, accountScope: { id: "TEST-space-b", version: 1 } };
    vi.mocked(api.list).mockResolvedValue([]);
    view.rerender(<MaterialsWorkspace api={api} profile={profile} currentFields={fields} onApply={vi.fn()} />);
    await screen.findByText("暂无资料");
    await act(async () => result.resolve(receipt(request, row("PARSING", 2))));
    expect(screen.queryByText("解析中")).toBeNull();
    expect(context.notify).not.toHaveBeenCalled();
    expect(locks()).toHaveLength(1);
  });

  it("保存等待真实回执和进度；编辑新版本仍是未解析草稿", async () => {
    const api = adapter();
    const pending = deferred<MaterialReceipt>();
    let submitted!: MaterialRequest;
    vi.mocked(api.mutate).mockImplementationOnce((request, options) => {
      submitted = request;
      options.onUploadProgress(24);
      return pending.promise;
    });
    mount(api);
    await screen.findByText("暂无资料");
    await add();
    expect((await screen.findByRole("progressbar")).getAttribute("value")).toBe(
      "24",
    );
    expect(screen.queryByText("资料草稿已同步，尚未解析确认。")).toBeNull();
    const created = {
      ...row(),
      id: submitted.change.materialId,
      ...(submitted.change.kind === "save" ? submitted.change.input : {}),
    };
    await act(async () => pending.resolve(receipt(submitted, created)));
    expect(await screen.findByText("TEST 新资料")).toBeTruthy();
    expect(locks()).toHaveLength(0);
    vi.mocked(api.mutate).mockImplementationOnce(async (request) =>
      receipt(request, {
        ...created,
        ...(request.change.kind === "save" ? request.change.input : {}),
        version: 2,
      }),
    );
    fireEvent.click(screen.getByRole("button", { name: "编辑" }));
    fireEvent.change(screen.getByLabelText("资料内容"), {
      target: { value: "TEST 编辑后正文" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存草稿" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(vi.mocked(api.mutate).mock.calls[1][0].change).toMatchObject({
      kind: "save",
      expectedVersion: 1,
      input: { text: "TEST 编辑后正文" },
    });
    expect(screen.getByText("已同步草稿")).toBeTruthy();
  });
  it("解析受理后刷新结果、对照证据人工确认，再显式填入画像草稿", async () => {
    const api = adapter([row()]);
    const view = mount(api);
    vi.mocked(api.mutate).mockImplementationOnce(async (request) =>
      receipt(request, row("PARSING", 2)),
    );
    fireEvent.click(await screen.findByRole("button", { name: "解析资料" }));
    expect(await screen.findByText("解析中")).toBeTruthy();
    expect(screen.queryByText("已确认")).toBeNull();
    vi.mocked(api.list).mockResolvedValueOnce([row("REVIEW_REQUIRED", 3)]);
    fireEvent.click(screen.getByRole("button", { name: "刷新解析状态" }));
    fireEvent.click(await screen.findByRole("button", { name: "核对提取" }));
    const dialog = screen.getByRole("dialog", { name: "确认资料提取" });
    expect(
      (
        within(dialog).getByRole("button", {
          name: "确认提取结果",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
    fireEvent.change(
      screen.getByLabelText("服务内容提取内容", { selector: "textarea" }),
      { target: { value: "人工核实后的服务" } },
    );
    fireEvent.click(screen.getByLabelText("已核对原文，确认所选提取内容准确"));
    vi.mocked(api.mutate).mockImplementationOnce(async (request) =>
      receipt(request, {
        ...row("READY", 4),
        extraction: {
          ...row("READY", 4).extraction!,
          fields:
            request.change.kind === "confirm" ? request.change.fields : {},
        },
      }),
    );
    fireEvent.click(
      within(dialog).getByRole("button", { name: "确认提取结果" }),
    );
    await screen.findByText("已确认");
    expect(view.onApply).not.toHaveBeenCalled();
    expect(vi.mocked(api.mutate).mock.calls[1][0].change).toMatchObject({
      kind: "confirm",
      expectedVersion: 3,
      extractionId: "extraction-test",
      fields: { service: "人工核实后的服务" },
    });
    fireEvent.click(screen.getByRole("button", { name: "用于画像" }));
    fireEvent.click(screen.getByLabelText("采用目标客户"));
    fireEvent.click(screen.getByLabelText("已核对当前画像，确认替换所选字段"));
    fireEvent.click(
      within(screen.getByRole("dialog")).getByRole("button", {
        name: "填入画像草稿",
      }),
    );
    expect(view.onApply).toHaveBeenCalledWith({ service: "人工核实后的服务" },expect.objectContaining({id:'material-test',profileVersionId:profile.id,version:4,status:'READY'}));
    expect(api.mutate).toHaveBeenCalledTimes(2);
  });
  it("解析失败保留正文且可重试", async () => {
    const api = adapter([
      { ...row("FAILED"), failure: "测试解析服务暂不可用" },
    ]);
    vi.mocked(api.mutate).mockImplementation(async (request) =>
      receipt(request, row("PARSING", 2)),
    );
    mount(api);
    await screen.findByText("测试解析服务暂不可用");
    fireEvent.click(screen.getByRole("button", { name: "重试解析" }));
    await screen.findByText("解析中");
    expect(api.mutate).toHaveBeenCalledTimes(1);
  });
  it("只有确认未执行的失败才释放提交保护且保留输入", async () => {
    const api = adapter();
    vi.mocked(api.mutate).mockImplementation(async (request) => ({
      ...receipt(request, undefined, "FAILED"),
      confirmedNoChange: true,
      message: "资料过期，请刷新核对",
    }));
    mount(api);
    await screen.findByText("暂无资料");
    await add();
    await screen.findByText("资料过期，请刷新核对");
    expect(
      (screen.getByLabelText("资料内容") as HTMLTextAreaElement).value,
    ).toBe("TEST 人工填写内容");
    expect(locks()).toHaveLength(0);
    expect(
      (screen.getByRole("button", { name: "保存草稿" }) as HTMLButtonElement)
        .disabled,
    ).toBe(false);
  });
  it("断网保留原请求，清草稿或重开不会重复提交，只能核对同一回执", async () => {
    const api = adapter([row()]);
    vi.mocked(api.mutate).mockRejectedValue(new Error("网络断开，结果未知"));
    const first = mount(api);
    fireEvent.click(await screen.findByRole("button", { name: "解析资料" }));
    await screen.findByText("网络断开，结果未知");
    const submitted = vi.mocked(api.mutate).mock.calls[0][0];
    expect(locks()).toHaveLength(1);
    expect(localStorage.getItem(locks()[0])).not.toContain("展台");
    clearLocalDrafts();
    first.unmount();
    mount(api);
    await screen.findByText("TEST 资料");
    expect(
      (screen.getByRole("button", { name: "解析资料" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    vi.mocked(api.operation)
      .mockResolvedValueOnce({
        ...receipt(submitted, row("PARSING", 2)),
        profileVersionId: "wrong-profile",
      })
      .mockResolvedValueOnce(receipt(submitted, row("PARSING", 2)));
    fireEvent.click(screen.getByRole("button", { name: "核对原资料操作" }));
    await screen.findByText("资料回执与原请求不匹配，请继续核对原操作。");
    expect(locks()).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "核对原资料操作" }));
    await screen.findByText("解析中");
    expect(locks()).toHaveLength(0);
    expect(api.mutate).toHaveBeenCalledTimes(1);
    expect(api.operation).toHaveBeenLastCalledWith(
      profile.id,
      submitted.requestId,
    );
  });
  it("本机提交记录不可写时不发出写请求", async () => {
    const api = adapter([row()]);
    mount(api);
    await screen.findByText("TEST 资料");
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("storage disabled");
    });
    fireEvent.click(screen.getByRole("button", { name: "解析资料" }));
    await screen.findByText(
      "存在待确认资料操作或本机记录不可写，请先核对原操作。",
    );
    expect(api.mutate).not.toHaveBeenCalled();
  });
  it("写请求 30 秒超时释放等待，迟到回执不能伪报成功，核对后才更新", async () => {
    const api = adapter([row()]);
    const pending = deferred<MaterialReceipt>();
    vi.mocked(api.mutate).mockReturnValue(pending.promise);
    mount(api);
    await screen.findByText("TEST 资料");
    vi.useFakeTimers();
    fireEvent.click(screen.getByRole("button", { name: "解析资料" }));
    await act(async () => {
      await Promise.resolve();
    });
    const request = vi.mocked(api.mutate).mock.calls[0][0];
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30000);
    });
    expect(
      screen.getByText(
        "资料操作等待超时，结果尚未确认，请核对原操作，勿重复提交。",
      ),
    ).toBeTruthy();
    expect(
      (
        screen.getByRole("button", {
          name: "核对原资料操作",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(false);
    await act(async () => pending.resolve(receipt(request, row("PARSING", 2))));
    expect(screen.queryByText("解析中")).toBeNull();
    expect(locks()).toHaveLength(1);
    vi.mocked(api.operation).mockResolvedValue(
      receipt(request, row("PARSING", 2)),
    );
    fireEvent.click(screen.getByRole("button", { name: "核对原资料操作" }));
    await act(async () => {
      await Promise.resolve();
    });
    expect(screen.getByText("解析中")).toBeTruthy();
    expect(locks()).toHaveLength(0);
  });
  it("切换客户空间后旧请求不会通知成功或清除原请求保护", async () => {
    const api = adapter([row()]);
    const pending = deferred<MaterialReceipt>();
    vi.mocked(api.mutate).mockReturnValue(pending.promise);
    const first = mount(api);
    fireEvent.click(await screen.findByRole("button", { name: "解析资料" }));
    await waitFor(() => expect(api.mutate).toHaveBeenCalledOnce());
    const request = vi.mocked(api.mutate).mock.calls[0][0];
    first.unmount();
    context.session.userId = "other-test-user";
    const other = adapter([]);
    mount(other);
    await screen.findByText("暂无资料");
    await act(async () => pending.resolve(receipt(request, row("PARSING", 2))));
    expect(screen.queryByText("TEST 资料")).toBeNull();
    expect(context.notify).not.toHaveBeenCalled();
    expect(locks()).toHaveLength(1);
  });
  it("接口返回其他画像的资料时显示错误，不能退化成正常空态", async () => {
    mount(adapter([{ ...row(), profileVersionId: "other-profile" }]));
    await screen.findByText("资料列表与当前画像不匹配，请刷新重试。");
    expect(screen.queryByText("暂无资料")).toBeNull();
    expect(
      (screen.getByRole("button", { name: "添加资料" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
  });
  it.each(["remove", "revoke"] as const)(
    "%s 必须读取当前引用影响并确认，成功后状态准确",
    async (kind) => {
      const api = adapter([row("READY")]);
      mount(api);
      fireEvent.click(
        await screen.findByRole("button", {
          name: kind === "remove" ? "移除" : "撤销引用",
        }),
      );
      await screen.findByText("联系草稿：TEST 待确认草稿");
      const button = screen.getByRole("button", {
        name: kind === "remove" ? "确认移除" : "确认撤销引用",
      });
      expect((button as HTMLButtonElement).disabled).toBe(true);
      fireEvent.click(screen.getByLabelText("已核对引用影响"));
      vi.mocked(api.mutate).mockImplementation(async (request) =>
        receipt(request, kind === "remove" ? undefined : row("REVOKED", 2)),
      );
      fireEvent.click(button);
      await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
      expect(vi.mocked(api.mutate).mock.calls[0][0].change).toMatchObject({
        kind,
        expectedVersion: 1,
        impactToken: "impact-test",
      });
      await screen.findByText(kind === "remove" ? "暂无资料" : "引用已撤销");
    },
  );
  it("影响查询错误和过期都可重新核对，过期 token 不提交", async () => {
    const api = adapter([row("READY")]);
    vi.mocked(api.impact)
      .mockRejectedValueOnce(new Error("影响查询失败"))
      .mockResolvedValueOnce({
        profileVersionId: profile.id,
        materialId: "material-test",
        version: 1,
        action: "remove",
        token: "expired",
        expiresAt: "2020-01-01T00:00:00Z",
        references: [],
      });
    mount(api);
    fireEvent.click(await screen.findByRole("button", { name: "移除" }));
    await screen.findByText("影响查询失败");
    fireEvent.click(screen.getByRole("button", { name: "重试" }));
    await screen.findByRole("button", { name: "重新核对" });
    expect(
      (screen.getByRole("button", { name: "确认移除" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    expect(api.mutate).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "重新核对" }));
    await screen.findByLabelText("已核对引用影响");
  });
});

describe("P03/P04 提取和输入保护", () => {
  it("保存回执正文与提交快照不一致时不清输入、不释放操作保护", async () => {
    const api = adapter();
    vi.mocked(api.mutate).mockImplementation(async (request) =>
      receipt(request, { ...row(), id: request.change.materialId }),
    );
    mount(api);
    await screen.findByText("暂无资料");
    await add();
    await screen.findByText(
      "保存回执与提交的资料内容不一致，输入和原操作保护仍保留。",
    );
    expect(
      (screen.getByLabelText("资料内容") as HTMLTextAreaElement).value,
    ).toBe("TEST 人工填写内容");
    expect(locks()).toHaveLength(1);
    expect(context.notify).not.toHaveBeenCalled();
  });
  it("提取成功回执未采用人工修改时不关闭面板、不释放操作保护", async () => {
    const api = adapter([row("REVIEW_REQUIRED")]);
    vi.mocked(api.mutate).mockImplementation(async (request) =>
      receipt(request, row("READY", 2)),
    );
    mount(api);
    fireEvent.click(await screen.findByRole("button", { name: "核对提取" }));
    fireEvent.change(
      screen.getByLabelText("服务内容提取内容", { selector: "textarea" }),
      { target: { value: "TEST 人工修正内容" } },
    );
    fireEvent.click(screen.getByLabelText("已核对原文，确认所选提取内容准确"));
    fireEvent.click(screen.getByRole("button", { name: "确认提取结果" }));
    await screen.findByText(
      "提取回执与人工确认内容不一致，输入和原操作保护仍保留。",
    );
    expect(
      (
        screen.getByLabelText("服务内容提取内容", {
          selector: "textarea",
        }) as HTMLTextAreaElement
      ).value,
    ).toBe("TEST 人工修正内容");
    expect(locks()).toHaveLength(1);
    expect(context.notify).not.toHaveBeenCalled();
  });
  it("人工画像在核对期间变化时不能覆盖", async () => {
    const apply = vi.fn();
    const props = {
      record: row("READY"),
      currentFields: fields,
      mode: "apply" as const,
      busy: false,
      locked: false,
      error: "",
      onClose: vi.fn(),
      onConfirm: apply,
    };
    const view = render(<MaterialExtraction {...props} />);
    fireEvent.click(screen.getByLabelText("已核对当前画像，确认替换所选字段"));
    view.rerender(
      <MaterialExtraction
        {...props}
        currentFields={{ ...fields, service: "新人工服务" }}
      />,
    );
    expect(
      screen.getByText(
        "画像内容已变化，请关闭后重新核对，当前不会覆盖人工修改。",
      ),
    ).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "填入画像草稿" }));
    expect(apply).not.toHaveBeenCalled();
  });
  it("文件读取后切换文字编辑，迟到结果不得覆盖人工内容", async () => {
    const pending = deferred<string>();
    const save = vi.fn();
    render(
      <MaterialEditor
        busy={false}
        locked={false}
        error=""
        progress={null}
        onClose={vi.fn()}
        onSave={save}
      />,
    );
    fireEvent.change(screen.getByLabelText("资料名称"), {
      target: { value: "TEST 资料" },
    });
    fireEvent.click(screen.getByRole("tab", { name: "上传文件" }));
    const file = new File(["old"], "test.txt");
    Object.defineProperty(file, "text", { value: () => pending.promise });
    fireEvent.change(screen.getByLabelText("上传资料文件"), {
      target: { files: [file] },
    });
    fireEvent.click(screen.getByRole("tab", { name: "粘贴文字" }));
    fireEvent.change(screen.getByLabelText("资料内容"), {
      target: { value: "TEST 新人工内容" },
    });
    await act(async () => pending.resolve("TEST 过期文件内容"));
    expect(
      (screen.getByLabelText("资料内容") as HTMLTextAreaElement).value,
    ).toBe("TEST 新人工内容");
    fireEvent.click(screen.getByRole("button", { name: "保存草稿" }));
    expect(save).toHaveBeenCalledWith(
      expect.objectContaining({ text: "TEST 新人工内容" }),
    );
  });
  it("资料修改退出有确认；选择内部资料不会自动批准对外引用", () => {
    const close = vi.fn();
    render(
      <MaterialEditor
        busy={false}
        locked={false}
        error=""
        progress={null}
        onClose={close}
        onSave={vi.fn()}
      />,
    );
    fireEvent.change(screen.getByLabelText("资料名称"), {
      target: { value: "TEST" },
    });
    fireEvent.click(screen.getByRole("button", { name: "取消" }));
    expect(screen.getByRole("dialog", { name: "离开资料编辑？" })).toBeTruthy();
    expect(close).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "关闭面板" }));
    expect(close).toHaveBeenCalledOnce();
  });
});

describe("资料证据与回执契约", () => {
  const binding: MaterialPending = {
    requestId: "00000000-0000-4000-8000-000000000001",
    profileVersionId: profile.id,
    materialId: "material-test",
    kind: "parse",
    expectedVersion: 1,
  };
  it("证据必须是同版本资料原文，重复 ID 或错误画像拒绝", () => {
    const record = row("READY");
    expect(() =>
      parseMaterials(
        [
          {
            ...record,
            extraction: { ...record.extraction!, materialVersion: 2 },
          },
        ],
        profile.id,
      ),
    ).toThrow();
    expect(() =>
      parseMaterials(
        [
          {
            ...record,
            extraction: {
              ...record.extraction!,
              evidence: [{ field: "service", quote: "虚构外部成果" }],
            },
          },
        ],
        profile.id,
      ),
    ).toThrow();
    expect(() => parseMaterials([record, record], profile.id)).toThrow();
  });
  it("缺失结果、错误状态、不增版本或未确认失败不能释放原请求", () => {
    for (const candidate of [
      { ...binding, status: "SUCCEEDED" },
      { ...binding, status: "SUCCEEDED", record: row("READY", 2) },
      { ...binding, status: "SUCCEEDED", record: row("PARSING", 1) },
      { ...binding, status: "FAILED" },
    ])
      expect(() => parseMaterialReceipt(candidate, binding)).toThrow();
    expect(
      parseMaterialReceipt(
        { ...binding, status: "FAILED", confirmedNoChange: true },
        binding,
      ).status,
    ).toBe("FAILED");
  });
});
