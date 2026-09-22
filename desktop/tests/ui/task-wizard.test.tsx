// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  act,
  cleanup,
  fireEvent,
  render,
  renderHook,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { TaskWizardPage } from "../../src/renderer/pages/TaskWizard";
import { clearLocalDrafts } from "../../src/renderer/app/hooks";
import { useTaskDraft } from "../../src/renderer/app/taskDraft";
import { parseRoute } from "../../src/renderer/domain/routes";
import {
  EMPTY_PROFILE,
  PLATFORMS,
  newTaskDraft,
  type PlatformConnection,
  type Profile,
  type Suggestion,
  type TaskDraft,
  type TaskRun,
} from "../../src/renderer/domain/models";
import { makeTerm, taskFingerprint } from "../../src/renderer/domain/task";
import { defaultResearchSettings } from "../../src/renderer/domain/researchUsage";
import {
  ServiceError,
  type YikeService,
} from "../../src/renderer/services/contracts";
import type { AppContextValue } from "../../src/renderer/app/context";

let context: AppContextValue;
vi.mock("../../src/renderer/app/context", () => ({ useApp: () => context }));
const profiles: Profile[] = [
  {
    id: "profile-one",
    version: 1,
    status: "CONFIRMED",
    description: "测试画像一",
    fields: { ...EMPTY_PROFILE, service: "测试服务一" },
  },
  {
    id: "profile-two",
    version: 2,
    status: "CONFIRMED",
    description: "测试画像二",
    fields: { ...EMPTY_PROFILE, service: "测试服务二" },
  },
];
const connections: PlatformConnection[] = [
  {
    platform: "xhs",
    status: "CONNECTED",
    accountId: "account-one",
    accountName: "测试账号一",
    capabilities: ["search", "read", "monitor"],
  },
  {
    platform: "xhs",
    status: "CONNECTED",
    accountId: "account-two",
    accountName: "测试账号二",
    capabilities: ["search", "read", "monitor"],
  },
];
beforeEach(() => {
  clearLocalDrafts();
  sessionStorage.clear();
  localStorage.clear();
  context = {
    service: {
      profiles: vi.fn().mockResolvedValue(profiles),
      connections: vi.fn().mockResolvedValue(connections),
      info: vi.fn().mockResolvedValue({
        version: "0.2.0",
        platform: "test",
        serviceConfigured: true,
        deviceReady: true,
      }),
      suggest: vi
        .fn()
        .mockRejectedValue(
          new ServiceError("UNAVAILABLE", "测试建议服务不可用", 501),
        ),
      startTask: vi.fn(async (draft: TaskDraft) => ({
        id: "test-created-run",
        name: draft.name,
        mode: draft.mode,
        status: "PENDING",
        platforms: draft.platforms,
      })),
    } as unknown as YikeService,
    session: { authenticated: true, userId: crypto.randomUUID() },
    sessionReady: true,
    route: parseRoute("#/tasks/new"),
    navigate: vi.fn(),
    notify: vi.fn(),
    refreshSession: vi.fn(),
  };
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});
function seed(patch: Partial<TaskDraft> = {}): TaskDraft {
  const value = {
    ...newTaskDraft(),
    name: "测试采集任务",
    profileId: "profile-one",
    profileVersion: 1,
    terms: [makeTerm("人工需求")],
    platforms: ["xhs"] as TaskDraft["platforms"],
    accounts: { xhs: "account-one" },
    ...patch,
  };
  sessionStorage.setItem(
    "yike.ui.draft.v1.task." + context.session.userId,
    JSON.stringify(value),
  );
  return value;
}
function currentDraft(): TaskDraft {
  return JSON.parse(
    sessionStorage.getItem("yike.ui.draft.v1.task." + context.session.userId)!,
  );
}
function addKeyword(value: string) {
  fireEvent.click(
    within(screen.getByRole("group", { name: "搜索关键词" })).getByRole(
      "button",
      { name: "添加" },
    ),
  );
  const input = screen.getByRole("textbox", { name: "新增搜索关键词" });
  fireEvent.change(input, { target: { value } });
  fireEvent.keyDown(input, { key: "Enter" });
}
function followNavigation(view: ReturnType<typeof render>) {
  const calls = vi.mocked(context.navigate).mock.calls;
  context = { ...context, route: parseRoute("#" + calls[calls.length - 1][0]) };
  view.rerender(<TaskWizardPage />);
}
async function confirmReady() {
  fireEvent.click(
    screen.getByRole("checkbox", {
      name: "我已核对以上业务画像、搜索条件、账号与运行设置",
    }),
  );
  const start = screen.getByRole("button", {
    name: "确认并启动",
  }) as HTMLButtonElement;
  await waitFor(() => expect(start.disabled).toBe(false));
  return start;
}

function expectPlatformState(name: string, status: string) {
  const accessibleName = status ? `${name} ${status}` : name;
  const checkbox = screen.getByRole("checkbox", { name: accessibleName });
  // Explicitly update Chromium's AX name as well as the changing implicit label.
  expect(checkbox.getAttribute("aria-label")).toBe(accessibleName);
  const label = checkbox.closest("label")!;
  expect(within(label).getByText(name)).toBeTruthy();
  expect(label.querySelector("small")?.textContent || "").toBe(status);
  return checkbox;
}

