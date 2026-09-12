import {
  PLATFORMS,
  type TaskDraft,
  type Term,
  type Suggestion,
  type Profile,
  type PlatformConnection,
} from "./models";
import { researchSettingsSchema } from "./researchUsage";
import { industryStrategyError } from './industryTaskStrategy';
import { platformTermsError } from './platformSearchTerms';
import {foregroundBindingSchema,publicSourceBindingSchema} from '../../shared/foregroundCollection';
import {allowsPublicSource,DEFAULT_PUBLIC_SOURCE,publicSourceIdSchema} from '../../shared/publicSources';
import {researchSourcePlanSchema} from '../../shared/researchSourcePlan';
import {DYNAMIC_RESEARCH_SOURCE,dynamicLimitsValid,dynamicScopeSchema,researchSelectionSchema} from '../../shared/dynamicResearch';
import {planNativeCollectionLinks} from '../../shared/nativeCollectionLinks';

export const PUBLIC_SOURCE_SCOPE='V2EX近期主题有界抽样，不覆盖历史/全站/评论';
function biliLinkCount(draft:TaskDraft):number|null {
 try {
  const platforms=draft.platforms.map(platform=>({bilibili:'BILIBILI'} as const)[platform as 'bilibili']);
  const links=draft.links.split(/\r\n|\n|\r/u).map(value=>value.trim()).filter(Boolean);
  const planned=planNativeCollectionLinks(platforms,links);
  return planned.every(item=>item.platform==='BILIBILI'&&(item.kind==='creator'||/^BV1[1-9A-HJ-NP-Za-km-z]{9}$/.test(item.external_id)))?planned.length:null;
 } catch {return null;}
}
export function hasPublicSourceBinding(connection: PlatformConnection): boolean {
  return connection.platform==='web' && connection.status==='CONNECTED' &&
    !connection.accountId && !connection.accountName && !connection.registration && !connection.foregroundBinding &&
    publicSourceBindingSchema.safeParse(connection.publicBinding).success;
}
export function publicTaskScope(draft: TaskDraft, connections: PlatformConnection[]): string | null {
  if (!draft.platforms.includes('web')) return null;
  return JSON.stringify(draft.platforms.map(platform=>connections.filter(c=>c.platform===platform &&
    (platform==='web' ? hasPublicSourceBinding(c) : c.accountId===draft.accounts[platform] && hasForegroundBinding(c)))
    .map(c=>c.publicBinding ?? c.foregroundBinding)));
}

