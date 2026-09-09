// @vitest-environment jsdom
import { StrictMode, useEffect } from "react";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ResearchDraftHandoff } from "../../src/renderer/pages/opportunities/ResearchDraftHandoff";
import { clearLocalDrafts } from "../../src/renderer/app/hooks";
import { useTaskDraft, useTaskLibrary } from "../../src/renderer/app/taskDraft";
import { newTaskDraft, type TaskDraft } from "../../src/renderer/domain/models";
import type { AppContextValue } from "../../src/renderer/app/context";
import type { YikeService } from "../../src/renderer/services/contracts";
import { parseRoute } from "../../src/renderer/domain/routes";
import {
  binding,
  collection,
  researchProfile,
  researchRow,
  similar,
} from "./r4-opportunity-research-fixtures";
let context: AppContextValue;
let observed: { draft: TaskDraft; library: TaskDraft[] };
vi.mock("../../src/renderer/app/context", () => ({ useApp: () => context }));
function Seed({ draft }: { draft: TaskDraft }) {
  const [, setDraft] = useTaskDraft(
    binding.userId,
    "once",
    context.session.accountScope,
  );
  useEffect(() => {
    setDraft(draft);
  }, []);
  return null;
}
function Probe() {
  const [draft] = useTaskDraft(
    binding.userId,
    "once",
    context.session.accountScope,
  );
  const [library] = useTaskLibrary(
    binding.userId,
    context.session.accountScope,
  );
  observed = { draft, library };
  return null;
}
beforeEach(() => {
  clearLocalDrafts();
  sessionStorage.clear();
  context = {
    session: {
      authenticated: true,
      userId: binding.userId,
      accountScope: binding.accountScope,
    },
    route: parseRoute("#/opportunities/test-opportunity"),
    navigate: vi.fn(),
    notify: vi.fn(),
    refreshSession: vi.fn(),
    service: {
      opportunityResearch: {
        list: vi.fn().mockResolvedValue(collection),
        similar: vi.fn(async (_binding, requestId) => ({
          ...structuredClone(similar),
          requestId,
        })),
      },
      profiles: vi.fn().mockResolvedValue([researchProfile]),
      opportunity: vi.fn().mockResolvedValue(researchRow),
    } as unknown as YikeService,
  };
});
afterEach(() => {
  cleanup();
  clearLocalDrafts();
});
async function prepare() {
  await screen.findByDisplayValue(researchProfile.description);
  fireEvent.click(screen.getByRole("checkbox", { name: "公开网站" }));
  fireEvent.change(screen.getByRole("spinbutton", { name: "单次搜贝上限" }), {
    target: { value: "50" },
  });
  fireEvent.click(screen.getByRole("button", { name: "创建任务草稿" }));
}
describe("R4 local task handoff", () => {
  it("stores the local task under its verified workspace without exposing it in another workspace", async () => {
    const accountScope = { id: "test-space-a", version: 1 };
    context.session = { ...context.session, accountScope };
    context.service.opportunityResearch!.list = vi
      .fn()
      .mockResolvedValue({ ...collection, accountScope });
    context.service.opportunityResearch!.similar = vi.fn(
      async (_binding, requestId) => ({
        ...similar,
        requestId,
        binding: { ...binding, accountScope },
      }),
    );
    const ui = render(
      <>
        <Probe />
        <ResearchDraftHandoff opportunity={researchRow} onClose={vi.fn()} />
      </>,
    );
    await prepare();
    await waitFor(() => expect(context.navigate).toHaveBeenCalledOnce());
    const createdId = observed.draft.id;
    expect(observed.draft.research?.provenance?.accountScope).toEqual(
      accountScope,
    );
    context.session = {
      ...context.session,
      accountScope: { id: "test-space-b", version: 1 },
    };
    ui.rerender(<Probe />);
    expect(observed.draft.id).not.toBe(createdId);
    expect(observed.library).toEqual([]);
    context.session = { ...context.session, accountScope };
    ui.rerender(<Probe />);
    expect(observed.draft.id).toBe(createdId);
    expect(observed.library).toHaveLength(1);
  });
  it("creates one deterministic local task under StrictMode without any execution API", async () => {
    render(
      <StrictMode>
        <Probe />
        <ResearchDraftHandoff opportunity={researchRow} onClose={vi.fn()} />
      </StrictMode>,
    );
    await prepare();
    await waitFor(() =>
      expect(context.navigate).toHaveBeenCalledWith(
        "/tasks/new?mode=once&step=conditions",
      ),
    );
    expect(observed.library).toHaveLength(1);
    expect(observed.draft.id).toBe(observed.library[0].id);
    expect(observed.draft.platforms).toEqual(["web"]);
    expect(observed.draft.research?.maxSoubei).toBe(50);
    expect(observed.draft.research?.provenance).toMatchObject({
      opportunityId: researchRow.id,
      evidenceVersion: "v2",
    });
  });
  it("keeps an existing unsaved task and requires explicit switch confirmation", async () => {
    const old = {
      ...newTaskDraft(),
      id: "old-task",
      name: "TEST 未保存原任务",
      terms: [
        {
          id: "human",
          value: "TEST 人工搜索词",
          origin: "manual" as const,
          edited: true,
        },
      ],
    };
    render(
      <>
        <Seed draft={old} />
        <Probe />
        <ResearchDraftHandoff opportunity={researchRow} onClose={vi.fn()} />
      </>,
    );
    await prepare();
    await screen.findByRole("dialog", { name: "切换到相似研究草稿？" });
    expect(context.navigate).not.toHaveBeenCalled();
    expect(observed.draft.id).toBe("old-task");
    fireEvent.click(screen.getByRole("button", { name: "保留旧草稿并继续" }));
    await waitFor(() => expect(context.navigate).toHaveBeenCalledOnce());
    expect(observed.library.find((d) => d.id === "old-task")?.terms).toEqual(
      old.terms,
    );
    expect(observed.library).toHaveLength(2);
    expect(observed.draft.id).not.toBe("old-task");
  });
  it("cancels switching without replacing the current task", async () => {
    const old = { ...newTaskDraft(), id: "old-task", name: "TEST 原任务" };
    render(
      <>
        <Seed draft={old} />
        <Probe />
        <ResearchDraftHandoff opportunity={researchRow} onClose={vi.fn()} />
      </>,
    );
    await prepare();
    await screen.findByRole("dialog", { name: "切换到相似研究草稿？" });
    fireEvent.click(screen.getByRole("button", { name: "取消" }));
    expect(observed.draft.id).toBe("old-task");
    expect(observed.library).toEqual([]);
    expect(context.navigate).not.toHaveBeenCalled();
  });
});
