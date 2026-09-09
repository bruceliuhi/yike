import {
  PLATFORMS,
  type TaskDraft,
  type Term,
  type Suggestion,
  type Profile,
  type PlatformConnection,
} from "./models";
import { researchSettingsSchema } from "./researchUsage";
export const termKey = (value: string) =>
  value.trim().replace(/\s+/g, " ").toLocaleLowerCase();
export function splitTerms(value: string): string[] {
  return [
    ...new Set(
      value
        .split(/[,，;；\n]+/)
        .map((v) => v.trim())
        .filter(Boolean),
    ),
  ];
}
export function makeTerm(
  value: string,
  origin: Term["origin"] = "manual",
): Term {
  return {
    id: crypto.randomUUID(),
    value: value.trim(),
    origin,
    edited: false,
  };
}
export function addTerms(terms: Term[], input: string): Term[] {
  const keys = new Set(terms.map((t) => termKey(t.value)));
  return [
    ...terms,
    ...splitTerms(input)
      .filter((v) => !keys.has(termKey(v)) && !!keys.add(termKey(v)))
      .map((v) => makeTerm(v)),
  ];
}
export function removeTerm(
  draft: TaskDraft,
  kind: "terms" | "exclusions",
  id: string,
): TaskDraft {
  const removed = draft[kind].find((t) => t.id === id);
  return {
    ...draft,
    revision: draft.revision + 1,
    [kind]: draft[kind].filter((t) => t.id !== id),
    removed: removed
      ? [...new Set([...draft.removed, `${kind}:${termKey(removed.value)}`])]
      : draft.removed,
  };
}
export function applySuggestion(
  draft: TaskDraft,
  suggestion: Suggestion,
  mode: "append" | "replace_unedited",
): TaskDraft {
  if (suggestion.profileId !== draft.profileId) return draft;
  const merge = (kind: "terms" | "exclusions", values: string[]) => {
    const keep =
      mode === "append"
        ? draft[kind]
        : draft[kind].filter((t) => t.origin === "manual" || t.edited);
    const keys = new Set(keep.map((t) => termKey(t.value)));
    const removed = new Set(draft.removed);
    return [
      ...keep,
      ...values
        .map((v) => v.trim())
        .filter(
          (v) =>
            v &&
            !removed.has(`${kind}:${termKey(v)}`) &&
            !keys.has(termKey(v)) &&
            !!keys.add(termKey(v)),
        )
        .map((v) => makeTerm(v, "ai")),
    ];
  };
  return {
    ...draft,
    revision: draft.revision + 1,
    terms: merge("terms", suggestion.keywords),
    exclusions: merge("exclusions", suggestion.exclusions),
    suggestionProfile: draft.profileId,
  };
}
export function taskErrors(draft: TaskDraft): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!draft.name.trim()) errors.name = "请填写任务名称。";
  else if (draft.name.length > 60) errors.name = "任务名称不能超过60个字。";
  if (!draft.platforms.length) errors.platforms = "至少选择一个目标平台。";
  if (draft.source === "search" && !draft.terms.length)
    errors.terms = "请添加至少一个搜索关键词。";
  if (draft.terms.length > 20 || draft.exclusions.length > 20)
    errors.terms = "关键词和排除词各不能超过20个。";
  if (
    [...draft.terms, ...draft.exclusions].some(
      (t) => !t.value.trim() || t.value.length > 80,
    )
  )
    errors.terms = "每个词项需为1至80个字符。";
  const conflicts = draft.terms.filter((t) =>
    draft.exclusions.some((e) => termKey(t.value).includes(termKey(e.value))),
  );
  if (conflicts.length)
    errors.conflicts = `排除词会过滤搜索词：${conflicts.map((t) => t.value).join("、")}。请修改冲突项。`;
  if (draft.source === "links") {
    const links = splitTerms(draft.links);
    if (!links.length) errors.links = "请填写公开内容链接。";
    else if (
      links.some((link) => {
        try {
          const u = new URL(link);
          return (
            !["http:", "https:"].includes(u.protocol) ||
            !!u.username ||
            !!u.password
          );
        } catch {
          return true;
        }
      })
    )
      errors.links = "每行填写一个有效的 http 或 https 公开链接。";
  }
  if (draft.mode === "monitor") {
    const schedule = draft.schedule;
    try {
      new Intl.DateTimeFormat("zh-CN", {
        timeZone: schedule.timezone,
      }).format();
    } catch {
      errors.timezone = "请选择有效时区。";
    }
    if (
      schedule.kind === "daily" &&
      (!schedule.times.length ||
        schedule.times.some((t) => !/^([01]\d|2[0-3]):[0-5]\d$/.test(t)) ||
        new Set(schedule.times).size !== schedule.times.length)
    )
      errors.schedule = "请设置有效且不重复的执行时间。";
    if (
      schedule.kind === "interval" &&
      (!Number.isFinite(schedule.interval) ||
        schedule.interval < 1 ||
        schedule.interval > 168)
    )
      errors.schedule = "间隔需在1至168小时之间；实际频率仍受平台能力限制。";
    if (
      schedule.kind === "interval" &&
      (!/^([01]\d|2[0-3]):[0-5]\d$/.test(schedule.start) ||
        !/^([01]\d|2[0-3]):[0-5]\d$/.test(schedule.end))
    )
      errors.schedule = "请填写有效的执行窗口。";
    else if (schedule.kind === "interval" && schedule.start === schedule.end)
      errors.schedule = "执行窗口开始与结束不能相同；请明确设置当天或跨日窗口。";
  }
  return errors;
}
export function startBlockers(
  draft: TaskDraft,
  profiles: Profile[],
  connections: PlatformConnection[],
  deviceReady: boolean,
): string[] {
  const blockers = Object.values(taskErrors(draft));
  if (draft.research && (!researchSettingsSchema.safeParse(draft.research).success || draft.research.maxSoubei === null))
    blockers.push("请填写有效的研究范围及搜贝上限。");
  const profile = profiles.find(
    (p) =>
      p.id === draft.profileId &&
      p.version === draft.profileVersion &&
      p.status === "CONFIRMED",
  );
  if (!profile) blockers.push("请选择并确认真实业务画像版本。");
  for (const platform of draft.platforms) {
    const name = PLATFORMS.find((p) => p.id === platform)?.name || platform;
    const connection = connections.find(
      (c) =>
        c.platform === platform &&
        !c.registration &&
        c.status === "CONNECTED" &&
        (platform === "web" || c.accountId === draft.accounts[platform]),
    );
    if (!connection) {
      blockers.push(`${name} 需连接并选择有效账号或确认读取范围。`);
      continue;
    }
    const required = draft.source === "search" ? "search" : "read";
    if (!connection.capabilities.includes(required))
      blockers.push(
        `${name} 的${required === "search" ? "搜索" : "读取"}能力尚未通过检查。`,
      );
    if (
      draft.mode === "monitor" &&
      !connection.capabilities.includes("monitor")
    )
      blockers.push(`${name} 尚不具备持续监控能力。`);
  }
  if (!deviceReady) blockers.push("执行设备尚未绑定或当前不可用。");
  return blockers;
}
export function taskFingerprint(draft: TaskDraft): string {
  return JSON.stringify({
    id: draft.id,
    revision: draft.revision,
    profileId: draft.profileId,
    profileVersion: draft.profileVersion,
    name: draft.name,
    terms: draft.terms.map((t) => t.value),
    exclusions: draft.exclusions.map((t) => t.value),
    platforms: draft.platforms,
    accounts: draft.accounts,
    mode: draft.mode,
    schedule: draft.schedule,
    source: draft.source,
    links: draft.links,
    ...(draft.research ? { research: draft.research } : {}),
  });
}