export function hasForegroundBinding(connection: PlatformConnection): boolean {
  const parsed = foregroundBindingSchema.safeParse(connection.foregroundBinding);
  const platform={xhs:'XIAOHONGSHU',douyin:'DOUYIN',bilibili:'BILIBILI',zhihu:'ZHIHU'} as const;
  if (!parsed.success || !connection.registration || !(connection.platform in platform) ||
      parsed.data.platform!==platform[connection.platform as keyof typeof platform] || connection.status !== 'CONNECTED') return false;
  const binding = parsed.data, registration = connection.registration;
  return registration.disconnectedAt === null && registration.connectionId === binding.connectionId &&
    registration.version === binding.connectionVersion && registration.deviceId === binding.deviceId &&
    connection.accountId === binding.accountPublicId;
}
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
  const queryError=platformTermsError(draft);
  if(queryError)errors.platformTerms=queryError;
  const industryError=industryStrategyError(draft);
  if(industryError)errors.industryStrategy=industryError;
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
  nativeMonitorReady = false,
  nativeResearchReady = false,
): string[] {
  const blockers = Object.values(taskErrors(draft));
  if(draft.publicSource!==undefined&&!researchSelectionSchema.safeParse(draft.publicSource).success)
    blockers.push('公开板块标识无效，请重新选择。');
  if (draft.research && (!researchSettingsSchema.safeParse(draft.research).success || draft.research.maxSoubei === null))
    blockers.push("请填写有效的研究范围及搜贝上限。");
  const profile = profiles.find(
    (p) =>
      p.id === draft.profileId &&
      p.version === draft.profileVersion &&
      p.status === "CONFIRMED",
  );
  if (!profile) blockers.push("请选择并确认真实业务画像版本。");
  const publicRows=connections.filter(hasPublicSourceBinding);
  const publicSelected=draft.platforms.includes('web');
  const selectedPublicSource=draft.publicSource??DEFAULT_PUBLIC_SOURCE;
  const dynamic=selectedPublicSource===DYNAMIC_RESEARCH_SOURCE;
  if(dynamic&&(!publicSelected||draft.platforms.length!==1||!draft.research||!dynamicScopeSchema.safeParse(draft.research.dynamicScope).success||
    !dynamicLimitsValid(draft.research.limits)||draft.research.sourcePlan||draft.research.provenance||draft.research.coverageProvenance))
    blockers.push('自主研究需明确时效，并使用2–100次搜索/读取、1–30分钟、2–20次模型调用上限；不能混入其他来源计划。');
  const sourcePlan=researchSourcePlanSchema.safeParse(draft.research?.sourcePlan);
  const sources=sourcePlan.success?sourcePlan.data.sources:[selectedPublicSource];
  if(sourcePlan.success && (sources[0]!==selectedPublicSource || (draft.research?.limits.sources??0)<sources.length ||
      (draft.executionLimits?.max_records??0)<sources.length || draft.mode!=='once'||draft.platforms.length!==1||!publicSelected))
    blockers.push('多来源计划需核对主来源、来源预算及每源记录配额，仅支持公开单次研究。');
  if(publicSelected && !dynamic && (publicRows.length!==1 || !sources.every(source=>allowsPublicSource(source,publicRows[0].publicBinding?.sourceId,publicRows[0].publicBinding?.sourceIds))))
    blockers.push('所选公开板块当前不可用，请重新核对来源；不会自动切换板块。');
  const publicMonitor=publicSelected&&draft.mode==='monitor'&&publicRows.length===1&&publicRows[0].publicBinding?.monitorSupported===true;
  const publicResearch=nativeResearchReady && draft.mode==='once' && draft.platforms.length===1 && publicSelected;
  if(publicSelected && (draft.accounts.web || !dynamic&&publicRows.length!==1 || !['once','monitor'].includes(draft.mode) || draft.mode==='monitor'&&!publicMonitor || draft.source!=='search' || draft.links.trim() || draft.research&&!publicResearch))
    blockers.push(draft.mode==='monitor'?'公开来源尚不具备持续监控能力。':'公开网站仅支持已核对的 V2EX 匿名近期主题关键词采样。');
  if(publicSelected && (!draft.executionLimits || !Number.isInteger(draft.executionLimits.max_records) ||
      !Number.isInteger(draft.executionLimits.max_runtime_seconds) || (draft.executionLimits.max_records??0)<draft.platforms.length ||
      (draft.executionLimits.max_runtime_seconds??0)<1 || (draft.executionLimits.max_records??0)>100 || (draft.executionLimits.max_runtime_seconds??0)>(dynamic?1800:900)))
    blockers.push(`公开采样需明确共享记录上限（至少所选平台数、最多100条）与运行时长（1至${dynamic?1800:900}秒）。`);
  const nativeSelections = draft.platforms.filter(platform=>platform!=='web').map(platform => connections.find(c => c.platform === platform &&
    c.accountId === draft.accounts[platform] && hasForegroundBinding(c)));
  const multiOnce = draft.mode === 'once' && draft.platforms.length > 1 && nativeSelections.every(c =>
    ['three-platform-foreground-v1','four-platform-foreground-v1','four-platform-public-bili-links-monitor-v1'].includes(c?.foregroundBinding?.mode ?? '')) &&
    new Set(nativeSelections.map(c => c?.registration?.deviceId)).size === 1 &&
    new Set(nativeSelections.map(c => c?.foregroundBinding?.mode)).size === 1;
  if(publicSelected && nativeSelections.some(c=>!c || c.foregroundBinding?.deviceId!==publicRows[0]?.publicBinding?.deviceId))
    blockers.push('公开来源与账号采集必须绑定同一本机设备。');
  if (nativeSelections.some(Boolean) && draft.executionLimits &&
      (draft.executionLimits.max_records ?? 0) < draft.platforms.length)
    blockers.push('共享记录上限不能小于所选平台数。');
  for (const platform of draft.platforms) {
    if(platform==='web'&&dynamic)continue; // Authenticated server capability is checked separately, not a local connector.
    const name = PLATFORMS.find((p) => p.id === platform)?.name || platform;
    const connection = connections.find(
      (c) =>
        c.platform === platform &&
        (platform !== 'web' || hasPublicSourceBinding(c)) &&
        (!c.registration || hasForegroundBinding(c)) &&
        c.status === "CONNECTED" &&
        (platform === "web" || c.accountId === draft.accounts[platform]),
    );
    if (!connection) {
      blockers.push(`${name} 需连接并选择有效账号或确认读取范围。`);
      continue;
    }
    const nativeMonitor = nativeMonitorReady && draft.mode === 'monitor' && hasForegroundBinding(connection) &&
      draft.platforms.every(p => ['xhs','douyin','bilibili','zhihu','web'].includes(p)) && (!publicSelected||publicMonitor);
    const linkCount=biliLinkCount(draft);
    const nativeLinks=draft.source==='links'&&platform==='bilibili'&&connection.capabilities.includes('read')&&linkCount!==null&&
      draft.platforms.length===1&&!draft.research&&!!draft.executionLimits&&
      (draft.executionLimits.max_records??0)>=linkCount&&
      (draft.mode==='once'||draft.mode==='monitor'&&nativeMonitor);
    if (connection.registration && ((!nativeMonitor && !multiOnce && !nativeLinks && (draft.platforms.length !== 1 || draft.mode !== 'once')) ||
        draft.source !== 'search' && !nativeLinks ||
        draft.links.trim() !== '' && !nativeLinks || draft.research))
      blockers.push('本机受控采集仅支持已开放平台的关键词搜索，暂不支持链接或研究。');
    if (connection.registration && draft.executionLimits &&
        ((draft.executionLimits.max_records ?? 0) > 100 || (draft.executionLimits.max_runtime_seconds ?? 0) > 900))
      blockers.push('本机受控采集每次最多 100 条记录、900 秒，请调低执行上限。');
    const required = draft.source === "search" ? "search" : "read";
    if (!connection.capabilities.includes(required))
      blockers.push(
        `${name} 的${required === "search" ? "搜索" : "读取"}能力尚未通过检查。`,
      );
    if (
      draft.mode === "monitor" &&
      !(platform==='web'?publicMonitor:nativeMonitor) && !connection.capabilities.includes("monitor")
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
    ...(draft.publicSource!==undefined ? {publicSource:draft.publicSource} : {}),
    links: draft.links,
    ...(draft.research ? { research: draft.research } : {}),
    ...(draft.industryStrategy ? { industryStrategy: draft.industryStrategy } : {}),
    ...(draft.platformTerms!==undefined ? {platformTerms:draft.platformTerms} : {}),
  });
}
