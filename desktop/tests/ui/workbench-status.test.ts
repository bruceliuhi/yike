import { expect, it } from "vitest";
import type { TaskRun } from "../../src/renderer/domain/models";
import {
  summarizeTaskRuns,
  taskQueueEmptyCopy,
} from "../../src/renderer/domain/workbenchStatus";

const base = (overrides: Partial<TaskRun> = {}): TaskRun => ({
  id: "TEST-task",
  name: "TEST 任务",
  mode: "monitor",
  status: "COMPLETED",
  platforms: ["web"],
  updatedAt: "2026-09-23T09:00:00+08:00",
  ...overrides,
});

it("keeps an offline task distinct from a completed run with no new results", () => {
  expect(
    summarizeTaskRuns([
      base({
        status: "PARTIAL",
        platformStages: [{ platform: "web", status: "OFFLINE" }],
      }),
    ]),
  ).toBe("OFFLINE");
  expect(
    summarizeTaskRuns([
      base({
        platformStages: [{ platform: "web", status: "NO_NEW", newCount: 0 }],
      }),
    ]),
  ).toBe("NO_NEW");
});

it("only calls an empty workbench queue empty after a terminal task check", () => {
  expect(summarizeTaskRuns([])).toBe("NO_TASK");
  expect(
    summarizeTaskRuns([
      base({
        status: "RUNNING",
        platformStages: [{ platform: "web", status: "RUNNING" }],
      }),
    ]),
  ).toBe("UNKNOWN");
  expect(summarizeTaskRuns([base()])).toBe("UNKNOWN");
  expect(summarizeTaskRuns([base({ statistics: { today: 0 } })])).toBe("READY");
  expect(
    summarizeTaskRuns([
      base({
        platformStages: [
          { platform: "web", status: "NO_NEW", newCount: 0 },
          { platform: "xhs", status: "RUNNING" },
        ],
      }),
    ]),
  ).toBe("UNKNOWN");
});

it("uses explicit copy for each empty workbench state", () => {
  expect(taskQueueEmptyCopy("OFFLINE").title).toBe("任务离线");
  expect(taskQueueEmptyCopy("NO_NEW").title).toBe("本次运行无新增");
  expect(taskQueueEmptyCopy("READY").title).toBe("今日待办为空");
  expect(taskQueueEmptyCopy("UNKNOWN").title).toBe("待办状态待核验");
});
