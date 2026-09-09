// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import {
  TaskWizardPage,
  matchesCreatedTask,
} from "../../src/renderer/pages/TaskWizard";
import { clearLocalDrafts } from "../../src/renderer/app/hooks";
import {
  newTaskDraft,
  EMPTY_PROFILE,
  type TaskDraft,
  type TaskRun,
} from "../../src/renderer/domain/models";
import { makeTerm } from "../../src/renderer/domain/task";
import { parseRoute } from "../../src/renderer/domain/routes";
import type { YikeService } from "../../src/renderer/services/contracts";
import type { AppContextValue } from "../../src/renderer/app/context";

let context: AppContextValue;
let draft: TaskDraft;
vi.mock("../../src/renderer/app/context", () => ({ useApp: () => context }));
beforeEach(() => {
  clearLocalDrafts();
  sessionStorage.clear();
  draft = {
    ...newTaskDraft(),
    name: "启动响应契约测试",
    profileId: "profile-test",
    profileVersion: 1,
    terms: [makeTerm("公开需求")],
    platforms: ["xhs"],
    accounts: { xhs: "test-account" },
  };
  context = {
    service: {
      profiles: vi
        .fn()
        .mockResolvedValue([
          {
            id: "profile-test",
            version: 1,
            status: "CONFIRMED",
            description: "测试",
            fields: { ...EMPTY_PROFILE, service: "测试服务" },
          },
        ]),
      connections: vi
        .fn()
        .mockResolvedValue([
          {
            platform: "xhs",
            status: "CONNECTED",
            accountId: "test-account",
            capabilities: ["read", "search"],
          },
        ]),
      info: vi.fn().mockResolvedValue({ deviceReady: true }),
      startTask: vi.fn(),
      suggest: vi.fn(),
    } as unknown as YikeService,
    session: { authenticated: true, userId: crypto.randomUUID() },
    sessionReady: true,
    route: parseRoute("#/tasks/new?step=confirm"),
    navigate: vi.fn(),
    notify: vi.fn(),
    refreshSession: vi.fn(),
  };
  sessionStorage.setItem(
    "yike.ui.draft.v1.task." + context.session.userId,
    JSON.stringify(draft),
  );
  sessionStorage.setItem(
    "yike.ui.draft.v1.task-library." + context.session.userId,
    JSON.stringify([draft]),
  );
});
afterEach(() => {
  cleanup();
  clearLocalDrafts();
});
async function submit() {
  fireEvent.click(
    screen.getByRole("checkbox", {
      name: "我已核对以上画像版本、搜索条件、账号与运行设置",
    }),
  );
  const button = screen.getByRole("button", {
    name: "确认并启动",
  }) as HTMLButtonElement;
  await waitFor(() => expect(button.disabled).toBe(false));
  fireEvent.click(button);
}
const validRun = (): TaskRun => ({
  id: "created-test-run",
  name: draft.name,
  mode: draft.mode,
  status: "PENDING",
  platforms: draft.platforms,
});

describe("task start result boundary", () => {
  it.each([
    undefined,
    null,
    {},
    { id: "wrong", mode: "monitor" },
    { id: "wrong", status: "SUCCESS" },
  ])(
    "keeps original request unknown after malformed result %j",
    async (result) => {
      context.service.startTask = vi.fn().mockResolvedValue(result);
      const view = render(<TaskWizardPage />);
      await submit();
      await screen.findByText(
        "任务返回结果与本次配置不一致，创建结果尚未确认。请核对原请求，勿重新提交。",
      );
      expect(context.navigate).not.toHaveBeenCalled();
      expect(context.notify).not.toHaveBeenCalled();
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
      fireEvent.click(screen.getByRole("button", { name: "确认并启动" }));
      expect(context.service.startTask).toHaveBeenCalledOnce();
    },
  );
  it("rejects a well-shaped run for another platform or profile", () => {
    expect(
      matchesCreatedTask({ ...validRun(), platforms: ["douyin"] }, draft),
    ).toBe(false);
    expect(
      matchesCreatedTask(
        { ...validRun(), profileId: "another-profile" },
        draft,
      ),
    ).toBe(false);
    expect(
      matchesCreatedTask({ ...validRun(), profileVersion: 99 }, draft),
    ).toBe(false);
    expect(
      matchesCreatedTask({ ...validRun(), name: "another-task" }, draft),
    ).toBe(false);
  });
  it("accepts a matching server task only after a nonempty identifier and state", async () => {
    context.service.startTask = vi.fn().mockResolvedValue(validRun());
    render(<TaskWizardPage />);
    await submit();
    await waitFor(() =>
      expect(context.navigate).toHaveBeenCalledWith("/collection"),
    );
    expect(context.notify).toHaveBeenCalledWith(
      "任务已创建，运行状态以任务详情为准。",
      "success",
    );
    expect(
      screen.queryByText("启动结果尚未确认，请先检查任务列表，避免重复创建。"),
    ).toBeNull();
  });
});
