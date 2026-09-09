import type { Candidate } from '../../src/renderer/domain/candidates';
import type { Followup, Opportunity, PlatformConnection, Profile, TaskDraft, TaskRun } from '../../src/renderer/domain/models';

/** Synthetic layout data only. Never an assertion about a real buyer or run. */
export const HARNESS_MARKER = 'YIKE_VISUAL_TEST_ONLY_18794';
export const TEST_USER = 'TEST-visual-review';
export const TEST_TIME = '2026-09-09T09:00:00+08:00';
export const KEYWORDS = ['找展台搭建', '求展台设计', '展台搭建报价', '展位设计预算', '展会布展需求', '展台搭建招标', '展位施工询价', '展台搭建推荐'];
export const EXCLUSIONS = ['招聘', '求职', '培训', '招生'];
export const profile: Profile = {
  id: 'TEST-profile-v1', version: 1, status: 'CONFIRMED',
  fields: {service: 'TEST 展台设计搭建', customer: 'TEST 参展企业与展会主办方', regions: 'TEST 湖南、深圳', preference: 'TEST 公开预算询价与布展需求', exclusions: '招聘、求职、培训、招生'},
  description: 'TEST 视觉验收画像；仅用于已批准展台设计场景的页面排版。',
};
export function taskDraft(mode: 'once' | 'monitor'): TaskDraft {
  return {
    id: `TEST-draft-${mode}`, revision: 1, name: `TEST 展台需求${mode === 'monitor' ? '监控' : '发现'}`,
    profileId: profile.id, profileVersion: 1,
    terms: KEYWORDS.map((value, i) => ({id: `TEST-term-${i}`, value, origin: 'ai', edited: false})),
    exclusions: EXCLUSIONS.map((value, i) => ({id: `TEST-exclusion-${i}`, value, origin: 'ai', edited: false})),
    removed: [], source: 'search', links: '', platforms: ['xhs', 'douyin', 'bilibili', 'zhihu', 'web'], accounts: {}, mode,
    schedule: {kind: 'daily', times: ['09:00', '15:00'], interval: 3, start: '09:00', end: '18:00', timezone: 'Asia/Shanghai'},
    savedAt: TEST_TIME, suggestionProfile: profile.id,
  };
}
export const connections: PlatformConnection[] = [
  {platform: 'xhs', status: 'DISCONNECTED', capabilities: [], reason: 'TEST 未连接状态'},
  {platform: 'douyin', status: 'DISCONNECTED', capabilities: [], reason: 'TEST 未连接状态'},
  {platform: 'bilibili', status: 'DISCONNECTED', capabilities: [], reason: 'TEST 未连接状态'},
  {platform: 'zhihu', status: 'DISCONNECTED', capabilities: [], reason: 'TEST 未连接状态'},
  {platform: 'web', status: 'DISCONNECTED', capabilities: [], reason: 'TEST 公开范围待确认'},
];
export const opportunity: Opportunity = {
  sourceObservedAt: TEST_TIME, sourceEvidenceVersion: 'TEST-evidence-v1',
  libraryFacts: {
    schema_version: 1, opportunity_id: 'TEST-opportunity', source_url: 'https://visual-test.invalid/TEST-opportunity',
    observed_at: TEST_TIME, evidence_version: 'TEST-evidence-v1',
    stage: {status: 'KNOWN', label: 'TEST 预算询价', evidence_excerpt: 'TEST 预算编制阶段询价，仅用于布局。'},
    materials_deadline: {status: 'KNOWN', at: '2026-09-15T18:00:00+08:00', evidence_excerpt: 'TEST 合成资料截止，只用于筛选与布局。'},
  },
  id: 'TEST-opportunity', sample: false,
  title: 'TEST 180㎡展区设计搭建预算询价', buyer: 'TEST 需求方（合成测试对象）',
  summary: 'TEST 180㎡展区，包含设计、搭建、维护、撤展与组展服务。',
  excerpt: 'TEST 本次报价仅用于预算测算。',
  matchReason: 'TEST 展台设计搭建范围与已选测试画像一致。',
  actionSignal: 'TEST 需先核对资料要求，再准备预算询价内容。',
  value: 'TEST 用于检查证据栏排版；不代表客户价值或实际收入。',
  risk: 'TEST 未确认预算、合同或联系人，不能据此真实联系。',
  contactPath: 'TEST 仅测试收件对象，无真实联系方式。',
  url: 'https://visual-test.invalid/TEST-opportunity', platform: '公开网站', sourceStatus: 'OPEN', profileStatus: 'CONFIRMED',
  profileVersionId: profile.id, reviewer: 'TEST 复核人', reviewedAt: TEST_TIME,
  publishedAt: '2026-09-08T16:54:00+08:00', updatedAt: TEST_TIME, intentStatus: 'READY',
  comment: 'TEST 您好，请问本次展区设计搭建的资料要求与服务范围如何获取？本内容只用于视觉验收，不会发送。',
  dm: 'TEST 请提供展区技术资料与预算询价要求。仅测试内存草稿。',
};
export const followups: Followup[] = [
  {id: 'TEST-followup-1', opportunityId: opportunity.id, title: opportunity.title, status: 'CONTACTED', note: 'TEST 人工登记状态示意：已整理待核实事项，没有进行真实联系。', createdAt: TEST_TIME, kind: 'manual'},
  {id: 'TEST-followup-2', opportunityId: opportunity.id, title: 'TEST 展区资料核对', status: 'REPLIED', note: 'TEST 回复列表状态示意，并非真实平台回复。', createdAt: '2026-09-09T09:30:00+08:00', kind: 'manual'},
];
export const monitor: TaskRun = {
  id: 'TEST-monitor', name: 'TEST 展台需求监控', mode: 'monitor', status: 'PARTIAL',
  platforms: ['xhs', 'douyin', 'bilibili', 'zhihu', 'web'], updatedAt: TEST_TIME,
  profileId: profile.id, profileVersion: 1, profileName: 'TEST 展台设计搭建', keywords: KEYWORDS,
  regions: 'TEST 湖南、深圳', createdAt: '2026-09-08T09:00:00+08:00', schedule: taskDraft('monitor').schedule,
  lastRunAt: TEST_TIME, nextRunAt: '2026-09-09T15:00:00+08:00',
  failureReason: 'TEST 平台状态组合示意，非真实运行记录。',
  platformStages: [
    {platform: 'xhs', status: 'LOGIN_EXPIRED', reason: 'TEST 登录状态过期，请重新连接后检查。', accountName: 'TEST 测试账号 A', newCount: 0, updatedAt: TEST_TIME},
    {platform: 'douyin', status: 'RATE_LIMITED', reason: 'TEST 限流状态示意，等待平台允许后再执行。', newCount: 0, updatedAt: TEST_TIME, nextRetryAt: '2026-09-09T10:00:00+08:00'},
    {platform: 'bilibili', status: 'NO_NEW', reason: 'TEST 本次无新增的状态示意。', newCount: 0, updatedAt: TEST_TIME},
    {platform: 'zhihu', status: 'OFFLINE', reason: 'TEST 执行设备离线状态示意。', updatedAt: TEST_TIME},
    {platform: 'web', status: 'COMPLETED', reason: 'TEST 完成状态示意。', newCount: 0, updatedAt: TEST_TIME},
  ],
  events: [
    {id: 'TEST-event-1', message: 'TEST 内存事件：测试任务状态载入。', occurredAt: TEST_TIME, level: 'info'},
    {id: 'TEST-event-2', message: 'TEST 内存事件：小红书登录过期状态。', occurredAt: TEST_TIME, platform: 'xhs', level: 'warning'},
  ], statistics: {today: 0, week: 0, month: 0, total: 0},
};
export const tasks: TaskRun[] = [
  {id: 'TEST-collection-1', name: 'TEST 展台需求发现', mode: 'once', status: 'RUNNING', platforms: ['web', 'xhs'], updatedAt: TEST_TIME},
  {id: 'TEST-collection-2', name: 'TEST 待处理采集任务', mode: 'once', status: 'BLOCKED', platforms: ['douyin'], updatedAt: TEST_TIME},
  monitor,
  {id: 'TEST-monitor-paused', name: 'TEST 展会布展监控草稿验证', mode: 'monitor', status: 'PAUSED', platforms: ['web'], updatedAt: TEST_TIME},
];
export const candidate: Candidate = {
  id: 'TEST-candidate', revision: 1, sample: false, status: 'PENDING_REVIEW',
  title: opportunity.title, buyer: opportunity.buyer, platform: 'web', sourceLabel: 'TEST 公开来源',
  sourceId: 'TEST-source', sourceVersionId: 'TEST-source-v1', sourceStatus: 'OPEN', url: opportunity.url,
  excerpt: opportunity.excerpt, summary: opportunity.summary, publishedAt: opportunity.publishedAt,
  collectedAt: TEST_TIME, location: 'TEST 深圳',
  assessment: {id: 'TEST-assessment', profileId: profile.id, profileVersion: 1, candidateRevision: 1, sourceVersionId: 'TEST-source-v1', assessedAt: TEST_TIME,
    evidence: {matchReason: opportunity.matchReason, actionSignal: opportunity.actionSignal, value: opportunity.value, risk: opportunity.risk, unknowns: 'TEST 联系方式、预算与采购安排均待核实。'}},
};
