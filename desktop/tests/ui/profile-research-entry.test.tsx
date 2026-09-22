// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { AppContextValue } from "../../src/renderer/app/context";
import { clearLocalDrafts } from "../../src/renderer/app/hooks";
import { taskDraftOwner } from "../../src/renderer/app/taskDraft";
import { newTaskDraft, type Profile, type TaskDraft } from "../../src/renderer/domain/models";
import { defaultResearchSettings } from "../../src/renderer/domain/researchUsage";
import { parseRoute } from "../../src/renderer/domain/routes";
import { ProfilePage } from "../../src/renderer/pages/Profile";
import { service as baseService } from "../../src/renderer/services/client";

let context: AppContextValue;
vi.mock("../../src/renderer/app/context", () => ({ useApp: () => context }));
const profile: Profile = {
  id: "confirmed-profile-version", profileEntityId: "business-entity", version: 3,
  status: "CONFIRMED", description: "业务画像", businessName: "软件服务",
  fields: { service: "软件定制", customer: "制造企业", regions: "上海", preference: "", exclusions: "招聘" },
};
const entryLabel = "用此画像新建研究";
const storageKey = (kind: "task" | "task-library", session = context.session) =>
  `yike.ui.draft.v1.${kind}.${taskDraftOwner(session.userId, session.accountScope)}`;
const storedDraft = () => JSON.parse(sessionStorage.getItem(storageKey("task")) || "null") as TaskDraft | null;
const storedLibrary = () => JSON.parse(sessionStorage.getItem(storageKey("task-library")) || "[]") as TaskDraft[];
function seed(draft: TaskDraft, library: TaskDraft[] = []) {
  sessionStorage.setItem(storageKey("task"), JSON.stringify(draft));
  sessionStorage.setItem(storageKey("task-library"), JSON.stringify(library));
}
function oldDraft(): TaskDraft {
  return {
    ...newTaskDraft("monitor"), name: "原来的人工任务", revision: 4,
    profileId: "other-profile-version", profileVersion: 2,
    research: { ...defaultResearchSettings(), maxSoubei: 77 },
    terms: [{ id: "manual-term", value: "人工搜索词", origin: "manual", edited: true }],
    templateSourceDraftIds: ["unknown-start-origin"],
  };
}
beforeEach(() => {
  clearLocalDrafts();
  context = {
    session: { authenticated: true, userId: crypto.randomUUID(), accountScope: { id: "customer-space", version: 1 } },
    route: parseRoute("#/profile"), navigate: vi.fn(), notify: vi.fn(), refreshSession: vi.fn(),
    service: {
      ...baseService, profiles: vi.fn().mockResolvedValue([profile]),
      confirmProfile: vi.fn().mockResolvedValue(profile), suggest: vi.fn(), startTask: vi.fn(),
      researchUsage: { quote: vi.fn() },
    },
  };
});
afterEach(() => { cleanup(); clearLocalDrafts(); sessionStorage.clear(); });
async function mountReady() {
  const view = render(<ProfilePage />);
  await screen.findByDisplayValue(profile.fields.service);
  return view;
}
async function openChoice() {
  await mountReady();
  fireEvent.click(screen.getByRole("button", { name: entryLabel }));
  return screen.findByRole("dialog", { name: "已有任务草稿" });
}