describe("platform selection state names", () => {
  it("offers login without requesting private platform state and preserves guest drafting", async () => {
    context.session = { authenticated: false, userId: "" };
    context.service.connections = vi.fn().mockRejectedValue(new Error("TEST 未登录读取失败"));
    const view = render(<TaskWizardPage />);
    await act(async () => {});
    expect(context.service.connections).not.toHaveBeenCalled();
    expect(context.service.profiles).not.toHaveBeenCalled();
    for (const platform of PLATFORMS)
      expectPlatformState(platform.name, platform.id === "web" ? "无需账号" : "登录后查看");
    expect(screen.queryByText("TEST 未登录读取失败")).toBeNull();
    fireEvent.change(screen.getByRole("textbox", {name: "任务名称"}), {target: {value: "先记录需求"}});
    fireEvent.click(screen.getByRole("button", {name: "保存草稿"}));
    expect(context.notify).toHaveBeenCalledWith("任务草稿已保存在本机会话中，尚未启动。", "success");
    fireEvent.click(screen.getByRole("button", {name: "登录客户空间"}));
    expect(context.navigate).toHaveBeenCalledWith("/login");
    expect(context.service.startTask).not.toHaveBeenCalled();

    context.service.connections = vi.fn().mockResolvedValue(connections);
    context = {...context, session: {authenticated: true, userId: crypto.randomUUID()}};
    view.rerender(<TaskWizardPage />);
    await screen.findByRole("checkbox", {name: "小红书 已连接"});
    expect(context.service.connections).toHaveBeenCalledOnce();
    expect(screen.queryByRole("button", {name: "登录客户空间"})).toBeNull();
  });

  it("discards a pending platform read on logout rather than presenting a connected guest", async () => {
    let finish!: (value: PlatformConnection[]) => void;
    context.service.connections = vi.fn(() => new Promise<PlatformConnection[]>(resolve => {finish = resolve;}));
    const view = render(<TaskWizardPage />);
    expectPlatformState("小红书", "读取中");
    context = {...context, session: {authenticated: false, userId: ""}};
    view.rerender(<TaskWizardPage />);
    await act(async () => finish(connections));
    expectPlatformState("小红书", "登录后查看");
    expect(context.service.connections).toHaveBeenCalledOnce();
    expect(screen.queryByRole("checkbox", {name: /已连接|读取失败/})).toBeNull();
  });

  it('does not ask for an account for public websites or mark the scope executable', async () => {
    render(<TaskWizardPage />);
    await screen.findByRole('checkbox', {name:'小红书 已连接'});
    const website = expectPlatformState('公开网站', '无需账号');
    expect((website as HTMLInputElement).checked).toBe(false);
    expect(context.service.startTask).not.toHaveBeenCalled();
    expect(screen.queryByRole('checkbox', {name:'公开网站 已连接'})).toBeNull();
  });
  it("keeps visible and explicit accessible names in sync from loading to failure", async () => {
    let reject!: (error: Error) => void;
    context.service.connections = vi.fn(() => new Promise<PlatformConnection[]>((_, fail) => { reject = fail; }));
    render(<TaskWizardPage />);
    for (const platform of PLATFORMS) expectPlatformState(platform.name, platform.id === "web" ? "无需账号" : "读取中");
    await act(async () => reject(new Error("TEST 连接读取失败")));
    for (const platform of PLATFORMS) expectPlatformState(platform.name, platform.id === "web" ? "无需账号" : "读取失败");
    expect(screen.queryByRole("checkbox", { name: /读取中|已连接/ })).toBeNull();
    // Selecting a draft's scope never asserts that it is executable.
    fireEvent.click(expectPlatformState("小红书", "读取失败"));
    expect((expectPlatformState("小红书", "读取失败") as HTMLInputElement).checked).toBe(true);
    expect(context.service.startTask).not.toHaveBeenCalled();
  });

  it("names only the actual ready records and does not equate registration with execution", async () => {
    context.service.connections = vi.fn().mockResolvedValue([
      { ...connections[0], capabilities: [], registration: { connectionId: "TEST-registry", deviceId: "TEST-device", version: 1, connectedAt: "2026-09-10T00:00:00Z", disconnectedAt: null } },
      { platform: "douyin", status: "UNVERIFIED", capabilities: [] },
      { platform: "bilibili", status: "EXPIRED", capabilities: [] },
      { platform: "zhihu", status: "UNAVAILABLE", capabilities: [] },
    ]);
    render(<TaskWizardPage />);
    await screen.findByRole("checkbox", { name: "小红书 已连接" });
    expectPlatformState("小红书", "已连接");
    expectPlatformState("抖音", "待核验");
    for (const name of ["B站", "知乎"]) expectPlatformState(name, "待连接");
    expectPlatformState("公开网站", "无需账号");
    expect(screen.queryByRole("checkbox", { name: /读取中|可用/ })).toBeNull();
    expect(context.service.startTask).not.toHaveBeenCalled();
  });

  it("does not restore an old space's connected name after the new space fails", async () => {
    let finishOld!: (value: PlatformConnection[]) => void;
    context.session.accountScope = { id: "TEST-space-a", version: 1 };
    context.service.connections = vi.fn()
      .mockImplementationOnce(() => new Promise<PlatformConnection[]>((resolve) => { finishOld = resolve; }))
      .mockRejectedValueOnce(new Error("TEST 新空间读取失败"));
    const view = render(<TaskWizardPage />);
    expectPlatformState("小红书", "读取中");
    context = { ...context, session: { ...context.session, accountScope: { id: "TEST-space-b", version: 1 } } };
    view.rerender(<TaskWizardPage />);
    await screen.findByRole("checkbox", { name: "小红书 读取失败" });
    await act(async () => finishOld(connections));
    for (const platform of PLATFORMS) expectPlatformState(platform.name, platform.id === "web" ? "无需账号" : "读取失败");
    expect(screen.queryByRole("checkbox", { name: /已连接|读取中/ })).toBeNull();
  });

  it("preserves the platform-only name for historical drafts without research state", async () => {
    seed({ research: undefined });
    render(<TaskWizardPage />);
    await screen.findByText("已确认业务画像");
    for (const platform of PLATFORMS) expectPlatformState(platform.name, "");
  });
});

