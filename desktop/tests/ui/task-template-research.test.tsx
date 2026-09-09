// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { AppContextValue } from "../../src/renderer/app/context";
import { clearLocalDrafts } from "../../src/renderer/app/hooks";
import { taskDraftOwner, taskDraftSchema } from "../../src/renderer/app/taskDraft";
import { newTaskDraft, type TaskDraft } from "../../src/renderer/domain/models";
import { defaultResearchSettings } from "../../src/renderer/domain/researchUsage";
import { parseRoute } from "../../src/renderer/domain/routes";
import { TasksPage } from "../../src/renderer/pages/Tasks";
import {
  draftFromTemplate,
  localTemplateSchema,
  templateFromDraft,
} from "../../src/renderer/pages/tasks/localTemplates";
import type { YikeService } from "../../src/renderer/services/contracts";

let context: AppContextValue;
vi.mock("../../src/renderer/app/context", () => ({ useApp: () => context }));

function configuredDraft(): TaskDraft {
  return {
    ...newTaskDraft("monitor"),
    name: "TEST 自定义研究模板",
    profileId: "TEST-profile",
    profileVersion: 3,
    terms: [{ id: "term", value: "人工研究词", origin: "manual", edited: true }],
    exclusions: [{ id: "exclude", value: "招聘", origin: "manual", edited: true }],
    platforms: ["web"],
    savedAt: "2026-09-09T12:00:00Z",
    research: {
      ...defaultResearchSettings(),
      demandTypes: ["CHANGE"],
      maxSoubei: 23,
      limits: { sources: 17, minutes: 7, modelCalls: 4 },
    },
    executionLimits: { max_records: 37, max_runtime_seconds: 420 },
  };
}
const storedKey = (kind: string) =>
  `yike.ui.draft.v1.${kind}.${taskDraftOwner(context.session.userId, context.session.accountScope)}`;

beforeEach(() => {
  clearLocalDrafts();
  sessionStorage.clear();
  localStorage.clear();
  context = {
    service: {
      tasks: vi.fn().mockResolvedValue([]),
      startTask: vi.fn(),
      taskAction: vi.fn(),
    } as unknown as YikeService,
    session: {
      authenticated: true,
      userId: "TEST-template-user",
      accountScope: { id: "TEST-space", version: 2 },
    },
    sessionReady: true,
    route: parseRoute("#/collection"),
    navigate: vi.fn(),
    notify: vi.fn(),
    refreshSession: vi.fn(),
  };
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

it("round-trips manual demand, soubei, stop and execution limits into a new task", () => {
  const source = configuredDraft();
  const template = templateFromDraft(source, source.name);
  const child = draftFromTemplate(template);
  expect(template.conditions.research).toEqual(source.research);
  expect(child.research).toEqual(source.research);
  expect(child.executionLimits).toEqual(source.executionLimits);
  expect(child.id).not.toBe(source.id);
  expect(child.revision).toBe(1);
  expect(child.savedAt).toBeNull();
  expect(child.templateSourceDraftIds).toEqual([source.id]);
  expect(child.schedule).toEqual(source.schedule);
  expect(taskDraftSchema.safeParse(child).success).toBe(true);
  child.research!.limits.sources = 2;
  expect(template.conditions.research!.limits.sources).toBe(17);
});

it("preserves incomplete but valid local inputs rather than replacing them with defaults", () => {
  const source = configuredDraft();
  source.research = {
    ...source.research!,
    demandTypes: [],
    maxSoubei: null,
    limits: { sources: 0, minutes: -1, modelCalls: 1.5 },
  };
  source.executionLimits = { max_records: null, max_runtime_seconds: -1 };
  const child = draftFromTemplate(templateFromDraft(source, source.name));
  expect(child.research).toEqual(source.research);
  expect(child.executionLimits).toEqual(source.executionLimits);
  expect(taskDraftSchema.safeParse(child).success).toBe(true);
});

it("filters quote, request, authorization and original-run provenance at both template boundaries", () => {
  const source = configuredDraft();
  const tainted = {
    ...source,
    requestId: "TEST-old-start",
    quote: { authorizationToken: "TEST-not-authority" },
    research: {
      ...source.research,
      quote: { quoteId: "TEST-old-quote" },
      authorizationToken: "TEST-token",
      requestId: "TEST-old-research",
      provenance: { requestId: "TEST-old-similar", userId: "TEST-other-user" },
      coverageProvenance: { runId: "TEST-old-run", budgetRevision: 9 },
      limits: { ...source.research!.limits, authorization: "TEST-not-authority" },
    },
    executionLimits: { ...source.executionLimits, requestId: "TEST-old-execution" },
  } as unknown as TaskDraft;
  const before = structuredClone(tainted);
  const template = templateFromDraft(tainted, source.name);
  expect(template.conditions.research).toEqual(source.research);
  expect(template.conditions.executionLimits).toEqual(source.executionLimits);
  expect(tainted).toEqual(before);
  const persisted = {
    ...template,
    conditions: { ...template.conditions, ...tainted },
  };
  const child = draftFromTemplate(persisted);
  expect(child.research).toEqual(source.research);
  expect(child.executionLimits).toEqual(source.executionLimits);
  expect(child).not.toHaveProperty("quote");
  expect(child).not.toHaveProperty("requestId");
  expect(child.id).not.toBe(source.id);
});

it.each([
  { stopAtAnyLimit: false },
  { maxSoubei: Number.NaN },
  { demandTypes: ["UNSUPPORTED"] },
])("rejects malformed research configuration instead of silently losing it: %j", (change) => {
  const source = configuredDraft();
  source.research = { ...source.research, ...change } as TaskDraft["research"];
  expect(() => templateFromDraft(source, source.name)).toThrow();
});

it("keeps templates saved before research/execution fields compatible", () => {
  const source = configuredDraft();
  delete source.research;
  delete source.executionLimits;
  const template = templateFromDraft(source, source.name);
  expect(localTemplateSchema.safeParse(template).success).toBe(true);
  const child = draftFromTemplate(template);
  expect(child.research).toBeUndefined();
  expect(child.executionLimits).toBeUndefined();
  expect(child.terms).toEqual(source.terms);
  expect(child.templateSourceDraftIds).toEqual([source.id]);
});

it("keeps the configured limits through the real P05 save-template/create actions without starting", async () => {
  const source = configuredDraft();
  source.mode = "once";
  sessionStorage.setItem(storedKey("task-library"), JSON.stringify([source]));
  render(<TasksPage />);
  fireEvent.click(await screen.findByRole("button", { name: "保存为模板" }));
  fireEvent.click(screen.getByRole("button", { name: "保存模板" }));
  fireEvent.click(await screen.findByRole("button", { name: "从模板新建" }));
  const created = JSON.parse(sessionStorage.getItem(storedKey("task"))!);
  expect(created.research).toEqual(source.research);
  expect(created.executionLimits).toEqual(source.executionLimits);
  expect(created.templateSourceDraftIds).toEqual([source.id]);
  expect(context.navigate).toHaveBeenCalledWith("/tasks/new");
  expect(context.service.startTask).not.toHaveBeenCalled();
});
