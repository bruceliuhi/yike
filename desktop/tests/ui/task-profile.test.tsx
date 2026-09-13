// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import type { AppContextValue } from "../../src/renderer/app/context";
import {
  EMPTY_PROFILE,
  type Profile,
  type TaskRun,
} from "../../src/renderer/domain/models";
import {
  compareTaskProfile,
  parseTaskProfiles,
} from "../../src/renderer/domain/taskProfile";
import { mapProfile } from "../../src/renderer/services/client";
import type { YikeService } from "../../src/renderer/services/contracts";
import { parseRoute } from "../../src/renderer/domain/routes";
import { TaskProfileStatus } from "../../src/renderer/pages/tasks/TaskProfileStatus";
import { TasksPage } from "../../src/renderer/pages/Tasks";
import { clearLocalDrafts } from "../../src/renderer/app/hooks";

let context: AppContextValue;
vi.mock("../../src/renderer/app/context", () => ({ useApp: () => context }));
const run: TaskRun = {
  id: "TEST-monitor",
  name: "TEST历史任务",
  mode: "monitor",
  status: "PAUSED",
  platforms: ["web"],
  profileId: "TEST-version-1",
  profileVersion: 1,
};
function profile(
  id: string,
  version: number,
  status: Profile["status"],
  entity: string | undefined = "TEST-business-a",
): Profile {
  return {
    id,
    version,
    status,
    ...(entity ? { profileEntityId: entity } : {}),
    fields: { ...EMPTY_PROFILE },
    description: "TEST业务说明",
  };
}
const history = () => [
  profile("TEST-version-1", 1, "REVOKED"),
  profile("TEST-version-2", 2, "CONFIRMED"),
];
beforeEach(() => {
  clearLocalDrafts();
  sessionStorage.clear();
  localStorage.clear();
  context = {
    service: {
      profiles: vi.fn().mockResolvedValue(history()),
      tasks: vi.fn().mockResolvedValue([run]),
      taskAction: vi.fn(),
      startTask: vi.fn(),
      confirmProfile: vi.fn(),
      saveProfile: vi.fn(),
    } as unknown as YikeService,
    session: {
      authenticated: true,
      userId: "TEST-user",
      accountScope: { id: "TEST-space-a", version: 1 },
    },
    sessionReady: true,
    route: parseRoute("#/monitors/TEST-monitor"),
    navigate: vi.fn(),
    notify: vi.fn(),
    refreshSession: vi.fn(),
  };
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("task profile entity lineage", () => {
  it("maps only the actual profile entity and preserves the version-row ID", () => {
    const mapped = mapProfile({
      profile_id: "entity",
      version_id: "version-row",
      version: 4,
      status: "CONFIRMED",
      payload: { description: "TEST" },
    });
    expect(mapped).toMatchObject({
      id: "version-row",
      profileEntityId: "entity",
      version: 4,
    });
    expect(
      mapProfile({
        version_id: "legacy-version-row",
        version: 3,
        status: "REVOKED",
      }).profileEntityId,
    ).toBeUndefined();
    for (const profile_id of [null, "", "   ", 42])
      expect(() =>
        mapProfile({
          profile_id,
          version_id: "version-row",
          version: 4,
          status: "CONFIRMED",
        }),
      ).toThrow(/响应不完整/);
  });
  it("ignores other businesses even when their confirmed version number is much higher", () => {
    const profiles = [
      profile(run.profileId!, 1, "CONFIRMED"),
      profile("other-version", 90, "CONFIRMED", "OTHER-business"),
    ];
    expect(compareTaskProfile(run, parseTaskProfiles(profiles)).status).toBe(
      "CURRENT",
    );
    expect(
      compareTaskProfile(run, parseTaskProfiles([...history(), profiles[1]])),
    ).toMatchObject({ status: "HISTORICAL", current: { version: 2 } });
  });
  it("never infers an entity from the only confirmed row or the same description", () => {
    const unlinked = history().map(({ profileEntityId: _entity, ...p }) => p);
    expect(compareTaskProfile(run, parseTaskProfiles(unlinked)).status).toBe(
      "UNKNOWN",
    );
    expect(
      compareTaskProfile(run, parseTaskProfiles([history()[1]])),
    ).toMatchObject({ status: "UNKNOWN" });
  });
  it.each([
    [
      profile("TEST-version-1", 1, "REVOKED"),
      profile("new-a", 2, "CONFIRMED"),
      profile("new-b", 3, "CONFIRMED"),
    ],
    [
      profile("TEST-version-1", 1, "REVOKED"),
      profile("other-same-number", 1, "CONFIRMED"),
    ],
    [profile("TEST-version-1", 1, "DRAFT"), profile("next", 2, "CONFIRMED")],
    [profile("TEST-version-1", 9, "REVOKED"), profile("next", 10, "CONFIRMED")],
  ])(
    "treats ambiguous or inconsistent version relations as unknown",
    (...profiles) => {
      expect(compareTaskProfile(run, parseTaskProfiles(profiles)).status).toBe(
        "UNKNOWN",
      );
    },
  );
  it("does not use another entity's confirmation when this one has no confirmed version", () => {
    expect(
      compareTaskProfile(
        run,
        parseTaskProfiles([
          history()[0],
          profile("other", 50, "CONFIRMED", "other-business"),
        ]),
      ),
    ).toMatchObject({ status: "NO_CONFIRMED" });
  });
  it.each([
    {},
    [{ id: "v", version: "1", status: "CONFIRMED" }],
    [{ id: "v", version: 1, status: "CONFIRMED", profileEntityId: 3 }],
  ])(
    "rejects malformed responses instead of reading them as an empty/current list",
    (value) => {
      expect(() => parseTaskProfiles(value)).toThrow(/响应不完整/);
    },
  );
});

describe("P09 profile comparison interaction", () => {
  it("shows the live lineage and lets users keep history or go to the profile without mutation", async () => {
    const snapshot = structuredClone(run);
    render(<TaskProfileStatus run={run} />);
    await screen.findByText("业务画像已有更新：任务仍使用原业务画像。");
    fireEvent.click(screen.getByRole("button", { name: "保持历史" }));
    expect(
      screen.getByText("已知悉保留历史：任务仍使用原业务画像。"),
    ).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "去更新" }));
    expect(context.navigate).toHaveBeenCalledWith("/profile");
    expect(run).toEqual(snapshot);
    for (const name of [
      "taskAction",
      "startTask",
      "confirmProfile",
      "saveProfile",
    ] as const)
      expect(context.service[name]).not.toHaveBeenCalled();
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });
  it("shows a new warning after a later version even after keeping the earlier history", async () => {
    render(<TaskProfileStatus run={run} />);
    await screen.findByText(/业务画像已有更新/);
    fireEvent.click(screen.getByRole("button", { name: "保持历史" }));
    context.service.profiles = vi
      .fn()
      .mockResolvedValue([
        history()[0],
        profile("TEST-version-3", 3, "CONFIRMED"),
      ]);
    fireEvent.click(screen.getByRole("button", { name: "重新核对" }));
    await screen.findByText("业务画像已有更新：任务仍使用原业务画像。");
    expect(screen.getByRole("button", { name: "保持历史" })).toBeTruthy();
    expect(screen.queryByText(/已知悉保留历史/)).toBeNull();
    context.service.profiles = vi.fn().mockResolvedValue(history());
    fireEvent.click(screen.getByRole("button", { name: "重新核对" }));
    await screen.findByText("业务画像已有更新：任务仍使用原业务画像。");
    expect(screen.queryByText(/已知悉保留历史/)).toBeNull();
  });
  it("does not present a failed refresh as agreement with the current profile", async () => {
    context.service.profiles = vi
      .fn()
      .mockResolvedValue([profile(run.profileId!, 1, "CONFIRMED")]);
    render(<TaskProfileStatus run={run} />);
    await screen.findByText(/任务使用的业务画像与当前已确认画像一致/);
    context.service.profiles = vi
      .fn()
      .mockRejectedValue(new Error("TEST读取失败"));
    fireEvent.click(screen.getByRole("button", { name: "重新核对" }));
    await screen.findByText(/当前画像待核对：TEST读取失败/);
    expect(screen.queryByText(/画像一致/)).toBeNull();
    expect(screen.queryByRole("button", { name: "保持历史" })).toBeNull();
  });
  it("times out a hung profile read and ignores its late response", async () => {
    vi.useFakeTimers();
    let finish!: (p: Profile[]) => void;
    context.service.profiles = vi.fn(
      () =>
        new Promise<Profile[]>((resolve) => {
          finish = resolve;
        }),
    );
    render(<TaskProfileStatus run={run} />);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30001);
    });
    expect(screen.getByText(/画像读取超时/)).toBeTruthy();
    await act(async () => finish(history()));
    expect(screen.queryByText(/业务画像已有更新/)).toBeNull();
  });
  it("drops old-space reads and cannot restore an old acknowledgement on an A-B-A switch", async () => {
    const view = render(<TaskProfileStatus run={run} />);
    await screen.findByText(/业务画像已有更新/);
    fireEvent.click(screen.getByRole("button", { name: "保持历史" }));
    let finish!: (p: Profile[]) => void;
    context.service.profiles = vi.fn(
      () =>
        new Promise<Profile[]>((resolve) => {
          finish = resolve;
        }),
    );
    fireEvent.click(screen.getByRole("button", { name: "重新核对" }));
    await waitFor(() =>
      expect(context.service.profiles).toHaveBeenCalledOnce(),
    );
    const oldFinish = finish;
    context = {
      ...context,
      session: {
        ...context.session,
        accountScope: { id: "TEST-space-b", version: 1 },
      },
    };
    context.service.profiles = vi.fn().mockResolvedValue([]);
    view.rerender(<TaskProfileStatus run={run} />);
    await screen.findByText(/未找到与任务绑定一致的画像版本/);
    await act(async () => oldFinish(history()));
    expect(screen.queryByText(/已知悉保留历史/)).toBeNull();
    expect(screen.queryByText(/业务画像已有更新/)).toBeNull();
    context = {
      ...context,
      session: {
        ...context.session,
        accountScope: { id: "TEST-space-a", version: 1 },
      },
    };
    context.service.profiles = vi.fn().mockResolvedValue(history());
    view.rerender(<TaskProfileStatus run={run} />);
    await screen.findByText(/业务画像已有更新/);
    expect(screen.getByRole("button", { name: "保持历史" })).toBeTruthy();
    expect(screen.queryByText(/已知悉保留历史/)).toBeNull();
  });
  it("never labels a legacy unlinked profile as current", async () => {
    context.service.profiles = vi
      .fn()
      .mockResolvedValue(
        [profile(run.profileId!, 1, "CONFIRMED", undefined)].map(
          ({ profileEntityId: _id, ...p }) => p,
        ),
      );
    render(<TaskProfileStatus run={run} />);
    await screen.findByText(/画像缺少业务实体关联/);
    expect(screen.queryByText(/画像一致/)).toBeNull();
  });
  it("keeps the warning available in task configuration and does not call a task mutation", async () => {
    render(<TasksPage />);
    await screen.findByText(/业务画像已有更新/);
    fireEvent.click(screen.getByRole("tab", { name: "任务配置" }));
    expect(
      screen.getByRole("region", { name: "任务画像版本核对" }),
    ).toBeTruthy();
    expect(screen.queryByText("v1")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "保持历史" }));
    expect(context.service.taskAction).not.toHaveBeenCalled();
    expect(context.service.tasks).toHaveBeenCalledOnce();
  });
});
