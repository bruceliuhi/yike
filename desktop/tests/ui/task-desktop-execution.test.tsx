// @vitest-environment jsdom
import {cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {TaskWizardPage} from '../../src/renderer/pages/TaskWizard';
import {clearLocalDrafts} from '../../src/renderer/app/hooks';
import type {AppContextValue} from '../../src/renderer/app/context';
import {EMPTY_PROFILE, newTaskDraft, type TaskDraft} from '../../src/renderer/domain/models';
import {parseRoute} from '../../src/renderer/domain/routes';
import {strategyPrepareRequest} from '../../src/renderer/domain/researchStrategies';
import type {StrategyReceipt} from '../../src/shared/researchStrategies';
import {executionOperationSchema, type ExecutionOperation} from '../../src/shared/executionOperation';
import type {DesktopExecutionCommand, DesktopExecutionResult} from '../../src/shared/desktopExecution';
import {defaultResearchSettings} from '../../src/renderer/domain/researchUsage';
import {RESEARCH_RUNTIME_SOURCE_LABEL,type ResearchRuntimeCapability} from '../../src/shared/researchRuntime';
import {taskDraftOwner} from '../../src/renderer/app/taskDraft';
import {dynamicCapability} from '../fixtures/dynamicResearch';

let context: AppContextValue;
let prepared: StrategyReceipt;
const recheck = vi.fn(async () => true);
vi.mock('../../src/renderer/app/context', () => ({useApp: () => context}));
vi.mock('../../src/renderer/pages/tasks/useStrategyConfirmation', () => ({useStrategyConfirmation: () => ({
  available: true, busy: false, error: '', prepared, historyReceipt: null, historyOnly: false, confirmed: true,
  pending: false, view: {is_current: true, profile_current: true, state: 'CONFIRMED'},
  prepare: vi.fn(), confirm: vi.fn(), revoke: vi.fn(), reconcile: vi.fn(), retry: vi.fn(), recheck,
})}));
let draft: TaskDraft;
let requests: ExecutionOperation[];
let execute: ReturnType<typeof vi.fn<(command: DesktopExecutionCommand) => Promise<DesktopExecutionResult>>>;
beforeEach(() => {
  clearLocalDrafts(); sessionStorage.clear(); localStorage.clear(); recheck.mockClear();
  draft = {...newTaskDraft(), name: '执行入口合成验证', profileId: crypto.randomUUID(), profileVersion: 1,
    terms: [{id: 'keyword', value: '采购', origin: 'manual', edited: false}], platforms: ['web'], accounts: {},
    executionLimits: {max_records: 10, max_runtime_seconds: 60}};
  const request = strategyPrepareRequest(draft, crypto.randomUUID(), draft.executionLimits! as {max_records: number; max_runtime_seconds: number});
  const strategyId = crypto.randomUUID();
  prepared = {schema_version: 'strategy-confirmation-v1', operation: 'PREPARE', request_id: request.request_id,
    strategy_version_id: strategyId, draft_id: draft.id, draft_revision: draft.revision, profile_version_id: draft.profileId,
    profile_sha256: 'a'.repeat(64), configuration_sha256: 'b'.repeat(64), state: 'DRAFT', recorded_at: '2026-09-10T00:00:00Z',
    snapshot: {strategy_version_id: strategyId, profile_version_id: draft.profileId, configuration: request.configuration,
      platforms: request.platforms, max_records: 10, max_runtime_seconds: 60}};
  requests = [];
  execute = vi.fn(async command => {
    if (command.action === 'LIST') return {state: 'LIST', requests};
    if(command.action==='RESEARCH_LIST')return {state:'RESEARCH_LIST',requests:[]};
    if (command.action === 'START') requests.push(executionOperationSchema.parse({schema_version: 'execution-runtime-v1',
      request_id: command.requestId, operation: 'START', device_id: draft.profileId, credential_version: 1,
      profile_version_id: command.profileVersionId, strategy_version_id: command.strategyVersionId,
      configuration_sha256: command.configurationSha256, targets: command.targets}));
    return 'requestId' in command?{state: 'UNKNOWN', requestId: command.requestId}:{state:'FAILED',error:'EXECUTION_SESSION_FAILED'};
  });
  context = {service: {execution: {execute}, profiles: vi.fn().mockResolvedValue([{id: draft.profileId, version: 1,
    status: 'CONFIRMED', description: '', fields: {...EMPTY_PROFILE, service: '合成服务'}}]),
    connections: vi.fn().mockResolvedValue([{platform: 'web', status: 'CONNECTED', capabilities: ['search'],publicBinding:{sourceId:'v2ex-latest-v1',deviceId:draft.profileId}}]),
    info: vi.fn().mockResolvedValue({version: 'test', platform: 'test', deviceReady: true}), startTask: vi.fn()},
    session: {authenticated: true, userId: crypto.randomUUID()}, sessionReady: true,
    route: parseRoute('#/tasks/new?step=confirm'), navigate: vi.fn(), notify: vi.fn()} as unknown as AppContextValue;
  sessionStorage.setItem('yike.ui.draft.v1.task.' + context.session.userId, JSON.stringify(draft));
});
afterEach(cleanup);
async function review() {
  await waitFor(() => expect(execute).toHaveBeenCalledWith({action: 'LIST'}));
  fireEvent.click(screen.getByRole('checkbox', {name: '我已核对以上业务画像、搜索条件、账号与运行设置'}));
}
describe('original TaskWizard signed execution entry', () => {
  it.each(['RECORDED', 'UNKNOWN'] as const)('opens the ordinary task only after a confirmed receipt (%s)', async state => {
    const taskId = crypto.randomUUID();
    execute.mockImplementation(async command => {
      if (command.action === 'LIST') return {state: 'LIST', requests: []};
      if (command.action === 'START') return state === 'UNKNOWN'
        ? {state: 'UNKNOWN', requestId: command.requestId}
        : {state: 'RECORDED', receipt: {schema_version: 'execution-runtime-v1', request_id: command.requestId,
          operation: 'START', task_id: taskId, run_id: crypto.randomUUID(), status: 'PENDING', stop_confirmed: false,
          platform_runs: [{platform: 'PUBLIC_WEB', platform_run_id: crypto.randomUUID(), status: 'PENDING'}]}};
      return {state: 'FAILED', error: 'EXECUTION_SESSION_FAILED'};
    });
    render(<TaskWizardPage />); await review();
    const start = screen.getByRole('button', {name: '确认并启动'}) as HTMLButtonElement;
    await waitFor(() => expect(start.disabled).toBe(false));
    fireEvent.click(start);
    await waitFor(() => expect(execute.mock.calls.filter(([command]) => command.action === 'START')).toHaveLength(1));
    if (state === 'RECORDED') {
      await waitFor(() => expect(context.navigate).toHaveBeenCalledWith(`/collection?task=${taskId}`));
      const next = JSON.parse(sessionStorage.getItem('yike.ui.draft.v1.task.' + context.session.userId)!);
      expect(next.id).not.toBe(draft.id);
      expect(next.name).toBe('');
      expect(next.research).toEqual(defaultResearchSettings());
    }
    else {
      await screen.findByRole('button', {name: '查询原执行请求'});
      expect(context.navigate).not.toHaveBeenCalled();
      expect(JSON.parse(sessionStorage.getItem('yike.ui.draft.v1.task.' + context.session.userId)!).id).toBe(draft.id);
    }
  });
  it('shows bounded public scope and refuses a changed device after explicit confirmation',async()=>{
    render(<TaskWizardPage />);await review();
    expect(screen.getByText('V2EX最新主题 · 近期主题有界抽样，不覆盖历史/全站/评论')).toBeTruthy();
    const start=screen.getByRole('button',{name:'确认并启动'}) as HTMLButtonElement;
    await waitFor(()=>expect(start.disabled).toBe(false));
    vi.mocked(context.service.connections).mockResolvedValue([{platform:'web',status:'CONNECTED',capabilities:['search'],publicBinding:{sourceId:'v2ex-latest-v1',deviceId:crypto.randomUUID()}}]);
    fireEvent.click(start);
    await screen.findByText(/公开读取范围或执行设备已变化/);
    expect(requests).toHaveLength(0);
  });
  it('makes only the exact foreground registered account selectable without removing its registration', async () => {
    draft.platforms=['xhs']; draft.accounts={};
    context.route=parseRoute('#/tasks/new?step=connect');
    const connectionId=crypto.randomUUID(), deviceId=crypto.randomUUID();
    const account={platform:'xhs' as const,status:'CONNECTED' as const,accountId:'account01',capabilities:['search'],
      registration:{connectionId,deviceId,version:2,connectedAt:'2026-09-10T00:00:00Z',disconnectedAt:null},
      foregroundBinding:{mode:'xhs-foreground-v1' as const,platform:'XIAOHONGSHU' as const,connectionId,connectionVersion:2,deviceId,accountPublicId:'account01'}};
    vi.mocked(context.service.connections).mockResolvedValue([{...account,accountId:'account02',foregroundBinding:undefined,
      registration:{...account.registration,connectionId:crypto.randomUUID()}},account]);
    sessionStorage.setItem('yike.ui.draft.v1.task.'+context.session.userId,JSON.stringify(draft));
    render(<TaskWizardPage />);
    const select=await screen.findByRole('combobox',{name:'小红书执行账号'});
    const ready=await screen.findByRole('option',{name:'小红书账号2'}) as HTMLOptionElement;
    expect(ready.disabled).toBe(false);
    expect(ready.value).toBe('account01');
    expect((screen.getByRole('option',{name:'小红书账号1（当前不可用）'}) as HTMLOptionElement).disabled).toBe(true);
    expect(select.textContent).not.toMatch(/account01|account02/);
    fireEvent.change(select,{target:{value:'account01'}});
    expect(account.registration.connectionId).toBe(connectionId);
  });
  it('uses original confirm button, rechecks prerequisites, and preserves unknown UUID across remount', async () => {
    const view = render(<TaskWizardPage />);
    await review();
    const start = screen.getByRole('button', {name: '确认并启动'}) as HTMLButtonElement;
    await waitFor(() => expect(start.disabled).toBe(false));
    fireEvent.click(start);
    await waitFor(() => expect(requests).toHaveLength(1));
    expect(recheck).toHaveBeenCalledTimes(1);
    expect(context.service.startTask).not.toHaveBeenCalled();
    expect(context.service.connections).toHaveBeenCalledTimes(2);
    await waitFor(() => expect(start.disabled).toBe(true));
    const originalId = requests[0].request_id;
    view.unmount(); render(<TaskWizardPage />);
    await screen.findByRole('button',{name:'查询原执行请求'});
    expect(screen.queryByText(originalId)).toBeNull();
    fireEvent.click(screen.getByRole('button', {name: '查询原执行请求'}));
    await waitFor(() => expect(execute).toHaveBeenLastCalledWith({action: 'RECOVER', requestId: originalId}));
    expect(execute.mock.calls.filter(([value]) => value.action === 'START')).toHaveLength(1);
  });
  it('keeps runtime NOT_READY blocked even when strategy and device identity are ready', async () => {
    vi.mocked(context.service.info).mockResolvedValue({version: 'test', platform: 'test', serviceConfigured: true, deviceReady: false});
    requests.push(executionOperationSchema.parse({schema_version: 'execution-runtime-v1', request_id: crypto.randomUUID(), operation: 'START',
      device_id: draft.profileId, credential_version: 1, profile_version_id: draft.profileId,
      strategy_version_id: prepared.strategy_version_id, configuration_sha256: prepared.configuration_sha256,
      targets: [{platform: 'PUBLIC_WEB', access_mode: 'PUBLIC_ANONYMOUS', connection_id: null, connection_version: null}]}));
    render(<TaskWizardPage />); await review();
    expect((screen.getByRole('button', {name: '确认并启动'}) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText('执行设备尚未绑定或当前不可用。')).toBeTruthy();
    expect((screen.getByRole('checkbox', {name: /我确认核对后重试此原启动请求/}) as HTMLInputElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole('button', {name: '查询原执行请求'}));
    await waitFor(() => expect(execute).toHaveBeenLastCalledWith({action: 'RECOVER', requestId: requests[0].request_id}));
    expect(execute.mock.calls.filter(([value]) => value.action === 'START')).toHaveLength(0);
  });
  it('cannot start or retry when history LIST fails, without assuming empty history', async () => {
    execute.mockResolvedValue({state: 'FAILED', error: 'EXECUTION_SESSION_FAILED'});
    render(<TaskWizardPage />); await review();
    await screen.findByText(/执行响应未核实，原请求已保留/);
    expect((screen.getByRole('button', {name: '确认并启动'}) as HTMLButtonElement).disabled).toBe(true);
    expect(execute.mock.calls.every(([command]) => command.action === 'LIST'||command.action==='RESEARCH_LIST')).toBe(true);
  });
  it('labels PENDING accurately and requires separate explicit task cancellation confirmation', async () => {
    execute.mockImplementation(async command => {
      if (command.action === 'LIST') return {state: 'LIST', requests: []};
      if(command.action==='RESEARCH_LIST')return {state:'RESEARCH_LIST',requests:[]};
      if (command.action === 'START') return {state: 'RECORDED', receipt: {schema_version: 'execution-runtime-v1',
        request_id: command.requestId, operation: 'START', task_id: draft.profileId, run_id: crypto.randomUUID(), status: 'PENDING',
        stop_confirmed: false, platform_runs: [{platform: 'PUBLIC_WEB', platform_run_id: crypto.randomUUID(), status: 'PENDING'}]}};
      return 'requestId' in command?{state: 'UNKNOWN', requestId: command.requestId}:{state:'FAILED',error:'EXECUTION_SESSION_FAILED'};
    });
    render(<TaskWizardPage />); await review();
    const start = screen.getByRole('button', {name: '确认并启动'}) as HTMLButtonElement;
    await waitFor(() => expect(start.disabled).toBe(false)); fireEvent.click(start);
    await screen.findByText(/任务已创建，当时待执行；不是当前任务状态/);
    const region = screen.getByRole('region', {name: '本机原执行请求'});
    const cancel = within(region).getByRole('button', {name: '确认取消此任务'}) as HTMLButtonElement;
    expect(cancel.disabled).toBe(true);
    fireEvent.click(within(region).getByRole('checkbox', {name: /我确认取消此任务/}));
    fireEvent.click(cancel);
    await waitFor(() => expect(execute.mock.calls.filter(([value]) => value.action === 'CANCEL')).toHaveLength(1));
    fireEvent.click(cancel);
    expect(execute.mock.calls.filter(([value]) => value.action === 'CANCEL')).toHaveLength(1);
  });
  it.each([
    {source:'v2ex-latest-v1',changed:false,plan:false},{source:'v2ex-qna-v1',changed:false,plan:false},
    {source:'v2ex-outsourcing-authors-v1',changed:false,plan:false},{source:'v2ex-qna-v1',changed:true,plan:false},
    {source:'v2ex-qna-v1',changed:false,plan:true},{source:'v2ex-qna-v1',changed:true,plan:true},
    {source:'v2ex-qna-v1',changed:'binding',plan:true},
  ] as const)('starts selected $source only while its fresh capability remains available ($changed, plan $plan)',async({source,changed,plan})=>{
    draft={...draft,publicSource:source,research:{...defaultResearchSettings(),maxSoubei:20,limits:{sources:2,minutes:3,modelCalls:4},
      ...(plan?{sourcePlan:{version:1 as const,sources:[source,'v2ex-outsourcing-authors-v1' as const]}}:{})}};
    const strategyRequest=strategyPrepareRequest(draft,prepared.request_id,{max_records:10,max_runtime_seconds:60});
    prepared={...prepared,draft_revision:draft.revision,snapshot:{...prepared.snapshot,configuration:strategyRequest.configuration,platforms:strategyRequest.platforms}};
    const calls:DesktopExecutionCommand[]=[];execute=vi.fn(async command=>{calls.push(structuredClone(command));if(command.action==='LIST')return {state:'LIST',requests:[]};
      if(command.action==='RESEARCH_LIST')return {state:'RESEARCH_LIST',requests:[]};return 'requestId'in command?{state:'UNKNOWN',requestId:command.requestId}:{state:'FAILED',error:'EXECUTION_SESSION_FAILED'};});
    const legacy:ResearchRuntimeCapability={contractVersion:1,sourceScope:'V2EX_LATEST_INDEX',sourceLabel:RESEARCH_RUNTIME_SOURCE_LABEL,maxFreshEffectsPerAdvance:1,settlementState:'PENDING'};
    const capability=vi.fn<()=>Promise<ResearchRuntimeCapability>>().mockResolvedValue(plan?{contractVersion:3,sourceScope:'V2EX_INDEX_PLAN',sourceLabel:'V2EX多板块 · 有界来源计划',
      sourceIds:['v2ex-latest-v1','v2ex-qna-v1','v2ex-outsourcing-authors-v1'],maxPlannedSources:3,maxFreshEffectsPerAdvance:1,settlementState:'PENDING'}:source==='v2ex-latest-v1'?legacy:{contractVersion:2,sourceScope:'V2EX_SELECTED_INDEX',sourceLabel:'V2EX定向板块 · 单源索引研究',
      sourceIds:['v2ex-latest-v1','v2ex-qna-v1','v2ex-outsourcing-authors-v1'],maxFreshEffectsPerAdvance:1,settlementState:'PENDING'});
    vi.mocked(context.service.connections).mockResolvedValue([{platform:'web',status:'CONNECTED',capabilities:['search'],publicBinding:{sourceId:'v2ex-latest-v1',sourceIds:['v2ex-latest-v1','v2ex-qna-v1','v2ex-outsourcing-authors-v1'],deviceId:draft.profileId}}]);
    context={...context,session:{...context.session,accountScope:{id:crypto.randomUUID(),version:1}},service:{...context.service,execution:{researchContractVersion:1,execute},researchRuntime:{capability,status:vi.fn(),advance:vi.fn()},
      researchUsage:{requiresConfirmedStrategy:true,quote:vi.fn(async input=>({...input,quoteId:crypto.randomUUID(),ruleVersion:'test-v1',ruleSha256:'c'.repeat(64),authorizationToken:'abc.def',
        estimatedSoubei:5,generatedAt:new Date(Date.now()-1000).toISOString(),expiresAt:new Date(Date.now()+60_000).toISOString(),basis:'TEST only'}))}}};
    sessionStorage.setItem('yike.ui.draft.v1.task.'+taskDraftOwner(context.session.userId,context.session.accountScope),JSON.stringify(draft));render(<TaskWizardPage/>);
    fireEvent.click(await screen.findByRole('button',{name:'重新估算'}));await screen.findByText('5 搜贝');await review();
    if(plan){expect(screen.getByRole('table',{name:'已确认来源配额'})).toBeTruthy();
      expect(prepared.snapshot.configuration.research?.sourcePlan?.sources).toEqual([source,'v2ex-outsourcing-authors-v1']);}
    if(source==='v2ex-qna-v1'&&!plan)expect(screen.getByText('V2EX问与答 · 单源索引研究（未读评论）')).toBeTruthy();
    if(source==='v2ex-outsourcing-authors-v1')expect(screen.getByText('V2EX项目外包 · 单源索引研究（未读作者回复）')).toBeTruthy();
    const start=screen.getByRole('button',{name:'确认并启动'}) as HTMLButtonElement;await waitFor(()=>expect(start.disabled).toBe(false));
    if(changed==='binding')vi.mocked(context.service.connections).mockResolvedValue([{platform:'web',status:'CONNECTED',capabilities:['search'],
      publicBinding:{sourceId:'v2ex-latest-v1',sourceIds:['v2ex-latest-v1','v2ex-qna-v1'],deviceId:draft.profileId}}]);
    else if(changed)capability.mockResolvedValue(legacy);
    fireEvent.click(start);
    if(changed){
      await screen.findByText(changed==='binding'?/公开读取范围或执行设备已变化/:/所选板块研究能力已变化/);
      expect(calls.some(command=>command.action==='RESEARCH_START')).toBe(false);
      return;
    }
    await waitFor(()=>expect(calls.some(command=>command.action==='RESEARCH_START')).toBe(true));const research=calls.find(command=>command.action==='RESEARCH_START')!;
    expect(research).toMatchObject({action:'RESEARCH_START',authorizationToken:'abc.def',reservation:{limits:{sources:2,minutes:3,modelCalls:4}}});
    for(const storage of [localStorage,sessionStorage])for(let index=0;index<storage.length;index++)
      expect(storage.getItem(storage.key(index)!)).not.toContain('abc.def');
  });
  it.each(['unknown','recorded','changed'] as const)('starts dynamic research without local public binding and rechecks service availability (%s)',async(outcome)=>{
    const changed=outcome==='changed';
    const taskId=crypto.randomUUID();
    if(outcome==='recorded')execute.mockImplementation(async command=>{
      if(command.action==='LIST')return {state:'LIST',requests:[]};
      if(command.action==='RESEARCH_LIST')return {state:'RESEARCH_LIST',requests:[]};
      if(command.action==='RESEARCH_START')return {state:'RESEARCH_RECORDED',receipt:{schema_version:'research-execution-v1',
        execution:{schema_version:'execution-runtime-v1',request_id:command.requestId,operation:'START',task_id:taskId,
          run_id:crypto.randomUUID(),status:'PENDING',stop_confirmed:false,
          platform_runs:[{platform:'PUBLIC_WEB',platform_run_id:crypto.randomUUID(),status:'PENDING'}]},
        reservation:{...command.reservation,reservation_id:crypto.randomUUID(),status:'RESERVED'}}};
      return {state:'FAILED',error:'EXECUTION_SESSION_FAILED'};
    });
    draft={...draft,publicSource:'public-web-agent-v1',research:{...defaultResearchSettings(),maxSoubei:20,
      limits:{sources:20,minutes:15,modelCalls:20},dynamicScope:{version:1,maxAgeDays:60,timezone:'Asia/Shanghai'}}};
    const request=strategyPrepareRequest(draft,prepared.request_id,{max_records:10,max_runtime_seconds:60});
    prepared={...prepared,snapshot:{...prepared.snapshot,configuration:request.configuration}};
    const capability=vi.fn().mockResolvedValue(dynamicCapability);
    vi.mocked(context.service.connections).mockResolvedValue([]);
    context={...context,session:{...context.session,accountScope:{id:crypto.randomUUID(),version:1}},service:{...context.service,
      execution:{researchContractVersion:1,execute},researchRuntime:{capability,status:vi.fn(),advance:vi.fn()},
      researchUsage:{requiresConfirmedStrategy:true,quote:vi.fn(async input=>({...input,quoteId:crypto.randomUUID(),ruleVersion:'test-v1',ruleSha256:'c'.repeat(64),
        authorizationToken:'abc.def',estimatedSoubei:5,generatedAt:new Date(Date.now()-1000).toISOString(),
        expiresAt:new Date(Date.now()+60_000).toISOString(),basis:'TEST only'}))}}};
    sessionStorage.setItem('yike.ui.draft.v1.task.'+taskDraftOwner(context.session.userId,context.session.accountScope),JSON.stringify(draft));
    render(<TaskWizardPage/>);
    fireEvent.click(await screen.findByRole('button',{name:'重新估算'}));await screen.findByText('5 搜贝');await review();
    expect(screen.queryByText(/关键词仅筛选本次近期主题样本/)).toBeNull();
    const start=screen.getByRole('button',{name:'确认并启动'}) as HTMLButtonElement;
    await waitFor(()=>expect(start.disabled).toBe(false));
    if(changed)capability.mockResolvedValue({contractVersion:1,sourceScope:'V2EX_LATEST_INDEX',sourceLabel:RESEARCH_RUNTIME_SOURCE_LABEL,
      maxFreshEffectsPerAdvance:1,settlementState:'PENDING'});
    fireEvent.click(start);
    if(changed){await screen.findByText(/所选板块研究能力已变化/);expect(execute.mock.calls.some(([c])=>c.action==='RESEARCH_START')).toBe(false);}
    else {
      await waitFor(()=>expect(execute.mock.calls.some(([c])=>c.action==='RESEARCH_START')).toBe(true));
      if(outcome==='recorded')await waitFor(()=>expect(context.navigate).toHaveBeenCalledWith(`/collection?task=${taskId}`));
      else {await waitFor(()=>expect(start.disabled).toBe(true));expect(context.navigate).not.toHaveBeenCalled();}
      expect(execute.mock.calls.filter(([c])=>c.action==='RESEARCH_START')).toHaveLength(1);
    }
    const nextDraft = JSON.parse(sessionStorage.getItem('yike.ui.draft.v1.task.' + taskDraftOwner(context.session.userId, context.session.accountScope))!);
    if (outcome === 'recorded') {
      expect(nextDraft.id).not.toBe(draft.id);
      expect(nextDraft.name).toBe('');
      expect(nextDraft.research).toEqual(defaultResearchSettings());
    } else expect(nextDraft.id).toBe(draft.id);
  });
  it('blocks native research when the explicit backend capability is unavailable',async()=>{
    draft={...draft,research:{...defaultResearchSettings(),maxSoubei:20}};sessionStorage.setItem('yike.ui.draft.v1.task.'+context.session.userId,JSON.stringify(draft));
    context={...context,service:{...context.service,execution:{researchContractVersion:1,execute},researchRuntime:undefined}};
    render(<TaskWizardPage/>);await screen.findByText(/研究用量服务尚未接通/);
    expect((screen.getByRole('button',{name:'确认并启动'}) as HTMLButtonElement).disabled).toBe(true);
    expect(execute.mock.calls.some(([command])=>command.action==='RESEARCH_START')).toBe(false);
  });
});