describe("确认画像后的研究入口", () => {
  it("使用当前选择的已确认版本创建新研究草稿，不自动生成、估算或启动", async () => {
    context.service.profiles = vi.fn().mockResolvedValue([{ ...profile, id: "another-version", version: 1 }, profile]);
    await mountReady();
    fireEvent.change(screen.getByLabelText("画像版本", { selector: "select" }), { target: { value: profile.id } });
    fireEvent.click(screen.getByRole("button", { name: entryLabel }));
    expect(storedDraft()).toMatchObject({ profileId: profile.id, profileVersion: 3, mode: "once", research: defaultResearchSettings() });
    expect(storedDraft()?.terms).toEqual([]);
    expect(context.navigate).toHaveBeenCalledWith("/tasks/new");
    expect(context.service.suggest).not.toHaveBeenCalled();
    expect(context.service.researchUsage?.quote).not.toHaveBeenCalled();
    expect(context.service.startTask).not.toHaveBeenCalled();
  });

  it("确认成功后明确提供下一步，点击前不创建任务或跳转", async () => {
    let confirmed = false;
    context.service.profiles = vi.fn(async (): Promise<Profile[]> => [{ ...profile, status: confirmed ? "CONFIRMED" : "DRAFT" }]);
    context.service.confirmProfile = vi.fn(async () => { confirmed = true; return profile; });
    await mountReady();
    expect(screen.queryByRole("button", { name: entryLabel })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "确认画像" }));
    const dialog = screen.getByRole("dialog");
    fireEvent.click(within(dialog).getByRole("checkbox"));
    fireEvent.click(within(dialog).getByRole("button", { name: "确认画像" }));
    await screen.findByRole("button", { name: entryLabel });
    expect(context.navigate).not.toHaveBeenCalled();
    expect(storedDraft()).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: entryLabel }));
    expect(storedDraft()?.profileId).toBe(profile.id);
  });

  it("修改已确认画像后须重新确认，不用旧版本悄悄进入研究", async () => {
    await mountReady();
    expect(screen.getByRole("button", { name: entryLabel })).toBeTruthy();
    fireEvent.change(screen.getByLabelText("服务地区", { selector: "input" }), { target: { value: "北京" } });
    expect(screen.queryByRole("button", { name: entryLabel })).toBeNull();
    expect(screen.getByRole("button", { name: "确认画像" })).toBeTruthy();
    expect(context.navigate).not.toHaveBeenCalled();
  });

  it("已有草稿先显示选择，取消不修改任何草稿", async () => {
    const old = oldDraft(); seed(old);
    const dialog = await openChoice();
    expect(within(dialog).getByText(old.name)).toBeTruthy();
    expect(storedDraft()).toEqual(old);
    expect(storedLibrary()).toEqual([]);
    expect(context.navigate).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole("button", { name: "取消" }));
    expect(storedDraft()).toEqual(old);
    expect(context.navigate).not.toHaveBeenCalled();
  });

  it("继续已有监控草稿保留画像、人工条件、额度、版本及待核对请求", async () => {
    const old = oldDraft(); seed(old);
    const dialog = await openChoice();
    fireEvent.click(within(dialog).getByRole("button", { name: "继续已有草稿" }));
    expect(storedDraft()).toEqual(old);
    expect(storedLibrary()).toEqual([]);
    expect(context.navigate).toHaveBeenCalledWith("/tasks/new?mode=monitor");
  });

  it("另开本画像任务前将最新原草稿完整保留到现有草稿库", async () => {
    const old = oldDraft();
    const unrelated = { ...newTaskDraft(), name: "其它已存草稿" };
    seed(old, [{ ...old, revision: 2, name: "旧保存版本" }, unrelated]);
    const dialog = await openChoice();
    fireEvent.click(within(dialog).getByRole("button", { name: "保留草稿并新建" }));
    expect(storedLibrary()).toEqual(expect.arrayContaining([old, unrelated]));
    expect(storedLibrary().filter(draft => draft.id === old.id)).toHaveLength(1);
    expect(storedDraft()?.id).not.toBe(old.id);
    expect(storedDraft()).toMatchObject({ profileId: profile.id, profileVersion: profile.version, terms: [], accounts: {}, research: defaultResearchSettings() });
    expect(storedDraft()?.templateSourceDraftIds).toBeUndefined();
    expect(context.navigate).toHaveBeenCalledWith("/tasks/new");
  });

  it("只改过额度的草稿也需选择，不被当作空白覆盖", async () => {
    const old = { ...newTaskDraft(), research: { ...defaultResearchSettings(), maxSoubei: 12 } };
    seed(old);
    await openChoice();
    expect(storedDraft()).toEqual(old);
    expect(context.navigate).not.toHaveBeenCalled();
  });

  it("草稿库已有同ID较新版本时不覆盖任一副本，提示先核对", async () => {
    const old = oldDraft();
    const newer = { ...old, revision: old.revision + 1, name: "较新草稿" };
    seed(old, [newer]);
    const dialog = await openChoice();
    fireEvent.click(within(dialog).getByRole("button", { name: "保留草稿并新建" }));
    expect(within(dialog).getByText("草稿列表中已有更新版本，请先在线索采集或监控任务中核对；当前草稿未改动。")).toBeTruthy();
    expect(storedDraft()).toEqual(old);
    expect(storedLibrary()).toEqual([newer]);
    expect(context.navigate).not.toHaveBeenCalled();
  });

  it("切换客户空间后不复用旧选择弹窗、旧画像或旧任务草稿", async () => {
    const old = oldDraft(); seed(old);
    const oldKey = storageKey("task");
    const view = await mountReady();
    fireEvent.click(screen.getByRole("button", { name: entryLabel }));
    await screen.findByRole("dialog", { name: "已有任务草稿" });
    context = { ...context, session: { ...context.session, accountScope: { id: "another-space", version: 2 } },
      service: { ...context.service, profiles: vi.fn().mockResolvedValue([]) } };
    view.rerender(<ProfilePage />);
    await waitFor(() => expect(screen.queryByText("正在加载…")).toBeNull());
    expect(screen.queryByRole("dialog", { name: "已有任务草稿" })).toBeNull();
    expect(screen.queryByRole("button", { name: entryLabel })).toBeNull();
    expect(storedDraft()).toBeNull();
    expect(JSON.parse(sessionStorage.getItem(oldKey)!)).toEqual(old);
    expect(context.navigate).not.toHaveBeenCalled();
  });

  it("旧账号迟到的画像确认不在新账号开启研究入口", async () => {
    let finish!: (result: Profile) => void;
    context.service.profiles = vi.fn().mockResolvedValue([{ ...profile, status: "DRAFT" }]);
    context.service.confirmProfile = vi.fn(() => new Promise<Profile>(resolve => { finish = resolve; }));
    const view = await mountReady();
    fireEvent.click(screen.getByRole("button", { name: "确认画像" }));
    const dialog = screen.getByRole("dialog");
    fireEvent.click(within(dialog).getByRole("checkbox"));
    fireEvent.click(within(dialog).getByRole("button", { name: "确认画像" }));
    await waitFor(() => expect(context.service.confirmProfile).toHaveBeenCalledWith(profile.id));
    context = { ...context, session: { authenticated: true, userId: "next-user" },
      service: { ...context.service, profiles: vi.fn().mockResolvedValue([]) } };
    view.rerender(<ProfilePage />);
    await act(async () => { finish(profile); });
    expect(screen.queryByRole("button", { name: entryLabel })).toBeNull();
    expect(storedDraft()).toBeNull();
    expect(context.navigate).not.toHaveBeenCalled();
  });
});
