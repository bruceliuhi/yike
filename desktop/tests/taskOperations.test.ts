import { describe, it, expect } from "vitest";
import { newTaskDraft, type TaskRun } from "../src/renderer/domain/models";
import {
  configurationHash,
  startEntry,
  readStartEntry,
  parseStartReceipt,
  parseActionReceipt,
  actionEntry,
  readActionEntry,
  type TaskStartBinding,
  type TaskActionBinding,
} from "../src/renderer/domain/taskOperations";
import { inDateRange, pageItems } from "../src/renderer/pages/tasks/listState";
const hash = "a".repeat(64);
const binding: TaskStartBinding = {
  draftId: "draft",
  revision: 2,
  requestId: "task:draft:2",
  configurationHash: hash,
  mode: "once",
};
const run: TaskRun = {
  id: "run",
  name: "测试任务",
  mode: "once",
  status: "PENDING",
  platforms: ["web"],
};
describe("task execution receipt contracts", () => {
  it("hashes the entire confirmed configuration and stores only its binding", async () => {
    const draft = newTaskDraft();
    expect(await configurationHash(draft)).toMatch(/^[a-f0-9]{64}$/);
    expect(await configurationHash(draft)).not.toBe(
      await configurationHash({ ...draft, accounts: { web: "other-account" } }),
    );
    expect(await configurationHash(draft)).not.toBe(
      await configurationHash({ ...draft, profileVersion: 8 }),
    );
    expect(readStartEntry("draft", startEntry(binding))).toEqual(binding);
    expect(readStartEntry("other", startEntry(binding))).toBeUndefined();
    expect(
      readStartEntry(
        "draft",
        JSON.stringify([binding.requestId, 2, "invalid", "once"]),
      ),
    ).toBeUndefined();
    expect(readStartEntry("draft", "task:draft:2")).toEqual({
      draftId: "draft",
      requestId: "task:draft:2",
      revision: 2,
    });
  });
  it.each([
    "requestId",
    "draftId",
    "revision",
    "configurationHash",
    "mode",
  ] as const)("rejects a different start %s", (field) => {
    const changes = {
      requestId: "task:draft:3",
      draftId: "other",
      revision: 3,
      configurationHash: "b".repeat(64),
      mode: "monitor",
    };
    expect(() =>
      parseStartReceipt(
        { ...binding, [field]: changes[field], status: "ACCEPTED", run },
        binding,
      ),
    ).toThrow(/不匹配/);
  });
  it("requires definitive rejection and refuses to auto-unlock legacy records", () => {
    expect(() =>
      parseStartReceipt({ ...binding, status: "REJECTED" }, binding),
    ).toThrow();
    expect(
      parseStartReceipt(
        { ...binding, status: "REJECTED", confirmedNotStarted: true },
        binding,
      ).status,
    ).toBe("REJECTED");
    expect(
      parseStartReceipt({ ...binding, status: "UNKNOWN" }, binding).status,
    ).toBe("UNKNOWN");
    expect(() =>
      parseStartReceipt(
        { ...binding, status: "ACCEPTED", run },
        readStartEntry("draft", "task:draft:2")!,
      ),
    ).toThrow(/旧请求/);
  });
  it("binds task operations and requires the actual completed transition", () => {
    const action: TaskActionBinding = {
      taskId: "run",
      action: "pause",
      requestId: "request",
      expectedHash: hash,
    };
    expect(readActionEntry(actionEntry(action))).toEqual(action);
    expect(() =>
      parseActionReceipt(
        { ...action, status: "APPLIED", run: { ...run, status: "RUNNING" } },
        action,
      ),
    ).toThrow();
    expect(() =>
      parseActionReceipt(
        {
          ...action,
          requestId: "other",
          status: "APPLIED",
          run: { ...run, status: "PAUSED" },
        },
        action,
      ),
    ).toThrow();
    expect(
      parseActionReceipt(
        { ...action, status: "APPLIED", run: { ...run, status: "PAUSED" } },
        action,
      ).status,
    ).toBe("APPLIED");
    expect(() =>
      parseActionReceipt({ ...action, status: "REJECTED" }, action),
    ).toThrow();
  });
  it("filters known update dates inclusively and clamps the last page", () => {
    expect(inDateRange(undefined, "2026-09-09", "")).toBe(false);
    expect(inDateRange(undefined, "", "")).toBe(true);
    expect(
      inDateRange(
        new Date(2026, 8, 9, 23, 59, 59).toISOString(),
        "2026-09-09",
        "2026-09-09",
      ),
    ).toBe(true);
    expect(
      inDateRange(
        new Date(2026, 8, 10, 0).toISOString(),
        "2026-09-09",
        "2026-09-09",
      ),
    ).toBe(false);
    expect(pageItems([1, 2, 3], 9, 2)).toEqual({
      items: [3],
      page: 2,
      pages: 2,
    });
  });
});
