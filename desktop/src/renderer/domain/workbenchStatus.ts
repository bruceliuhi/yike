import type { TaskRun } from "./models";

/**
 * The workbench must not turn a missing result into a zero-result claim.
 * These states are intentionally derived only from an explicit task/run
 * status, or from a terminal run with a complete platform snapshot.
 */
export type WorkbenchTaskState =
  | "NO_TASK"
  | "OFFLINE"
  | "NO_NEW"
  | "READY"
  | "UNKNOWN";

const OFFLINE = new Set(["OFFLINE"]);
const NO_NEW = new Set(["NO_NEW"]);
const TERMINAL = new Set(["COMPLETED", "SUCCESS", "NO_NEW"]);

function timestamp(run: TaskRun) {
  return Date.parse(run.updatedAt || run.lastRunAt || run.createdAt || "") || 0;
}

/** Summarise the newest legacy task without treating an incomplete run as empty. */
export function summarizeTaskRuns(runs: readonly TaskRun[]): WorkbenchTaskState {
  if (!runs.length) return "NO_TASK";
  const run = [...runs].sort((a, b) => timestamp(b) - timestamp(a))[0];
  const stages = run.platformStages || [];
  if (OFFLINE.has(run.status) || stages.some((stage) => OFFLINE.has(stage.status)))
    return "OFFLINE";
  // A mixed snapshot (one platform finished while another is still running)
  // is not a no-result run. Require an explicit task-level result or every
  // platform to report the explicit NO_NEW outcome.
  if (
    NO_NEW.has(run.status) ||
    (stages.length > 0 && stages.every((stage) => NO_NEW.has(stage.status)))
  )
    return "NO_NEW";

  // A terminal task with a complete platform snapshot is a known completed
  // check. It is safe to say today's queue is empty only after the queue API
  // itself returns an authoritative empty response.
  if (
    TERMINAL.has(run.status) &&
    run.statistics?.today === 0 &&
    (stages.length === 0 || stages.every((stage) => TERMINAL.has(stage.status)))
  )
    return "READY";
  return "UNKNOWN";
}

export function taskStateLabel(state: WorkbenchTaskState) {
  switch (state) {
    case "OFFLINE":
      return "任务离线";
    case "NO_NEW":
      return "本次无新增";
    case "READY":
      return "今日待办为空";
    case "UNKNOWN":
      return "状态待核验";
    default:
      return "未开始";
  }
}

export function taskQueueEmptyCopy(state: WorkbenchTaskState) {
  switch (state) {
    case "OFFLINE":
      return {
        title: "任务离线",
        description:
          "执行设备当前离线，本次检查未完成；不能据此判断今天没有新增需求。",
        action: "查看运行情况",
      };
    case "NO_NEW":
      return {
        title: "本次运行无新增",
        description: "最近一次检查已完成，当前任务范围内没有新增线索。",
        action: "查看运行情况",
      };
    case "READY":
      return {
        title: "今日待办为空",
        description:
          "最近一次检查已完成，目前没有待复核、待联系、待回复或待跟进事项。",
        action: "查看运行情况",
      };
    case "UNKNOWN":
      return {
        title: "待办状态待核验",
        description:
          "任务尚未完成或状态读取不完整，不能据此判断今天没有需求。",
        action: "查看运行情况",
      };
    default:
      return {
        title: "还没有待处理商机",
        description: "创建任务后，新增需求会出现在这里。",
        action: null,
      };
  }
}