describe("explicit platform collection entry", () => {
  it.each([{}, { xhs: "account-two" }])(
    "switches only on request and preserves the collection draft with accounts %j",
    async (accounts) => {
      const saved = seed({
        research: defaultResearchSettings(),
        accounts,
        exclusions: [makeTerm("人工排除")],
        platformTerms: { xhs: [makeTerm("平台搜索词")] },
        executionLimits: { max_records: 37, max_runtime_seconds: 180 },
        savedAt: "2026-09-13T00:00:00Z",
      });
      context.service.researchUsage = { quote: vi.fn() };
      const view = render(<TaskWizardPage />);
      const switchMode = await screen.findByRole("button", { name: "使用平台采集" });
      await screen.findByText("已确认业务画像");
      expect(currentDraft()).toEqual(saved);
      expect(screen.getByRole("heading", { name: "研究用量" })).toBeTruthy();

      fireEvent.click(switchMode);
      const { research: _research, ...collection } = saved;
      expect(currentDraft()).toEqual({ ...collection, revision: saved.revision + 1, savedAt: null });
      expect(taskFingerprint(currentDraft())).not.toBe(taskFingerprint(saved));
      expect(screen.queryByRole("heading", { name: "研究用量" })).toBeNull();
      expect(screen.queryByRole("button", { name: "配置研究用量" })).toBeNull();
      expect(screen.queryByRole("button", { name: "使用平台采集" })).toBeNull();
      view.unmount();
      render(<TaskWizardPage />);
      await screen.findByText("已确认业务画像");
      expect(currentDraft().research).toBeUndefined();
      expect(context.service.researchUsage.quote).not.toHaveBeenCalled();
      expect(context.service.suggest).not.toHaveBeenCalled();
      expect(context.service.startTask).not.toHaveBeenCalled();
      expect(context.navigate).not.toHaveBeenCalled();
    },
  );

  it.each<TaskDraft["platforms"]>([[], ["web"], ["xhs", "web"]])(
    "does not offer a platform-only switch for scope %j",
    async (...platforms) => {
      const saved = seed({ research: defaultResearchSettings(), platforms });
      render(<TaskWizardPage />);
      await screen.findByText("已确认业务画像");
      expect(screen.queryByRole("button", { name: "使用平台采集" })).toBeNull();
      expect(screen.getByRole("heading", { name: "研究用量" })).toBeTruthy();
      expect(currentDraft()).toEqual(saved);
      expect(context.service.startTask).not.toHaveBeenCalled();
    },
  );

  it("clears an earlier configuration review when switching to platform collection", async () => {
    seed({ research: defaultResearchSettings() });
    context.route = parseRoute("#/tasks/new?step=confirm");
    const view = render(<TaskWizardPage />);
    await screen.findByText("执行服务已就绪");
    const reviewName = "我已核对以上业务画像、搜索条件、账号与运行设置";
    fireEvent.click(screen.getByRole("checkbox", { name: reviewName }));
    expect((screen.getByRole("checkbox", { name: reviewName }) as HTMLInputElement).checked).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "返回修改" }));
    followNavigation(view);
    fireEvent.click(screen.getByRole("button", { name: "使用平台采集" }));
    fireEvent.click(screen.getByRole("button", { name: "下一步：连接平台" }));
    followNavigation(view);
    fireEvent.click(screen.getByRole("button", { name: "下一步：确认任务" }));
    followNavigation(view);
    expect((screen.getByRole("checkbox", { name: reviewName }) as HTMLInputElement).checked).toBe(false);
    expect((screen.getByRole("button", { name: "确认并启动" }) as HTMLButtonElement).disabled).toBe(true);
    expect(context.service.startTask).not.toHaveBeenCalled();
  });

  it("does not label a non-research task as a historical research draft", async () => {
    seed();
    render(<TaskWizardPage />);
    await screen.findByText("已确认业务画像");
    expect(screen.queryByRole("heading", { name: "研究用量" })).toBeNull();
    expect(screen.queryByText("此历史草稿尚未配置搜贝上限。")).toBeNull();
    expect(screen.queryByRole("button", { name: "配置研究用量" })).toBeNull();
  });
});

