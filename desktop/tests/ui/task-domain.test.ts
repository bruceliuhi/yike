import { describe, it, expect } from "vitest";
import {
  newTaskDraft,
  type Suggestion,
} from "../../src/renderer/domain/models";
import {
  makeTerm,
  applySuggestion,
  removeTerm,
  taskErrors,
  taskFingerprint,
  startBlockers,
} from "../../src/renderer/domain/task";
describe("task draft invariants", () => {
  const suggestion: Suggestion = {
    profileId: "p1",
    requestId: "r1",
    keywords: ["采购展台", "找搭建", "采购展台"],
    exclusions: ["招聘"],
  };
  it("keeps manual changes and removed suggestions during replacement", () => {
    let d = {
      ...newTaskDraft(),
      profileId: "p1",
      terms: [
        makeTerm("人工需求"),
        { ...makeTerm("自定义改词", "ai"), edited: true },
        makeTerm("找搭建", "ai"),
      ],
    };
    d = removeTerm(d, "terms", d.terms[2].id);
    const out = applySuggestion(d, suggestion, "replace_unedited");
    expect(out.terms.map((t) => t.value)).toEqual([
      "人工需求",
      "自定义改词",
      "采购展台",
    ]);
    expect(out.exclusions.map((t) => t.value)).toEqual(["招聘"]);
  });
  it("ignores responses from a different profile", () => {
    const draft = { ...newTaskDraft(), profileId: "new" };
    expect(applySuggestion(draft, suggestion, "append")).toBe(draft);
  });
  it("does not change platforms or schedules when applying suggestions", () => {
    const d = { ...newTaskDraft("monitor"), profileId: "p1" };
    const out = applySuggestion(d, suggestion, "append");
    expect(out.schedule).toEqual(d.schedule);
    expect(out.platforms).toEqual(d.platforms);
  });
  it("detects broad exclusion and duplicate schedule times", () => {
    const d = {
      ...newTaskDraft("monitor"),
      name: "任务",
      terms: [makeTerm("找展台设计")],
      exclusions: [makeTerm("设计")],
    };
    d.schedule.times = ["09:00", "09:00"];
    expect(taskErrors(d).conflicts).toContain("找展台设计");
    expect(taskErrors(d).schedule).toBeTruthy();
  });
  it("confirmation fingerprint changes for account, schedule or edited content", () => {
    const d = newTaskDraft();
    expect(taskFingerprint(d)).not.toBe(
      taskFingerprint({ ...d, accounts: { xhs: "new" } }),
    );
    expect(taskFingerprint(d)).not.toBe(
      taskFingerprint({ ...d, terms: [makeTerm("买方需求")] }),
    );
  });
  it("allows confirmed exclusions through native once and monitor collection paths", () => {
    const connection = {platform: 'xhs', accountId: 'a1', status: 'CONNECTED', capabilities: ['search'],
      registration: {deviceId: 'd1', connectionId: 'c1', version: 1, connectedAt: '2026-09-10T00:00:00Z', disconnectedAt: null},
      foregroundBinding: {mode: 'three-platform-foreground-v1', platform: 'XIAOHONGSHU', connectionId: 'c1', connectionVersion: 1,
        deviceId: 'd1', accountPublicId: '66c01234abcdef0123456789'}} as any;
    const profile = {id: 'p1', version: 1, status: 'CONFIRMED'} as any;
    const once = {...newTaskDraft(), name: '任务', profileId: 'p1', profileVersion: 1, terms: [makeTerm('采购')], exclusions: [makeTerm('招聘')],
      platforms: ['xhs'], accounts: {xhs: 'a1'}} as any;
    expect(startBlockers(once, [profile], [connection], true)).not.toContain(expect.stringContaining('排除词'));
    const monitor = {...once, mode: 'monitor', schedule: {...newTaskDraft('monitor').schedule}};
    expect(startBlockers(monitor, [profile], [connection], true, true)).not.toContain(expect.stringContaining('排除词'));
  });
});
