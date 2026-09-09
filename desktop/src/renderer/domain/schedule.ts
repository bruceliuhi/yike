import { z } from "zod";
import type { Schedule } from "./models";

/** A configuration contract only. An executor must opt in before starting it. */
export const SCHEDULE_POLICY_VERSION = 1 as const;
export const scheduleSchema = z.object({
  kind: z.enum(["daily", "interval"]),
  times: z.array(z.string()),
  interval: z.number(),
  start: z.string(),
  end: z.string(),
  timezone: z.string(),
  policyVersion: z.literal(SCHEDULE_POLICY_VERSION).optional(),
});

const time = /^([01]\d|2[0-3]):[0-5]\d$/;

export function scheduleWindowLabel(schedule: Schedule): string {
  if (schedule.kind === "daily") return "按每日设定时间";
  if (!time.test(schedule.start) || !time.test(schedule.end))
    return "执行窗口待设置";
  if (schedule.start === schedule.end) return "开始与结束相同，请修改";
  // Legacy schedules may have had different overnight semantics. Do not rewrite them.
  if (schedule.policyVersion !== SCHEDULE_POLICY_VERSION)
    return `${schedule.start}–${schedule.end}（历史规则待核验）`;
  return `${schedule.start}–${schedule.end < schedule.start ? "次日 " : ""}${schedule.end}（含开始，不含结束）`;
}

export function schedulePolicyDescription(schedule: Schedule): string[] {
  if (schedule.policyVersion !== SCHEDULE_POLICY_VERSION)
    return ["历史日程未声明跨日、夏令时与离线规则；继续沿用原配置，需由原执行服务核验。"];
  return [
    schedule.kind === "daily"
      ? "夏令时：不存在的设定时刻跳过，重复时刻只执行较早的一次。"
      : "固定间隔从每天窗口开始，按实际经过小时计算；窗口边界遇夏令时缺失则跳过该窗口，重复则取较早时刻。",
    "离线错过的计划不补跑；恢复在线后，从下一个计划时刻继续。",
    "以上为任务配置，执行服务须明确支持；当前页面不代表已经按规则运行。",
  ];
}

export function scheduleContractBlocker(
  schedule: Schedule,
  supportedVersion: number | undefined,
): string | null {
  if (schedule.policyVersion === undefined) return null;
  if (schedule.policyVersion !== SCHEDULE_POLICY_VERSION)
    return "此日程规则版本不受当前客户端支持，请核对原配置。";
  if (supportedVersion !== SCHEDULE_POLICY_VERSION)
    return "执行服务尚未支持当前日程规则，可保存草稿，暂不能启动此监控。";
  return null;
}