describe("task wizard service boundary", () => {
  it('edits platform-specific words in the real wizard and restores their saved draft',async()=>{
    seed({platforms:['xhs','bilibili']});
    const view=render(<TaskWizardPage/>);
    await screen.findByText('已确认业务画像');
    fireEvent.click(screen.getByText('按平台设置搜索词'));
    fireEvent.click(screen.getByRole('button',{name:'小红书单独设置'}));
    const group=screen.getByRole('group',{name:'小红书搜索词'});
    fireEvent.click(within(group).getByRole('button',{name:'人工需求'}));
    const editor=within(group).getByRole('textbox',{name:'修改人工需求'});
    fireEvent.change(editor,{target:{value:'有没有搭建公司'}});
    fireEvent.keyDown(editor,{key:'Enter'});
    expect(currentDraft().platformTerms?.xhs?.map(term=>term.value)).toEqual(['有没有搭建公司']);
    expect(currentDraft().terms.map(term=>term.value)).toEqual(['人工需求']);
    fireEvent.click(screen.getByRole('button',{name:'保存草稿'}));
    view.unmount();render(<TaskWizardPage/>);
    fireEvent.click(screen.getByText('按平台设置搜索词'));
    expect(screen.getByRole('button',{name:'有没有搭建公司'})).toBeTruthy();
    fireEvent.click(screen.getByRole('button',{name:'小红书恢复通用词'}));
    expect(currentDraft().platformTerms).toBeUndefined();
    expect(context.service.startTask).not.toHaveBeenCalled();
  });
  it("uses the controlled suggestion disclosure path without legacy auto-generation", async () => {
    const versionId = "33333333-3333-4333-8333-333333333333";
    context.service.profiles = vi.fn().mockResolvedValue([{ ...profiles[0], id: versionId }]);
    context.session.accountScope = { id: "space-a", version: 1 };
    context.service.searchSuggestions = {
      preview: vi.fn().mockResolvedValue({
        profile_version_id: versionId, profile_sha256: "a".repeat(64), description: "完整业务介绍",
        model_provider: "controlled-provider", model_name: "controlled-model",
        disclosure_policy_version: "profile-description-v1",
      }),
      submit: vi.fn(), getReceipt: vi.fn(),
    };
    seed({ profileId: versionId, terms: [], exclusions: [] });
    render(<TaskWizardPage />);
    await screen.findByText("已确认业务画像");
    expect(context.service.suggest).not.toHaveBeenCalled();
    expect(context.service.searchSuggestions.preview).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "生成建议" }));
    expect((await screen.findAllByText("完整业务介绍")).length).toBe(1);
    expect(context.service.searchSuggestions.submit).not.toHaveBeenCalled();
  });

  it("does not regenerate a saved empty draft on entry or remount", async () => {
    seed({ terms: [], exclusions: [], savedAt: "2026-09-09T00:00:00Z" });
    const view = render(<TaskWizardPage />);
    await screen.findByText("已确认业务画像");
    expect(context.service.suggest).not.toHaveBeenCalled();
    view.unmount();
    render(<TaskWizardPage />);
    await screen.findByText("已确认业务画像");
    expect(context.service.suggest).not.toHaveBeenCalled();
  });

  it("does not auto-generate on confirmation or replace manually entered exclusions", async () => {
    seed({ terms: [], exclusions: [makeTerm("人工排除")] });
    const view = render(<TaskWizardPage />);
    await screen.findByText("已确认业务画像");
    expect(context.service.suggest).not.toHaveBeenCalled();
    context.route = parseRoute("#/tasks/new?step=confirm");
    view.rerender(<TaskWizardPage />);
    expect(context.service.suggest).not.toHaveBeenCalled();
  });

  it.each(["connect", "confirm"])(
    "never starts a suggestion request on the %s step even with empty conditions",
    async (step) => {
      seed({ terms: [], exclusions: [] });
      context.route = parseRoute(`#/tasks/new?step=${step}`);
      render(<TaskWizardPage />);
      await waitFor(() =>
        expect(context.service.profiles).toHaveBeenCalledOnce(),
      );
      await act(async () => {});
      expect(context.service.suggest).not.toHaveBeenCalled();
    },
  );

  it("saving during an automatic request preserves the saved empty snapshot and rejects late fill", async () => {
    seed({ terms: [], exclusions: [] });
    let finish!: (value: Suggestion) => void;
    let requestId = "";
    context.service.suggest = vi.fn((_profile, id) => {
      requestId = id;
      return new Promise<Suggestion>((resolve) => {
        finish = resolve;
      });
    });
    const view = render(<TaskWizardPage />);
    await waitFor(() => expect(context.service.suggest).toHaveBeenCalledOnce());
    fireEvent.click(screen.getByRole("button", { name: "保存草稿" }));
    expect(currentDraft().savedAt).toBeTruthy();
    await act(async () =>
      finish({
        profileId: "profile-one",
        requestId,
        keywords: ["未保存的晚到词"],
        exclusions: [],
      }),
    );
    expect(currentDraft().terms).toEqual([]);
    view.unmount();
    render(<TaskWizardPage />);
    await screen.findByText("已确认业务画像");
    expect(context.service.suggest).toHaveBeenCalledOnce();
  });

  it("cancels automatic suggestions immediately and ignores a transport that resolves late", async () => {
    seed({ terms: [], exclusions: [] });
    let finish!: (value: Suggestion) => void;
    let signal!: AbortSignal;
    let requestId = "";
    context.service.suggest = vi.fn((_profile, id, requestSignal) => {
      signal = requestSignal!;
      requestId = id;
      return new Promise<Suggestion>((resolve) => {
        finish = resolve;
      });
    });
    render(<TaskWizardPage />);
    await waitFor(() => expect(context.service.suggest).toHaveBeenCalledOnce());
    fireEvent.click(screen.getByRole("button", { name: "取消生成" }));
    expect(signal.aborted).toBe(true);
    expect(screen.getByText(/已取消建议生成/)).toBeTruthy();
    addKeyword("继续人工填写");
    await act(async () =>
      finish({
        profileId: "profile-one",
        requestId,
        keywords: ["已取消的晚到词"],
        exclusions: [],
      }),
    );
    expect(screen.queryByText("已取消的晚到词")).toBeNull();
    expect(screen.queryByRole("dialog", { name: "更新搜索建议" })).toBeNull();
    expect(currentDraft().terms.map((t) => t.value)).toEqual(["继续人工填写"]);
  });

  it("times out hanging suggestions and permits an explicit retry without applying late data", async () => {
    seed();
    let finish!: (value: Suggestion) => void;
    let oldId = "";
    context.service.suggest = vi
      .fn()
      .mockImplementationOnce((_profile, id) => {
        oldId = id;
        return new Promise((resolve) => {
          finish = resolve;
        });
      })
      .mockImplementationOnce(async (profileId, requestId) => ({
        profileId,
        requestId,
        keywords: ["重试新建议"],
        exclusions: [],
      }));
    render(<TaskWizardPage />);
    await screen.findByText("已确认业务画像");
    vi.useFakeTimers();
    await act(async () =>
      fireEvent.click(screen.getByRole("button", { name: "重新生成" })),
    );
    await act(async () => vi.advanceTimersByTimeAsync(45_000));
    expect(screen.getByText(/搜索建议生成超时/)).toBeTruthy();
    expect(currentDraft().terms.map((t) => t.value)).toEqual(["人工需求"]);
    await act(async () =>
      fireEvent.click(screen.getByRole("button", { name: "重新生成" })),
    );
    const dialog = screen.getByRole("dialog", { name: "更新搜索建议" });
    await act(async () =>
      finish({
        profileId: "profile-one",
        requestId: oldId,
        keywords: ["超时旧词"],
        exclusions: [],
      }),
    );
    expect(screen.queryByText("超时旧词")).toBeNull();
    fireEvent.click(
      within(dialog).getByRole("button", { name: "合并新增建议" }),
    );
    expect(currentDraft().terms.map((t) => t.value)).toEqual([
      "人工需求",
      "重试新建议",
    ]);
  });

  it.each(["ai", "manual"] as const)(
    "retains %s condition origin after profile changes through the final summary",
    async (origin) => {
      seed({
        terms: [makeTerm("原画像条件", origin)],
        suggestionProfile: origin === "ai" ? "profile-one" : null,
      });
      const view = render(<TaskWizardPage />);
      await screen.findByText("已确认业务画像");
      fireEvent.change(screen.getByRole("combobox", { name: "业务画像" }), {
        target: { value: "profile-two" },
      });
      expect(
        screen.getByText(/当前搜索条件仍来自「测试服务一 · v1」/),
      ).toBeTruthy();
      expect(currentDraft().terms.map((t) => t.value)).toEqual(["原画像条件"]);
      expect(context.service.suggest).not.toHaveBeenCalled();
      fireEvent.click(screen.getByRole("button", { name: "下一步：连接平台" }));
      followNavigation(view);
      fireEvent.click(screen.getByRole("button", { name: "下一步：确认任务" }));
      followNavigation(view);
      expect(
        screen.getByText(/当前搜索条件仍来自「测试服务一 · v1」/),
      ).toBeTruthy();
      expect(screen.getByText("原画像条件")).toBeTruthy();
      expect(context.service.startTask).not.toHaveBeenCalled();
    },
  );

  it("keeps manual edits while a delayed automatic suggestion waits for explicit merge", async () => {
    seed({ terms: [], exclusions: [] });
    let resolve!: (value: Suggestion) => void;
    let requestId = "";
    context.service.suggest = vi.fn((_profileId, id) => {
      requestId = id;
      return new Promise<Suggestion>((done) => {
        resolve = done;
      });
    });
    render(<TaskWizardPage />);
    expect(screen.queryByText(/结果返回本机后再过滤/)).toBeNull();
    await waitFor(() => expect(context.service.suggest).toHaveBeenCalledOnce());
    addKeyword("人工输入");
    await act(async () =>
      resolve({
        profileId: "profile-one",
        requestId,
        keywords: ["新建议"],
        exclusions: ["招聘"],
      }),
    );
    const dialog = await screen.findByRole("dialog", { name: "更新搜索建议" });
    expect(currentDraft().terms.map((t) => t.value)).toEqual(["人工输入"]);
    fireEvent.click(
      within(dialog).getByRole("button", { name: "合并新增建议" }),
    );
    await screen.findByRole("button", { name: "新建议" });
    expect(currentDraft().terms.map((t) => t.value)).toEqual([
      "人工输入",
      "新建议",
    ]);
    expect(currentDraft().platforms).toEqual(["xhs"]);
    expect(context.service.startTask).not.toHaveBeenCalled();
  });

  it("preserves edited and deleted terms when replacing untouched AI suggestions", async () => {
    const original = seed({
      mode: "monitor",
      terms: [
        makeTerm("人工需求"),
        makeTerm("原AI词", "ai"),
        makeTerm("删除词", "ai"),
        makeTerm("旧AI词", "ai"),
      ],
    });
    context.service.suggest = vi.fn(async (profileId, requestId) => ({
      profileId,
      requestId,
      keywords: ["删除词", "全新建议"],
      exclusions: ["招聘"],
    }));
    render(<TaskWizardPage />);
    await screen.findByText("已确认业务画像");
    fireEvent.click(screen.getByRole("button", { name: "原AI词" }));
    const input = screen.getByRole("textbox", { name: "修改原AI词" });
    fireEvent.change(input, { target: { value: "人工改过建议" } });
    fireEvent.keyDown(input, { key: "Enter" });
    fireEvent.click(screen.getByRole("button", { name: "删除删除词" }));
    fireEvent.click(screen.getByRole("button", { name: "重新生成" }));
    const dialog = await screen.findByRole("dialog", { name: "更新搜索建议" });
    fireEvent.click(
      within(dialog).getByRole("button", { name: "替换未修改的建议" }),
    );
    await screen.findByRole("button", { name: "全新建议" });
    expect(currentDraft().terms.map((t) => t.value)).toEqual([
      "人工需求",
      "人工改过建议",
      "全新建议",
    ]);
    expect(currentDraft().schedule).toEqual(original.schedule);
    expect(currentDraft().mode).toBe("monitor");
  });

  it("aborts profile-one suggestions and ignores their late response after choosing profile two", async () => {
    seed({ terms: [] });
    const requests: {
      profileId: string;
      requestId: string;
      signal?: AbortSignal;
      resolve: (value: Suggestion) => void;
    }[] = [];
    context.service.suggest = vi.fn(
      (profileId, requestId, signal) =>
        new Promise<Suggestion>((resolve) =>
          requests.push({ profileId, requestId, signal, resolve }),
        ),
    );
    render(<TaskWizardPage />);
    await waitFor(() => expect(requests).toHaveLength(1));
    fireEvent.change(screen.getByRole("combobox", { name: "业务画像" }), {
      target: { value: "profile-two" },
    });
    await waitFor(() => expect(requests).toHaveLength(2));
    expect(requests[0].signal?.aborted).toBe(true);
    await act(async () =>
      requests[0].resolve({
        profileId: "profile-one",
        requestId: requests[0].requestId,
        keywords: ["旧画像迟到词"],
        exclusions: [],
      }),
    );
    expect(screen.queryByText("旧画像迟到词")).toBeNull();
    await act(async () =>
      requests[1].resolve({
        profileId: "profile-two",
        requestId: requests[1].requestId,
        keywords: ["新画像建议"],
        exclusions: [],
      }),
    );
    await screen.findByRole("button", { name: "新画像建议" });
    expect(currentDraft().profileId).toBe("profile-two");
    expect(currentDraft().profileVersion).toBe(2);
    expect(currentDraft().terms.map((t) => t.value)).toEqual(["新画像建议"]);
  });

  it("retains all steps and requires a new confirmation after editing the final task fingerprint", async () => {
    // This fixture exercises the existing unversioned startTask adapter.
    const legacySchedule = { ...newTaskDraft("monitor").schedule };
    delete legacySchedule.policyVersion;
    seed({ mode: "monitor", schedule: legacySchedule });
    context.route = parseRoute("#/tasks/new?mode=monitor");
    const view = render(<TaskWizardPage />);
    await screen.findByText("已确认业务画像");
    fireEvent.change(screen.getByRole("textbox", { name: "任务名称" }), {
      target: { value: "修改后的监控任务" },
    });
    addKeyword("另一个人工词");
    fireEvent.click(screen.getByRole("button", { name: "下一步：连接平台" }));
    followNavigation(view);
    await screen.findByRole("option", { name: "测试账号二" });
    fireEvent.change(screen.getByRole("combobox", { name: "小红书执行账号" }), {
      target: { value: "account-two" },
    });
    fireEvent.click(screen.getByRole("button", { name: "下一步：确认任务" }));
    followNavigation(view);
    await confirmReady();
    fireEvent.click(screen.getByRole("button", { name: "返回修改" }));
    followNavigation(view);
    expect(
      (screen.getByRole("textbox", { name: "任务名称" }) as HTMLInputElement)
        .value,
    ).toBe("修改后的监控任务");
    expect(screen.getByRole("button", { name: "另一个人工词" })).toBeTruthy();
    fireEvent.change(screen.getByRole("textbox", { name: "任务名称" }), {
      target: { value: "最终监控任务" },
    });
    fireEvent.click(screen.getByRole("button", { name: "下一步：连接平台" }));
    followNavigation(view);
    await screen.findByRole("option", { name: "测试账号二" });
    expect(
      (
        screen.getByRole("combobox", {
          name: "小红书执行账号",
        }) as HTMLSelectElement
      ).value,
    ).toBe("account-two");
    fireEvent.click(screen.getByRole("button", { name: "下一步：确认任务" }));
    followNavigation(view);
    expect(
      (screen.getByRole("button", { name: "确认并启动" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    const start = await confirmReady();
    fireEvent.click(start);
    await waitFor(() =>
      expect(context.service.startTask).toHaveBeenCalledOnce(),
    );
    const [sent, requestId] = vi.mocked(context.service.startTask).mock
      .calls[0];
    expect(sent).toMatchObject({
      name: "最终监控任务",
      mode: "monitor",
      profileId: "profile-one",
      profileVersion: 1,
      accounts: { xhs: "account-two" },
    });
    expect(sent.terms.map((t) => t.value)).toEqual([
      "人工需求",
      "另一个人工词",
    ]);
    expect(requestId).toBe(`task:${sent.id}:${sent.revision}`);
  });

  it("rechecks capabilities immediately before start and never submits after capability revocation", async () => {
    seed();
    context.route = parseRoute("#/tasks/new?step=confirm");
    render(<TaskWizardPage />);
    const start = await confirmReady();
    vi.mocked(context.service.connections).mockResolvedValueOnce([
      { ...connections[0], capabilities: [] },
    ]);
    fireEvent.click(start);
    await screen.findByText("小红书 的搜索能力尚未通过检查。");
    expect(context.service.startTask).not.toHaveBeenCalled();
    expect(start.disabled).toBe(true);
    expect(
      (
        screen.getByRole("checkbox", {
          name: "我已核对以上业务画像、搜索条件、账号与运行设置",
        }) as HTMLInputElement
      ).checked,
    ).toBe(false);
  });

  it.each([
    {
      patch: {
        source: "links" as const,
        links: "https://example.test/public-source",
      },
      reason: "小红书 的读取能力尚未通过检查。",
    },
    {
      patch: { mode: "monitor" as const },
      reason: "小红书 尚不具备持续监控能力。",
    },
  ])(
    "requires the specific execution capability: $reason",
    async ({ patch, reason }) => {
      seed(patch);
      context.route = parseRoute("#/tasks/new?step=confirm");
      context.service.connections = vi
        .fn()
        .mockResolvedValue([{ ...connections[0], capabilities: ["search"] }]);
      render(<TaskWizardPage />);
      await screen.findByText(reason);
      fireEvent.click(
        screen.getByRole("checkbox", {
          name: "我已核对以上业务画像、搜索条件、账号与运行设置",
        }),
      );
      expect(
        (
          screen.getByRole("button", {
            name: "确认并启动",
          }) as HTMLButtonElement
        ).disabled,
      ).toBe(true);
      expect(context.service.startTask).not.toHaveBeenCalled();
    },
  );

  it("allows a retry after an explicit capability rejection without inventing a created task", async () => {
    seed();
    context.route = parseRoute("#/tasks/new?step=confirm");
    context.service.startTask = vi
      .fn()
      .mockRejectedValue(
        new ServiceError("CAPABILITY_UNAVAILABLE", "测试启动能力未接通", 501),
      );
    render(<TaskWizardPage />);
    fireEvent.click(await confirmReady());
    await screen.findByText("测试启动能力未接通");
    await waitFor(() =>
      expect(
        (
          screen.getByRole("button", {
            name: "确认并启动",
          }) as HTMLButtonElement
        ).disabled,
      ).toBe(false),
    );
    expect(
      screen.queryByText("启动结果尚未确认，请先检查任务列表，避免重复创建。"),
    ).toBeNull();
    expect(context.navigate).not.toHaveBeenCalled();
    expect(context.notify).not.toHaveBeenCalled();
  });

  it.each(["NETWORK_ERROR", "SERVICE_TIMEOUT", "SERVICE_UNAVAILABLE"])(
    "keeps an unknown %s start locked across remount instead of duplicating the request",
    async (code) => {
      seed();
      context.route = parseRoute("#/tasks/new?step=confirm");
      context.service.startTask = vi
        .fn()
        .mockRejectedValue(new ServiceError(code, "测试网络结果未知"));
      const view = render(<TaskWizardPage />);
      fireEvent.click(await confirmReady());
      await screen.findByText(
        "启动结果尚未确认，请先检查任务列表，避免重复创建。",
      );
      expect(
        (
          screen.getByRole("button", {
            name: "确认并启动",
          }) as HTMLButtonElement
        ).disabled,
      ).toBe(true);
      view.unmount();
      render(<TaskWizardPage />);
      await screen.findByText(
        "启动结果尚未确认，请先检查任务列表，避免重复创建。",
      );
      fireEvent.click(
        screen.getByRole("checkbox", {
          name: "我已核对以上业务画像、搜索条件、账号与运行设置",
        }),
      );
      fireEvent.click(screen.getByRole("button", { name: "确认并启动" }));
      expect(context.service.startTask).toHaveBeenCalledOnce();
    },
  );

  it("records a pending request before navigation so a late network failure cannot lose the duplicate-start lock", async () => {
    seed();
    context.route = parseRoute("#/tasks/new?step=confirm");
    let reject!: (reason: unknown) => void;
    context.service.startTask = vi.fn(
      () =>
        new Promise<TaskRun>((_resolve, fail) => {
          reject = fail;
        }),
    );
    const view = render(<TaskWizardPage />);
    fireEvent.click(await confirmReady());
    await waitFor(() =>
      expect(context.service.startTask).toHaveBeenCalledOnce(),
    );
    view.unmount();
    await act(async () =>
      reject(new ServiceError("NETWORK_ERROR", "离开后返回的网络错误")),
    );
    render(<TaskWizardPage />);
    await screen.findByText(
      "启动结果尚未确认，请先检查任务列表，避免重复创建。",
    );
    fireEvent.click(
      screen.getByRole("checkbox", {
        name: "我已核对以上业务画像、搜索条件、账号与运行设置",
      }),
    );
    fireEvent.click(screen.getByRole("button", { name: "确认并启动" }));
    expect(context.service.startTask).toHaveBeenCalledOnce();
  });
  it("retains an unknown start after clearing drafts and restoring the same task for the signed-in user", async () => {
    const saved = seed();
    const userId = context.session.userId!;
    context.route = parseRoute("#/tasks/new?step=confirm");
    context.service.startTask = vi
      .fn()
      .mockRejectedValue(new ServiceError("NETWORK_ERROR", "测试启动结果未知"));
    const view = render(<TaskWizardPage />);
    fireEvent.click(await confirmReady());
    await screen.findByText(
      "启动结果尚未确认，请先检查任务列表，避免重复创建。",
    );
    view.unmount();
    act(() => clearLocalDrafts());
    context = { ...context, session: { authenticated: true, userId } };
    const restored = renderHook(() => useTaskDraft(userId));
    act(() => restored.result.current[1](saved));
    restored.unmount();
    render(<TaskWizardPage />);
    await screen.findByText(
      "启动结果尚未确认，请先检查任务列表，避免重复创建。",
    );
    fireEvent.click(
      screen.getByRole("checkbox", {
        name: "我已核对以上业务画像、搜索条件、账号与运行设置",
      }),
    );
    expect(
      (screen.getByRole("button", { name: "确认并启动" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    expect(context.service.startTask).toHaveBeenCalledOnce();
  });

  it("does not initiate a new write after leaving while the final capability recheck is pending", async () => {
    seed();
    context.route = parseRoute("#/tasks/new?step=confirm");
    const view = render(<TaskWizardPage />);
    const start = await confirmReady();
    let resolve!: (value: Profile[]) => void;
    vi.mocked(context.service.profiles).mockImplementationOnce(
      () =>
        new Promise<Profile[]>((done) => {
          resolve = done;
        }),
    );
    fireEvent.click(start);
    await waitFor(() =>
      expect(context.service.profiles).toHaveBeenCalledTimes(2),
    );
    view.unmount();
    await act(async () => resolve(profiles));
    expect(context.service.startTask).not.toHaveBeenCalled();
  });
});

describe("collection readiness copy", () => {
  const id = '11111111-1111-4111-8111-111111111111';
  const accountId = 'a'.repeat(24);
  const registered: PlatformConnection = {platform:'xhs',status:'CONNECTED',accountId,accountName:'已登录的小红书',capabilities:[],
    registration:{connectionId:id,deviceId:id,version:2,connectedAt:'2026-09-13T00:00:00Z',disconnectedAt:null}};
  const readyAccount: PlatformConnection = {...registered,foregroundBinding:{mode:'xhs-foreground-v1',platform:'XIAOHONGSHU',
    connectionId:id,deviceId:id,connectionVersion:2,accountPublicId:accountId}};

  it('reloads account bindings when entering platform selection after runtime preparation', async () => {
    seed({accounts:{}});
    vi.mocked(context.service.connections).mockResolvedValueOnce([registered]).mockResolvedValue([readyAccount]);
    const view = render(<TaskWizardPage />);
    await screen.findByRole('checkbox',{name:/^小红书/});
    await act(async()=>{});
    fireEvent.click(screen.getByRole('button',{name:'下一步：连接平台'}));
    followNavigation(view);
    await waitFor(()=>expect((screen.getByRole('option',{name:'已登录的小红书'}) as HTMLOptionElement).disabled).toBe(false));
    expect(currentDraft().accounts.xhs).toBeUndefined();
    expect(context.service.startTask).not.toHaveBeenCalled();
  });

  it('rechecks accounts as well as readiness without requiring another platform login', async () => {
    seed({accounts:{}});
    context.route = parseRoute('#/tasks/new?step=connect');
    vi.mocked(context.service.connections).mockResolvedValueOnce([registered]).mockResolvedValue([readyAccount]);
    render(<TaskWizardPage />);
    expect((await screen.findByRole('option',{name:'已登录的小红书（当前不可用）'}) as HTMLOptionElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole('button',{name:'重新检查'}));
    await waitFor(()=>expect((screen.getByRole('option',{name:'已登录的小红书'}) as HTMLOptionElement).disabled).toBe(false));
    expect(context.service.info).toHaveBeenCalledTimes(2);
    expect(context.service.startTask).not.toHaveBeenCalled();
  });

  it("does not diagnose an unbound device when collection capability is unavailable", async () => {
    seed();
    context.route = parseRoute("#/tasks/new?step=connect");
    vi.mocked(context.service.info).mockResolvedValue({version:'0.2.0',platform:'win32',serviceConfigured:true,deviceReady:false});
    render(<TaskWizardPage />);
    await screen.findByRole('heading', {name:'采集准备'});
    expect(screen.getByText('尚未就绪')).toBeTruthy();
    expect(screen.queryByText('待绑定或检查')).toBeNull();
    expect(screen.getByText('请检查所选平台的连接及服务状态；启动前会再次核对。')).toBeTruthy();
    vi.mocked(context.service.info).mockResolvedValue({version:'0.2.0',platform:'win32',serviceConfigured:true,deviceReady:true});
    fireEvent.click(screen.getByRole('button', {name:'重新检查'}));
    await screen.findByText('执行服务已就绪');
    expect(context.service.startTask).not.toHaveBeenCalled();
  });
});

describe("new original-start contract", () => {
  it("persists the exact configuration binding before dispatch and reconciles rather than restarting", async () => {
    const draft = seed();
    context.route = parseRoute("#/tasks/new?step=confirm");
    const start = vi.fn(
      async (
        _draft: TaskDraft,
        binding: import("../../src/renderer/domain/taskOperations").TaskStartBinding,
      ) => ({ ...binding, status: "UNKNOWN" as const }),
    );
    const reconcile = vi.fn(
      async (
        binding: import("../../src/renderer/domain/taskOperations").TaskStartLookup,
      ) => ({
        ...binding,
        status: "ACCEPTED" as const,
        run: {
          id: "actual-task",
          name: draft.name,
          mode: draft.mode,
          status: "PENDING",
          platforms: draft.platforms,
        },
      }),
    );
    context.service.taskOperations = {
      start,
      reconcileStart: reconcile,
    } as unknown as NonNullable<YikeService["taskOperations"]>;
    render(<TaskWizardPage />);
    await screen.findByText("执行服务已就绪");
    fireEvent.click(await confirmReady());
    await screen.findByRole("button", { name: "核对原启动结果" });
    await waitFor(() => expect(start).toHaveBeenCalledOnce());
    expect(context.service.startTask).not.toHaveBeenCalled();
    const [, binding] = start.mock.calls[0];
    expect(binding.configurationHash).toMatch(/^[a-f0-9]{64}$/);
    expect(binding.requestId).toBe(`task:${draft.id}:${draft.revision}`);
    fireEvent.click(screen.getByRole("button", { name: "核对原启动结果" }));
    await waitFor(() =>
      expect(context.navigate).toHaveBeenCalledWith("/collection"),
    );
    expect(reconcile).toHaveBeenCalledWith(binding);
    expect(start).toHaveBeenCalledOnce();
  });
  it("requires manual confirmation of a new revision only after a bound definitive rejection", async () => {
    const draft = seed();
    context.route = parseRoute("#/tasks/new?step=confirm");
    const start = vi.fn(
      async (
        _draft: TaskDraft,
        binding: import("../../src/renderer/domain/taskOperations").TaskStartBinding,
      ) => ({
        ...binding,
        status: "REJECTED" as const,
        confirmedNotStarted: true as const,
        message: "已核实未创建测试任务",
      }),
    );
    context.service.taskOperations = { start } as unknown as NonNullable<
      YikeService["taskOperations"]
    >;
    render(<TaskWizardPage />);
    await screen.findByText("执行服务已就绪");
    fireEvent.click(await confirmReady());
    await screen.findByText("已核实未创建测试任务");
    expect(currentDraft().revision).toBe(draft.revision + 1);
    expect(
      (screen.getByRole("button", { name: "确认并启动" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    fireEvent.click(await confirmReady());
    await waitFor(() => expect(start).toHaveBeenCalledTimes(2));
    expect(start.mock.calls[1][1].requestId).not.toBe(
      start.mock.calls[0][1].requestId,
    );
  });
  it("does not start when durable request recording fails", async () => {
    seed();
    context.route = parseRoute("#/tasks/new?step=confirm");
    const start = vi.fn();
    context.service.taskOperations = { start } as unknown as NonNullable<
      YikeService["taskOperations"]
    >;
    render(<TaskWizardPage />);
    await screen.findByText("执行服务已就绪");
    const button = await confirmReady();
    const original = Storage.prototype.setItem;
    const spy = vi
      .spyOn(Storage.prototype, "setItem")
      .mockImplementation(function (this: Storage, key, value) {
        if (key.startsWith("yike.ui.operation."))
          throw new Error("test unavailable storage");
        return original.call(this, key, value);
      });
    fireEvent.click(button);
    await screen.findByText(/操作确认记录暂时无法可靠保存/);
    expect(start).not.toHaveBeenCalled();
    expect(context.service.startTask).not.toHaveBeenCalled();
    spy.mockRestore();
  });
});

describe("template ancestry start guards", () => {
  it("shows the original ancestor request and blocks starting a descendant draft", async () => {
    seed({ templateSourceDraftIds: ["ancestor-original"] });
    context.route = parseRoute("#/tasks/new?step=confirm");
    localStorage.setItem(
      `yike.ui.operation.v1.unknown-task-starts.${context.session.userId}`,
      JSON.stringify({ "ancestor-original": "task:ancestor-original:1" }),
    );
    render(<TaskWizardPage />);
    await screen.findByText("执行服务已就绪");
    expect(screen.queryByText("task:ancestor-original:1")).toBeNull();
    const start = screen.getByRole("button", {
      name: "确认并启动",
    }) as HTMLButtonElement;
    expect(start.disabled).toBe(true);
    fireEvent.click(start);
    expect(context.service.startTask).not.toHaveBeenCalled();
  });
  it("rechecks ancestor locks after live preflight even without a storage event", async () => {
    seed({ templateSourceDraftIds: ["ancestor-original"] });
    context.route = parseRoute("#/tasks/new?step=confirm");
    render(<TaskWizardPage />);
    await screen.findByText("执行服务已就绪");
    const button = await confirmReady();
    let resolve!: (value: unknown) => void;
    context.service.info = vi.fn(
      () =>
        new Promise((done) => {
          resolve = done;
        }),
    ) as never;
    fireEvent.click(button);
    await waitFor(() => expect(resolve).toBeTypeOf("function"));
    localStorage.setItem(
      `yike.ui.operation.v1.unknown-task-starts.${context.session.userId}`,
      JSON.stringify({ "ancestor-original": "task:ancestor-original:1" }),
    );
    await act(async () =>
      resolve({
        version: "test",
        platform: "test",
        serviceConfigured: true,
        deviceReady: true,
      }),
    );
    await screen.findByText("该任务已有启动请求待确认，当前不会重复创建。");
    expect(context.service.startTask).not.toHaveBeenCalled();
  });
});
