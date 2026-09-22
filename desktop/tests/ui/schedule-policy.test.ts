import { describe, expect, it } from "vitest";
import { newTaskDraft, type Schedule } from "../../src/renderer/domain/models";
import { scheduleContractBlocker, schedulePolicyDescription, scheduleSchema, scheduleWindowLabel } from "../../src/renderer/domain/schedule";
import { taskErrors, taskFingerprint } from "../../src/renderer/domain/task";
import { taskDraftSchema } from "../../src/renderer/app/taskDraft";
import { configurationHash, parseTaskRuns } from "../../src/renderer/domain/taskOperations";
const schedule = (patch: Partial<Schedule> = {}): Schedule => ({ ...newTaskDraft("monitor").schedule, kind: "interval", start: "22:00", end: "02:00", ...patch });
describe("monitor configuration without executing a scheduler", () => {
  it("shows next-day and exclusive-end semantics only for the declared policy", () => {
    expect(scheduleWindowLabel(schedule())).toBe("22:00–次日 02:00（含开始，不含结束）");
    expect(scheduleWindowLabel(schedule({start: "08:00", end: "18:00"}))).toBe("08:00–18:00（含开始，不含结束）");
    expect(scheduleWindowLabel(schedule({policyVersion: undefined}))).toBe("22:00–02:00（历史规则待核验）");
  });
  it("rejects equal or incomplete windows without guessing all-day semantics", () => {
    for (const patch of [{start: "09:00", end: "09:00"}, {end: ""}])
      expect(taskErrors({...newTaskDraft("monitor"), schedule: schedule(patch)}).schedule).toBeTruthy();
    expect(taskErrors({...newTaskDraft("monitor"), schedule: schedule()}).schedule).toBeUndefined();
  });
  it.each(["Europe/London", "America/New_York", "Australia/Sydney"])("records daily DST and offline rules for %s without inventing next-run times", timezone => {
    const configured = schedule({timezone, kind: "daily", times: ["02:30"]});
    expect(taskErrors({...newTaskDraft("monitor"), schedule: configured}).timezone).toBeUndefined();
    expect(schedulePolicyDescription(configured)[0]).toContain("不存在的设定时刻跳过，重复时刻只执行较早的一次");
    expect(schedulePolicyDescription(configured)[1]).toContain("离线错过的计划不补跑");
    expect(schedulePolicyDescription(configured)[2]).toContain("不代表已经按规则运行");
    expect(configured).not.toHaveProperty("nextRunAt");
  });
  it("keeps elapsed-hour intervals distinct from daily wall-clock recurrence", () => {
    expect(schedulePolicyDescription(schedule())[0]).toContain("按实际经过小时计算");
    expect(schedulePolicyDescription(schedule())[0]).not.toContain("只执行较早的一次");
  });
  it("preserves a legacy draft and its hash until explicit adoption", async () => {
    const draft = {...newTaskDraft("monitor"), schedule: schedule()};
    delete draft.schedule.policyVersion;
    const parsed = taskDraftSchema.parse(JSON.parse(JSON.stringify(draft)));
    expect(parsed.schedule).not.toHaveProperty("policyVersion");
    expect(taskFingerprint(parsed)).toBe(taskFingerprint(draft));
    expect(await configurationHash(parsed)).toBe(await configurationHash(draft));
    expect(await configurationHash({...draft, schedule: {...draft.schedule, policyVersion: 1}})).not.toBe(await configurationHash(draft));
  });
  it("requires executor opt-in for v1 while identifying the legacy contract", () => {
    expect(scheduleContractBlocker(schedule(), undefined)).toContain("暂不能启动");
    expect(scheduleContractBlocker(schedule(), undefined)).toContain("可先保存草稿");
    expect(scheduleContractBlocker(schedule(), undefined)).not.toContain("规则版本");
    // @ts-expect-error Exercise the defensive path for an incompatible persisted policy.
    expect(scheduleContractBlocker(schedule({policyVersion: 2}), 1)).toBe('此日程暂不可用，请重新设置执行时间。');
    expect(scheduleContractBlocker(schedule(), 1)).toBeNull();
    expect(scheduleContractBlocker(schedule({policyVersion: undefined}), undefined)).toBeNull();
    expect(schedulePolicyDescription(schedule({policyVersion: undefined}))[0]).toContain("历史日程未声明");
    expect(scheduleSchema.safeParse({...schedule(), policyVersion: 2}).success).toBe(false);
  });
  it("retains policy in the service task read model", () => {
    const [run] = parseTaskRuns([{id: "TEST-run", name: "TEST", mode: "monitor", status: "PAUSED", platforms: ["web"], schedule: schedule()}]);
    expect(run.schedule?.policyVersion).toBe(1);
  });
});
