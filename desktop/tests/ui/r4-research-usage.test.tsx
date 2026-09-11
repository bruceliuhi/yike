// @vitest-environment jsdom
import { webcrypto } from "node:crypto";
import {
  act,
  cleanup,
  fireEvent,
  render,
  renderHook,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { clearLocalDrafts } from "../../src/renderer/app/hooks";
import { taskDraftOwner, useTaskDraft } from "../../src/renderer/app/taskDraft";
import { createDraftFromResearch } from "../../src/renderer/app/researchHandoff";
import { operationLedgerKey } from "../../src/renderer/app/operationLedger";
import type { AppContextValue } from "../../src/renderer/app/context";
import {
  newTaskDraft,
  EMPTY_PROFILE,
  type TaskDraft,
  type Profile,
} from "../../src/renderer/domain/models";
import {
  defaultResearchSettings,
  parseUsageQuote,
  usageQuoteRequest,
  type UsageQuote,
  type UsageQuoteRequest,
} from "../../src/renderer/domain/researchUsage";
import {
  configurationHash,
  parseStartReceipt,
  readStartEntry,
  startEntry,
  type TaskStartBinding,
} from "../../src/renderer/domain/taskOperations";
import { makeTerm } from "../../src/renderer/domain/task";
import { parseRoute } from "../../src/renderer/domain/routes";
import { TaskWizardPage } from "../../src/renderer/pages/TaskWizard";
import { useUsageQuote } from "../../src/renderer/pages/tasks/useUsageQuote";
import type { YikeService } from "../../src/renderer/services/contracts";
import { planFor } from "./r4-coverage-plan-fixtures";

let context: AppContextValue, draft: TaskDraft;
vi.mock("../../src/renderer/app/context", () => ({ useApp: () => context }));
const quoteFor = (input: UsageQuoteRequest): UsageQuote => ({
  ...input,
  quoteId: "TEST-quote",
  ruleVersion: "TEST-rule-v1",
  authorizationToken: "TEST-opaque",
  estimatedSoubei: 12,
  generatedAt: new Date(Date.now() - 1000).toISOString(),
  expiresAt: new Date(Date.now() + 60000).toISOString(),
  basis: "TEST 确认范围，仅用于隔离测试",
});
beforeEach(() => {
  vi.stubGlobal("crypto", webcrypto);
  sessionStorage.clear();
  localStorage.clear();
  const userId = crypto.randomUUID();
  draft = {
    ...newTaskDraft(),
    name: "TEST 用量控制",
    profileId: "TEST-profile",
    profileVersion: 1,
    terms: [makeTerm("公开询价")],
    // This fixture tests the historical usage/start receipt protocol, not the
    // public V2EX collector (which deliberately cannot execute research).
    platforms: ["bilibili"],
    accounts: {bilibili: "TEST-account"},
    research: { ...defaultResearchSettings(), maxSoubei: 50 },
  };
  context = {
    service: {
      profiles: vi.fn().mockResolvedValue([
        {
          id: draft.profileId,
          version: 1,
          status: "CONFIRMED",
          description: "TEST",
          fields: { ...EMPTY_PROFILE, service: "TEST 服务" },
        },
      ]),
      connections: vi.fn().mockResolvedValue([
        {
          platform: "bilibili",
          accountId: "TEST-account",
          status: "CONNECTED",
          capabilities: ["search", "read"],
        },
      ]),
      info: vi.fn().mockResolvedValue({ deviceReady: true }),
      suggest: vi.fn(),
      startTask: vi.fn(),
      researchUsage: { quote: vi.fn(async (input) => quoteFor(input)) },
      taskOperations: {
        researchContractVersion: 1,
        start: vi.fn(async (snapshot, binding) => ({
          ...binding,
          status: "ACCEPTED",
          run: {
            id: "TEST-run",
            name: snapshot.name,
            mode: snapshot.mode,
            status: "PENDING",
            platforms: snapshot.platforms,
          },
        })),
        reconcileStart: vi.fn(),
      },
    } as unknown as YikeService,
    session: {
      authenticated: true,
      userId,
      accountScope: { id: "TEST-space", version: 1 },
    },
    sessionReady: true,
    route: parseRoute("#/tasks/new?step=confirm"),
    navigate: vi.fn(),
    notify: vi.fn(),
    refreshSession: vi.fn(),
  };
  sessionStorage.setItem(
    "yike.ui.draft.v1.task." +
      taskDraftOwner(userId, context.session.accountScope),
    JSON.stringify(draft),
  );
});
afterEach(() => {
  cleanup();
  clearLocalDrafts();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});
async function estimateAndConfirm() {
  fireEvent.click(screen.getByRole("button", { name: "重新估算" }));
  await screen.findByText(/预计 12 搜贝，最多 50 搜贝/);
  fireEvent.click(screen.getByRole("checkbox", { name: /我已核对以上/ }));
  await waitFor(() =>
    expect(
      (screen.getByRole("button", { name: "确认并启动" }) as HTMLButtonElement)
        .disabled,
    ).toBe(false),
  );
}
describe("R4 usage bindings and recovered start protection", () => {
  it("hashes demand types, cap, resource limits and provenance as confirmed configuration", async () => {
    const initial = await configurationHash(draft);
    for (const research of [
      { ...draft.research!, maxSoubei: 51 },
      { ...draft.research!, demandTypes: ["CHANGE" as const] },
      {
        ...draft.research!,
        limits: { ...draft.research!.limits, minutes: 16 },
      },
    ])
      expect(await configurationHash({ ...draft, research })).not.toBe(initial);
  });
  it.each([
    "accountScopeId",
    "accountScopeVersion",
    "configurationHash",
    "maxSoubei",
    "requestId",
  ])("rejects a quote with a wrong %s", async (key) => {
    const input = usageQuoteRequest(
      draft,
      context.session,
      await configurationHash(draft),
    );
    const quote = quoteFor(input);
    expect(() =>
      parseUsageQuote(
        {
          ...quote,
          [key]:
            typeof quote[key as keyof UsageQuote] === "number" ? 999 : "wrong",
        },
        input,
      ),
    ).toThrow();
  });
  it("rejects over-cap and expired quotes, never supplies a zero estimate for missing accounting", async () => {
    const input = usageQuoteRequest(
      draft,
      context.session,
      await configurationHash(draft),
    );
    expect(() =>
      parseUsageQuote({ ...quoteFor(input), estimatedSoubei: 51 }, input),
    ).toThrow(/超过/);
    expect(() =>
      parseUsageQuote(
        {
          ...quoteFor(input),
          expiresAt: new Date(Date.now() - 1).toISOString(),
        },
        input,
      ),
    ).toThrow(/过期/);
    expect(() =>
      usageQuoteRequest(
        draft,
        { ...context.session, accountScope: undefined },
        input.configurationHash,
      ),
    ).toThrow(/账户/);
  });
  it("preserves in-progress blank and invalid limits without erasing the task", () => {
    const { result } = renderHook(() =>
      useTaskDraft(
        context.session.userId,
        "once",
        context.session.accountScope,
      ),
    );
    act(() =>
      result.current[1]({
        ...draft,
        research: {
          ...draft.research!,
          maxSoubei: null,
          demandTypes: [],
          limits: { ...draft.research!.limits, minutes: 0 },
        },
      }),
    );
    expect(result.current[0].name).toBe(draft.name);
    expect(result.current[0].research?.maxSoubei).toBeNull();
    expect(result.current[0].research?.limits.minutes).toBe(0);
  });
  it("does not silently start a research draft through a legacy execution adapter", async () => {
    delete context.service.taskOperations;
    render(<TaskWizardPage />);
    fireEvent.click(screen.getByRole("checkbox", { name: /我已核对以上/ }));
    expect(
      (screen.getByRole("button", { name: "确认并启动" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    expect(context.service.startTask).not.toHaveBeenCalled();
  });
  it("starts once with the quoted cap and requires the corresponding reservation receipt", async () => {
    render(<TaskWizardPage />);
    await estimateAndConfirm();
    expect(context.service.taskOperations!.start).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "确认并启动" }));
    await waitFor(() =>
      expect(context.navigate).toHaveBeenCalledWith("/collection"),
    );
    const [snapshot, binding, quote] = vi.mocked(
      context.service.taskOperations!.start,
    ).mock.calls[0];
    expect(snapshot.research?.maxSoubei).toBe(50);
    expect(binding.usageReservation?.quoteId).toBe(quote!.quoteId);
    expect(context.service.startTask).not.toHaveBeenCalled();
  });
  it("does not dispatch an old-space start after delayed prerequisite checks", async () => {
    const view = render(<TaskWizardPage />);
    await estimateAndConfirm();
    let resolve!: (value: Profile[]) => void;
    context.service.profiles = vi.fn(
      () =>
        new Promise<Profile[]>((done) => {
          resolve = done;
        }),
    );
    fireEvent.click(screen.getByRole("button", { name: "确认并启动" }));
    await waitFor(() =>
      expect(context.service.profiles).toHaveBeenCalledOnce(),
    );
    const oldResolve = resolve;
    context = {
      ...context,
      session: {
        ...context.session,
        accountScope: { id: "TEST-other-space", version: 2 },
      },
    };
    view.rerender(<TaskWizardPage />);
    await act(async () => oldResolve([]));
    expect(context.service.taskOperations!.start).not.toHaveBeenCalled();
    expect(context.service.startTask).not.toHaveBeenCalled();
  });
  it("requires a rejected request to confirm the same usage reservation is absent", async () => {
    const input = usageQuoteRequest(
      draft,
      context.session,
      await configurationHash(draft),
    );
    const q = quoteFor(input);
    const binding: TaskStartBinding = {
      requestId: `task:${draft.id}:1`,
      draftId: draft.id,
      revision: 1,
      configurationHash: input.configurationHash,
      mode: "once",
      usageReservation: {
        quoteId: q.quoteId,
        ruleVersion: q.ruleVersion,
        maxSoubei: 50,
        accountScopeId: q.accountScopeId,
        accountScopeVersion: 1,
      },
    };
    const receipt = {
      ...binding,
      status: "REJECTED",
      confirmedNotStarted: true,
    };
    expect(() => parseStartReceipt(receipt, binding)).toThrow(/搜贝预留/);
    expect(() =>
      parseStartReceipt(
        {
          ...receipt,
          confirmedNoUsageReserved: true,
          usageReservation: undefined,
        },
        binding,
      ),
    ).toThrow(/搜贝上限/);
    expect(
      parseStartReceipt({ ...receipt, confirmedNoUsageReserved: true }, binding)
        .status,
    ).toBe("REJECTED");
    expect(
      readStartEntry(draft.id, startEntry(binding))?.usageReservation,
    ).toEqual(binding.usageReservation);
  });
  it("retains a durable unknown start when the receipt omits accounting, including after remount", async () => {
    context.service.taskOperations!.start = vi.fn(
      async (snapshot, binding) => ({
        ...binding,
        usageReservation: undefined,
        status: "ACCEPTED",
        run: {
          id: "TEST-run",
          name: snapshot.name,
          mode: snapshot.mode,
          status: "PENDING",
          platforms: snapshot.platforms,
        },
      }),
    );
    const view = render(<TaskWizardPage />);
    await estimateAndConfirm();
    fireEvent.click(screen.getByRole("button", { name: "确认并启动" }));
    await screen.findByText(/启动回执尚未确认原搜贝上限/);
    const entries = JSON.parse(
      localStorage.getItem(
        operationLedgerKey("unknown-task-starts", context.session.userId!),
      )!,
    );
    const binding = readStartEntry(draft.id, entries[draft.id])!;
    expect(binding.usageReservation?.maxSoubei).toBe(50);
    expect(context.navigate).not.toHaveBeenCalled();
    view.unmount();
    render(<TaskWizardPage />);
    expect(
      (screen.getByRole("button", { name: "确认并启动" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    expect(context.service.taskOperations!.start).toHaveBeenCalledTimes(1);
    const receipt = {
      ...binding,
      status: "ACCEPTED",
      run: {
        id: "TEST-run",
        name: draft.name,
        mode: "once",
        status: "PENDING",
        platforms: ["bilibili"],
      },
    };
    expect(() =>
      parseStartReceipt({ ...receipt, usageReservation: undefined }, binding),
    ).toThrow(/搜贝/);
    expect(parseStartReceipt(receipt, binding).status).toBe("ACCEPTED");
  });
  it("rejects a quote that arrives after an edit or a same-user space switch", async () => {
    let resolve!: (value: UsageQuote) => void;
    context.service.researchUsage!.quote = vi.fn(
      () =>
        new Promise<UsageQuote>((done) => {
          resolve = done;
        }),
    );
    const hook = renderHook(({ value }) => useUsageQuote(value), {
      initialProps: { value: draft },
    });
    act(() => {
      void hook.result.current.estimate();
    });
    await waitFor(() =>
      expect(context.service.researchUsage!.quote).toHaveBeenCalledOnce(),
    );
    const input = vi.mocked(context.service.researchUsage!.quote).mock
      .calls[0][0];
    context = {
      ...context,
      session: {
        ...context.session,
        accountScope: { id: "another-space", version: 2 },
      },
    };
    hook.rerender({ value: { ...draft, revision: 2 } });
    await act(async () => resolve(quoteFor(input)));
    expect(hook.result.current.quote).toBeNull();
    expect(hook.result.current.valid).toBe(false);
  });
  it("keeps terminal-run provenance and rejects estimation in another customer space", async () => {
    draft.research!.coverageProvenance = {
      ...planFor("NEW_DRAFT"),
      kind: "NEW_DRAFT",
      userId: context.session.userId!,
      accountScopeId: context.session.accountScope!.id,
      scopeVersion: context.session.accountScope!.version,
      scopeSummary: "TEST 原检查范围",
    };
    const hash = await configurationHash(draft);
    expect(usageQuoteRequest(draft, context.session, hash).draftId).toBe(
      draft.id,
    );
    const hook = renderHook(() =>
      useTaskDraft(
        context.session.userId,
        "once",
        context.session.accountScope,
      ),
    );
    act(() => hook.result.current[1](draft));
    hook.rerender();
    expect(hook.result.current[0].research?.coverageProvenance).toEqual(
      draft.research!.coverageProvenance,
    );
    expect(() =>
      usageQuoteRequest(
        draft,
        { ...context.session, accountScope: { id: "OTHER", version: 1 } },
        hash,
      ),
    ).toThrow("其他客户空间");
  });
  it("preserves similar-source provenance while requesting a fresh estimate", () => {
    const created = createDraftFromResearch({
      requestId: "request",
      draftId: "draft",
      suggestionId: "suggestion",
      binding: {
        userId: context.session.userId!,
        opportunityId: "opp",
        sourceUrl: "https://example.test/source",
        profileVersionId: "profile-v1",
        evidenceVersion: "e1",
        accountScope: context.session.accountScope!,
      },
      name: "TEST 相似研究",
      profileId: "profile",
      profileVersion: 1,
      keywords: ["询价"],
      exclusions: [],
      platforms: ["web"],
      originalScope: "原范围",
      additionalScope: "新增范围",
      limits: { sources: 80, minutes: 10, soubei: 50, stopAtAnyLimit: true },
      usage: { status: "UNKNOWN", reason: "待估算" },
    });
    expect(created.research?.provenance?.accountScope).toEqual(
      context.session.accountScope,
    );
    expect(created.research?.limits).toEqual({
      sources: 80,
      minutes: 10,
      modelCalls: 50,
    });
    expect(created.research?.provenance?.suggestionId).toBe("suggestion");
    expect(JSON.stringify(created)).not.toContain("authorizationToken");
  });
});
