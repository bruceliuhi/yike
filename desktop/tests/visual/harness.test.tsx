// @vitest-environment jsdom
import {afterEach, describe, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {AppProvider} from '../../src/renderer/app/context';
import {TasksPage} from '../../src/renderer/pages/Tasks';
import {FollowupsPage} from '../../src/renderer/pages/Followups';
import {OutreachPage} from '../../src/renderer/pages/Outreach';
import {createVisualService} from './service';
import {MemoryStorage} from './isolation';
import {EXCLUSIONS, KEYWORDS, opportunity, profile, taskDraft} from './fixtures';

afterEach(() => {cleanup(); vi.restoreAllMocks();});
describe('strictly separate visual service', () => {
  it('supplies all three TEST outreach queues without enabling send or claiming a receipt', async () => {
    const harness = createVisualService();
    for (const queue of ['confirm', 'reply', 'issues'] as const) {
      expect((await harness.service.outreach!.queue(queue)).items[0].title).toContain('TEST');
      expect((await createVisualService('empty').service.outreach!.queue(queue)).items).toEqual([]);
    }
    const draft = {opportunityId: opportunity.id, channel: 'comment' as const, content: 'TEST', version: 1, savedContent: 'TEST', accountId: 'TEST-account', recipient: 'TEST-recipient'};
    await expect(harness.service.outreach!.send(draft, {requestId: 'TEST-request', confirmationToken: 'TEST-token'})).rejects.toMatchObject({code: 'CAPABILITY_UNAVAILABLE'});
    expect((await harness.service.outreach!.reconcile({requestId: 'TEST-request', opportunityId: opportunity.id, channel: 'comment', version: 1})).status).toBe('UNKNOWN');
  });
  it('keeps writes in one service instance and never calls network or clipboard', async () => {
    const network = vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('must not reach network'));
    const a = createVisualService(); const b = createVisualService();
    await a.service.addFollowup(opportunity.id, 'CONTACTED', 'TEST memory-only');
    expect(await a.service.followups()).toHaveLength(3);
    expect(await b.service.followups()).toHaveLength(2);
    await a.service.copy('TEST clipboard'); await a.service.openExternal('https://external.invalid');
    expect(a.events.map(x => x.operation)).toContain('copy');
    expect(a.events.map(x => x.operation)).toContain('openExternal');
    expect(network).not.toHaveBeenCalled();
  });
  it('returns deep copies so view edits cannot mutate fixture or other reads', async () => {
    const {service} = createVisualService(); const first = await service.tasks();
    first[2].platformStages![0].reason = 'changed';
    expect((await service.tasks())[2].platformStages![0].reason).toContain('TEST');
  });
  it('never permits execution or sending, even when directly invoked', async () => {
    const {service, events} = createVisualService();
    await expect(service.startTask(taskDraft('monitor'), 'TEST-request')).rejects.toMatchObject({code: 'CAPABILITY_UNAVAILABLE'});
    const draft = {opportunityId: opportunity.id, channel: 'comment' as const, content: 'TEST', version: 1, savedContent: 'TEST', accountId: 'TEST-account', recipient: 'TEST-recipient'};
    expect((await service.verifyContact(draft, 'TEST-fingerprint')).allowed).toBe(false);
    await expect(service.send(draft, 'TEST-token')).rejects.toMatchObject({code: 'CAPABILITY_UNAVAILABLE'});
    expect(events.map(e => e.operation)).toEqual(['startTask', 'verifyContact', 'send']);
  });
  it('rejects memory mutation in the guest and failure scenarios', async () => {
    await expect(createVisualService('populated', true).service.saveProfile(profile.fields)).rejects.toMatchObject({code: 'UNAUTHORIZED'});
    await expect(createVisualService('error').service.addFollowup(opportunity.id, 'CONTACTED', 'TEST')).rejects.toMatchObject({code: 'VISUAL_TEST_ERROR'});
    expect(await createVisualService('empty').service.tasks()).toEqual([]);
  });
  it('models task action states only in memory without an executor', async () => {
    const {service} = createVisualService();
    await service.taskAction('TEST-monitor', 'pause');
    expect((await service.tasks()).find(x => x.id === 'TEST-monitor')?.status).toBe('PAUSED');
    await service.taskAction('TEST-monitor', 'resume');
    expect((await service.tasks()).find(x => x.id === 'TEST-monitor')?.status).toBe('RUNNING');
  });
  it('retains approved 8/4 terms and both monitor times', () => {
    expect(KEYWORDS).toHaveLength(8); expect(EXCLUSIONS).toHaveLength(4);
    expect(taskDraft('monitor').schedule).toMatchObject({times: ['09:00', '15:00'], timezone: 'Asia/Shanghai'});
  });
  it('does not claim platform accounts or a ready executor', async () => {
    const {service} = createVisualService();
    expect((await service.connections()).every(row => row.status !== 'CONNECTED')).toBe(true);
    expect(await service.info()).toMatchObject({serviceConfigured: false, deviceReady: false});
  });
  it('supplies a memory Storage interface without sharing values', () => {
    const a = new MemoryStorage(); const b = new MemoryStorage(); a.setItem('TEST', 'value');
    expect(a.getItem('TEST')).toBe('value'); expect(b.getItem('TEST')).toBeNull();
    expect(a.key(0)).toBe('TEST'); a.clear(); expect(a.length).toBe(0);
  });
});
describe('real page components with the real AppProvider', () => {
  it('switches the same opportunity from an existing comment route to queue-selected dm through real asynchronous hashchange', async () => {
    history.replaceState(null, '', '#/outreach?opportunity=TEST-opportunity&channel=comment');
    const harness = createVisualService();
    harness.service.session = async () => ({authenticated: true, userId: 'TEST-outreach-route-' + 'real-hash'});
    render(<AppProvider service={harness.service}><OutreachPage /></AppProvider>);
    await screen.findByDisplayValue(opportunity.comment);
    fireEvent.change(screen.getByRole('textbox', {name: '沟通内容'}), {target: {value: 'TEST 已保留的人工评论'}});
    fireEvent.click(screen.getByRole('tab', {name: '待确认'}));
    fireEvent.click(await screen.findByRole('button', {name: /TEST 触达记录 · 待确认/}));
    fireEvent.click(screen.getByRole('button', {name: '查看联系准备'}));
    // No synchronous route mock or manual event dispatch: AppProvider observes
    // the hashchange scheduled by its real navigate() after the queue update.
    await screen.findByDisplayValue(opportunity.dm);
    expect(location.hash).toBe('#/outreach?opportunity=TEST-opportunity&channel=dm');
    expect(screen.getByRole('tab', {name: '草稿箱'}).getAttribute('aria-selected')).toBe('true');
    expect(screen.getByRole('tab', {name: '私信草稿'}).getAttribute('aria-selected')).toBe('true');
    fireEvent.click(screen.getByRole('tab', {name: '评论草稿'}));
    expect((screen.getByRole('textbox', {name: '沟通内容'}) as HTMLTextAreaElement).value).toBe('TEST 已保留的人工评论');
    expect(harness.events.some(event => event.operation === 'send' || event.operation === 'outreach.send')).toBe(false);
  });
  it('renders all five monitor platform states and real detail tabs', async () => {
    location.hash = '#/monitors/TEST-monitor';
    render(<AppProvider service={createVisualService().service}><TasksPage /></AppProvider>);
    await screen.findByText('TEST 平台状态组合示意，非真实运行记录。');
    expect(screen.getByRole('button', {name: '查看小红书状态'})).toBeTruthy();
    fireEvent.click(screen.getByRole('button', {name: '查看抖音状态'}));
    expect(screen.getByText('TEST 限流状态示意，等待平台允许后再执行。')).toBeTruthy();
    fireEvent.click(screen.getByRole('tab', {name: '执行记录'}));
    expect(screen.getByText('TEST 内存事件：测试任务状态载入。')).toBeTruthy();
  });
  it('renders actual task lists from isolated data', async () => {
    location.hash = '#/collection';
    render(<AppProvider service={createVisualService().service}><TasksPage /></AppProvider>);
    await screen.findByText('TEST 展台需求发现');
    expect(screen.queryByText('TEST 展台需求监控')).toBeNull();
  });
  it('renders the real followup drawer against the same isolated service', async () => {
    location.hash = '#/followups?add=1&opportunity=TEST-opportunity';
    const harness = createVisualService();
    render(<AppProvider service={harness.service}><FollowupsPage /></AppProvider>);
    await waitFor(() => expect((screen.getByLabelText('关联商机') as HTMLSelectElement).disabled).toBe(false));
    expect(screen.getByRole('dialog', {name: '添加跟进'})).toBeTruthy();
    expect(screen.getByRole('button', {name: '保存记录'})).toBeTruthy();
    expect(harness.events.some(event => event.operation === 'followups')).toBe(true);
  });
});
