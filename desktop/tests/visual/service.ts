import { ServiceError, type YikeService } from '../../src/renderer/services/contracts';
import type { CandidateReviewResult } from '../../src/renderer/domain/candidates';
import type { ContactVerification, Profile, Session } from '../../src/renderer/domain/models';
import * as fixtures from './fixtures';

export type VisualState = 'populated' | 'empty' | 'error' | 'loading';
export interface HarnessEvent {sequence: number; operation: string; detail: string}
export function createVisualService(state: VisualState = 'populated', guest = false) {
  let session: Session = guest ? {authenticated: false} : {authenticated: true, userId: fixtures.TEST_USER};
  let profiles = structuredClone([fixtures.profile]);
  let opportunities = structuredClone([fixtures.opportunity]);
  let followups = structuredClone(fixtures.followups);
  let tasks = structuredClone(fixtures.tasks);
  const events: HarnessEvent[] = [];
  const record = (operation: string, detail = 'TEST 内存操作；未调用外部服务') => {
    events.push({sequence: events.length + 1, operation, detail});
  };
  const read = async <T,>(operation: string, value: T, empty: T): Promise<T> => {
    record(operation);
    if (state === 'error') throw new ServiceError('VISUAL_TEST_ERROR', 'TEST 服务失败状态（隔离夹具）', 503);
    if (state === 'loading') return new Promise<T>(() => {});
    return structuredClone(state === 'empty' ? empty : value);
  };
  const findOpportunity = (id: string) => {
    const row = opportunities.find(item => item.id === id);
    if (!row) throw new ServiceError('NOT_FOUND', 'TEST 记录不存在', 404);
    return structuredClone(row);
  };
  const sessionWrite = (name: string) => {
    record(name);
    if (!session.authenticated) throw new ServiceError('UNAUTHORIZED', 'TEST 请先登录', 401);
    if (state === 'error') throw new ServiceError('VISUAL_TEST_ERROR', 'TEST 保存失败；输入保留', 503);
  };
  const service: YikeService = {
    session: async () => structuredClone(session),
    loginToken: async () => {record('loginToken', 'TEST 不记录或验证输入凭证'); return session = {authenticated: true, userId: fixtures.TEST_USER};},
    login: async () => {record('login', 'TEST 不发送短信'); return session = {authenticated: true, userId: fixtures.TEST_USER};},
    requestCode: async () => {record('requestCode', 'TEST 未发送短信'); return {retryAfter: 60};},
    logout: async () => {record('logout'); session = {authenticated: false};},
    profiles: () => read('profiles', profiles, []),
    saveProfile: async fields => {
      sessionWrite('saveProfile');
      const saved: Profile = {id: `TEST-profile-v${profiles.length + 1}`, version: profiles.length + 1, status: 'DRAFT', fields: structuredClone(fields), description: 'TEST 内存画像'};
      profiles = [saved, ...profiles]; return structuredClone(saved);
    },
    confirmProfile: async id => {sessionWrite('confirmProfile'); const p = profiles.find(item => item.id === id); if (!p) throw new ServiceError('NOT_FOUND', 'TEST 画像不存在', 404); p.status = 'CONFIRMED'; return structuredClone(p);},
    opportunities: () => read('opportunities', opportunities, []),
    opportunity: async id => {
      if (state === 'empty') throw new ServiceError('NOT_FOUND', 'TEST 记录不存在', 404);
      return read('opportunity', findOpportunity(id), findOpportunity(id));
    },
    followups: () => read('followups', followups, []),
    addFollowup: async (id, status, note) => {sessionWrite('addFollowup'); const row = findOpportunity(id); followups.push({id: `TEST-followup-${followups.length + 1}`, opportunityId: id, title: row.title, status, note, kind: 'manual', createdAt: fixtures.TEST_TIME});},
    connections: () => read('connections', fixtures.connections, []),
    connect: async platform => {record('connect', `TEST ${platform}；未打开登录窗口`);},
    checkConnection: async platform => {record('checkConnection'); const c = fixtures.connections.find(item => item.platform === platform); if (!c) throw new ServiceError('NOT_FOUND', 'TEST 平台不存在'); return structuredClone(c);},
    disconnect: async platform => {record('disconnect', `TEST ${platform}；未改变任何真实账号`);},
    suggest: async (profileId, requestId, signal) => {record('suggest', 'TEST 固定建议；未调用模型'); if (signal?.aborted) throw new DOMException('Aborted', 'AbortError'); return read('suggest-result', {profileId, requestId, keywords: fixtures.KEYWORDS, exclusions: fixtures.EXCLUSIONS}, {profileId, requestId, keywords: [], exclusions: []});},
    tasks: () => read('tasks', tasks, []),
    startTask: async () => {record('startTask', 'TEST 拦截启动，无执行器'); throw new ServiceError('CAPABILITY_UNAVAILABLE', 'TEST 不启动真实或模拟执行器', 501);},
    taskAction: async (id, action) => {sessionWrite('taskAction'); const task = tasks.find(item => item.id === id); if (!task) throw new ServiceError('NOT_FOUND', 'TEST 任务不存在', 404); task.status = {pause: 'PAUSED', resume: 'RUNNING', cancel: 'CANCELED', retry: 'RETRYING'}[action];},
    generateContact: async () => {record('generateContact', 'TEST 固定草稿；未调用模型'); return fixtures.opportunity.comment;},
    saveContact: async () => {sessionWrite('saveContact');},
    verifyContact: async (draft, fingerprint): Promise<ContactVerification> => {
      record('verifyContact', 'TEST 收件人未授权，禁止发送');
      return {allowed: false, fingerprint, confirmationToken: '', expiresAt: '', opportunityId: draft.opportunityId, accountId: draft.accountId, channel: draft.channel, recipientId: '', recipientLabel: 'TEST 无真实收件人', reason: 'TEST 视觉夹具禁止消息发送'};
    },
    send: async () => {record('send', 'TEST 拦截发送'); throw new ServiceError('CAPABILITY_UNAVAILABLE', 'TEST 消息没有发送', 501);},
    activate: async () => {record('activate', 'TEST 不激活真实授权'); throw new ServiceError('CAPABILITY_UNAVAILABLE', 'TEST 无真实授权服务', 501);},
    checkUpdate: async () => {record('checkUpdate'); return {available: false};},
    info: async () => ({version: '0.2.0-TEST', platform: 'darwin', serviceConfigured: false, deviceReady: false}),
    openExternal: async () => {record('openExternal', 'TEST 已拦截外链；未打开浏览器');},
    copy: async text => {record('copy', `TEST 仅记录 ${text.length} 个字符的复制请求；未修改剪贴板`);},
    candidates: query => {
      const item = structuredClone(fixtures.candidate);
      const matches = (!query?.query || item.title.includes(query.query)) && (!query?.platform || item.platform === query.platform) && (!query?.status || item.status === query.status);
      return read('candidates', {items: matches ? [item] : [], total: matches ? 1 : 0, page: query?.page || 1, pageSize: query?.pageSize || 20}, {items: [], total: 0, page: 1, pageSize: 20});
    },
    reviewCandidate: async (review): Promise<CandidateReviewResult> => {
      sessionWrite('reviewCandidate');
      if (review.action !== 'ASSESS') throw new ServiceError('CAPABILITY_UNAVAILABLE', 'TEST 不将候选导入客户库', 501);
      return {kind: 'assessment', requestId: review.requestId, candidateId: review.candidateId, assessment: {...structuredClone(fixtures.candidate.assessment!), profileId: review.profileId, profileVersion: review.profileVersion}};
    },
  };
  return {service, events, record};
}
