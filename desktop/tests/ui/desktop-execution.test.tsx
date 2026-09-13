// @vitest-environment jsdom
import {act, cleanup, renderHook, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {useDesktopExecution, type DesktopResearchStartCommand, type DesktopStartCommand} from '../../src/renderer/pages/tasks/useDesktopExecution';
import {executionOperationSchema} from '../../src/shared/executionOperation';
import type {StrategyReceipt} from '../../src/shared/researchStrategies';
import type {AppContextValue} from '../../src/renderer/app/context';
import type {DesktopExecutionCommand, DesktopExecutionResult} from '../../src/shared/desktopExecution';
import {createDeviceIdentityController} from '../../src/main/deviceIdentityController';
import {createExecutionSession} from '../../src/main/executionSession';
import {createExecutionController} from '../../src/main/executionController';

let context: AppContextValue;
vi.mock('../../src/renderer/app/context', () => ({useApp: () => context}));
const requestId = '12345678-1234-4234-8234-123456789abc';
const profileId = '22345678-1234-4234-8234-123456789abc';
const strategyId = '32345678-1234-4234-8234-123456789abc';
const taskId = '42345678-1234-4234-8234-123456789abc';
const command: DesktopStartCommand = {action: 'START', humanConfirmed: true, requestId, profileVersionId: profileId,
  strategyVersionId: strategyId, configurationSha256: 'a'.repeat(64),
  targets: [{platform: 'PUBLIC_WEB', access_mode: 'PUBLIC_ANONYMOUS', connection_id: null, connection_version: null}]};
const request = executionOperationSchema.parse({schema_version: 'execution-runtime-v1', request_id: requestId, operation: 'START',
  device_id: profileId, credential_version: 1, profile_version_id: profileId, strategy_version_id: strategyId,
  configuration_sha256: 'a'.repeat(64), targets: command.targets});
const prepared = {profile_version_id: profileId, strategy_version_id: strategyId, configuration_sha256: 'a'.repeat(64)} as StrategyReceipt;
const receipt = {schema_version: 'execution-runtime-v1' as const, request_id: requestId, operation: 'START' as const,
  task_id: taskId, run_id: profileId, status: 'PENDING' as const, stop_confirmed: false as const,
  platform_runs: [{platform: 'PUBLIC_WEB' as const, platform_run_id: strategyId, status: 'PENDING' as const}]};
const researchCommand:DesktopResearchStartCommand={action:'RESEARCH_START',humanConfirmed:true,requestId,profileVersionId:profileId,strategyVersionId:strategyId,
  configurationSha256:'a'.repeat(64),targets:command.targets,reservation:{quote_id:taskId,strategy_version_id:strategyId,profile_version_id:profileId,
    configuration_sha256:'a'.repeat(64),rule_version:'test-v1',rule_sha256:'b'.repeat(64),estimated_soubei:1,max_soubei:2,limits:{sources:1,minutes:1,modelCalls:1}},authorizationToken:'abc.def'};
let execute: ReturnType<typeof vi.fn<(command: DesktopExecutionCommand) => Promise<DesktopExecutionResult>>>;
beforeEach(() => {
  execute = vi.fn(async value => value.action === 'LIST' ? {state: 'LIST', requests: []} : value.action==='RESEARCH_LIST'
    ?{state:'RESEARCH_LIST',requests:[]}:'requestId' in value?{state: 'UNKNOWN', requestId: value.requestId}:{state:'FAILED',error:'EXECUTION_SESSION_FAILED'});
  context = {service: {execution: {researchContractVersion:1,execute}}, session: {authenticated: true, userId: 'user'}, sessionReady: true} as unknown as AppContextValue;
});
afterEach(() => {cleanup(); vi.useRealTimers();});

describe('desktop execution original-request safety', () => {
  it('ignores a recorded research response after the account scope changes',async()=>{
    const hook=renderHook(()=>useDesktopExecution(prepared));
    await waitFor(()=>expect(hook.result.current.loaded).toBe(true));
    let finish!:(value:DesktopExecutionResult)=>void;
    execute.mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;}));
    const onRecorded=vi.fn();let pending!:Promise<void>;
    await act(async()=>{pending=hook.result.current.startResearch(researchCommand,onRecorded);});
    context={...context,session:{authenticated:true,userId:'another-user'}};
    hook.rerender();
    await act(async()=>{
      finish({state:'RESEARCH_RECORDED',receipt:{schema_version:'research-execution-v1',execution:receipt,
        reservation:{...researchCommand.reservation,reservation_id:taskId,status:'RESERVED'}}});
      await pending;
    });
    expect(onRecorded).not.toHaveBeenCalled();
    expect(hook.result.current.entries).toHaveLength(0);
  });
  it('serially loads both journals through the real identity, controller, and session locks',async()=>{
    const researchRequest={...request,request_id:taskId};
    const researchRecord={record_version:2 as const,record_type:'RESEARCH_START' as const,request:researchRequest,reservation:{quote_id:requestId,
      strategy_version_id:strategyId,profile_version_id:profileId,configuration_sha256:'a'.repeat(64),rule_version:'test-v1',rule_sha256:'b'.repeat(64),
      estimated_soubei:1,max_soubei:2,limits:{sources:1,minutes:1,modelCalls:1}}};
    const journal={persist:vi.fn(),read:vi.fn(),list:vi.fn(async()=>[request]),persistResearch:vi.fn(),readResearch:vi.fn(),listResearch:vi.fn(async()=>[researchRecord])};
    const identity=createDeviceIdentityController({service:{request:vi.fn(async()=>({ok:true as const,status:200,data:{authenticated:true,user_id:'user'}})),requestDevice:vi.fn(async()=>({ok:true as const,status:200,data:{}}))},
      identityFactory:()=>({prepare:vi.fn(async()=>({state:'FAILED' as const,error:'DEVICE_IDENTITY_FAILED' as const}))})});
    const session=createExecutionSession({serviceOrigin:'http://127.0.0.1:8000',journal:journal as any,vault:{read:vi.fn(async()=>null)},transport:{requestExecution:vi.fn()}});
    const bridge=createExecutionController({identity,execution:session});
    context={...context,service:{...context.service,execution:{researchContractVersion:1,execute:bridge.execute}}};
    const hook=renderHook(()=>useDesktopExecution(null));
    await waitFor(()=>expect(hook.result.current.loaded).toBe(true));
    expect(journal.list).toHaveBeenCalledTimes(1);expect(journal.listResearch).toHaveBeenCalledTimes(1);
    expect(hook.result.current.entries.map(entry=>entry.kind).sort()).toEqual(['ORDINARY','RESEARCH']);
    expect(JSON.stringify(hook.result.current.entries)).not.toContain('authorizationToken');expect(hook.result.current.error).toBe('');
  });
  it('loads an old bridge without probing research or falling ordinary START back to another command',async()=>{
    context={...context,service:{...context.service,execution:{execute}}};
    const hook=renderHook(()=>useDesktopExecution(prepared));await waitFor(()=>expect(hook.result.current.loaded).toBe(true));
    expect(execute.mock.calls.map(([value])=>value.action)).toEqual(['LIST']);
    await act(async()=>{await hook.result.current.start(command);});
    expect(execute.mock.calls.map(([value])=>value.action)).toEqual(['LIST','START']);
  });
  it('keeps research token only in the invocation and recovers listed original without retry',async()=>{let stored:any=null;
    execute.mockImplementation(async value=>{if(value.action==='LIST')return {state:'LIST',requests:[]};if(value.action==='RESEARCH_LIST')return {state:'RESEARCH_LIST',requests:stored?[stored]:[]};
      if(value.action==='RESEARCH_START'){stored={record_version:2,record_type:'RESEARCH_START',request:{...request},reservation:value.reservation};return {state:'UNKNOWN',requestId:value.requestId};}
      if(value.action==='RESEARCH_RECOVER')return {state:'UNKNOWN',requestId:value.requestId};return {state:'FAILED',error:'EXECUTION_SESSION_FAILED'};});
    const hook=renderHook(()=>useDesktopExecution(prepared));await waitFor(()=>expect(hook.result.current.loaded).toBe(true));
    await act(async()=>{await hook.result.current.startResearch(researchCommand);});const entry=hook.result.current.entries[0];
    expect(entry.kind).toBe('RESEARCH');expect(JSON.stringify(entry)).not.toContain('abc.def');expect(entry.command).toEqual({action:'RESEARCH_RECOVER',requestId});
    await act(async()=>{await hook.result.current.startResearch({...researchCommand,requestId:crypto.randomUUID()});});
    expect(execute.mock.calls.filter(([value])=>value.action==='RESEARCH_START')).toHaveLength(1);
    hook.unmount();const reopened=renderHook(()=>useDesktopExecution(prepared));await waitFor(()=>expect(reopened.result.current.entries).toHaveLength(1));
    await act(async()=>{await reopened.result.current.recover(reopened.result.current.entries[0],true);});
    expect(execute).toHaveBeenLastCalledWith({action:'RESEARCH_RECOVER',requestId});
    expect(execute.mock.calls.filter(([value])=>value.action==='RESEARCH_START')).toHaveLength(1);
  });
  it('cancels a listed task without a local START receipt, preserves unknown and reloads the same cancel', async () => {
    let stored: ReturnType<typeof executionOperationSchema.parse> | undefined;
    execute.mockImplementation(async value => {
      if(value.action==='LIST')return {state:'LIST',requests:stored?[stored]:[]};
      if(value.action==='RESEARCH_LIST')return {state:'RESEARCH_LIST',requests:[]};
      if(value.action==='CANCEL')stored=executionOperationSchema.parse({schema_version:'execution-runtime-v1',
        operation:'CANCEL',request_id:value.requestId,device_id:profileId,credential_version:1,task_id:value.taskId});
      return {state:'UNKNOWN',requestId:value.requestId};
    });
    const hook=renderHook(()=>useDesktopExecution(null));
    await waitFor(()=>expect(hook.result.current.loaded).toBe(true));
    await act(async()=>{await hook.result.current.cancelTask(taskId,false);});
    expect(execute.mock.calls.filter(([c])=>c.action==='CANCEL')).toHaveLength(0);
    await act(async()=>{await hook.result.current.cancelTask(taskId,true);});
    await act(async()=>{await hook.result.current.cancelTask(taskId,true);});
    expect(execute.mock.calls.filter(([c])=>c.action==='CANCEL')).toHaveLength(1);
    hook.unmount();const reopened=renderHook(()=>useDesktopExecution(null));
    await waitFor(()=>expect(reopened.result.current.loaded).toBe(true));
    await act(async()=>{await reopened.result.current.cancelTask(taskId,true);});
    await act(async()=>{await reopened.result.current.recover(reopened.result.current.entries[0]);});
    expect(execute).toHaveBeenLastCalledWith({action:'RECOVER',requestId:stored!.request_id});
    expect(execute.mock.calls.filter(([c])=>c.action==='CANCEL')).toHaveLength(1);
  });
  it('blocks START until LIST succeeds and never treats unreadable LIST as empty history', async () => {
    let finish!: (value: DesktopExecutionResult) => void;
    execute.mockImplementationOnce(() => new Promise(resolve => {finish = resolve;}));
    const hook = renderHook(() => useDesktopExecution(prepared));
    await waitFor(() => expect(execute).toHaveBeenCalledWith({action: 'LIST'}));
    await act(async () => {await hook.result.current.start(command);});
    expect(execute).toHaveBeenCalledTimes(1);
    await act(async () => {finish({state: 'FAILED', error: 'EXECUTION_SESSION_FAILED'});});
    await waitFor(()=>expect(execute).toHaveBeenCalledWith({action:'RESEARCH_LIST'}));
    expect(hook.result.current.loaded).toBe(false);
    await act(async () => {await hook.result.current.start(command);});
    expect(execute).toHaveBeenCalledTimes(2);
  });
  it('keeps original UUID on unknown START and discovers it after remount without another START', async () => {
    let stored = false;
    execute.mockImplementation(async value => {
      if (value.action === 'LIST') return {state: 'LIST', requests: stored ? [request] : []};
      if(value.action==='RESEARCH_LIST')return {state:'RESEARCH_LIST',requests:[]};
      stored = true;
      return {state: 'UNKNOWN', requestId: value.requestId};
    });
    const hook = renderHook(() => useDesktopExecution(prepared));
    await waitFor(() => expect(hook.result.current.loaded).toBe(true));
    await act(async () => {await hook.result.current.start(command);});
    expect(hook.result.current.entries[0].requestId).toBe(requestId);
    await act(async () => {await hook.result.current.start({...command, requestId: crypto.randomUUID()});});
    expect(execute.mock.calls.filter(([value]) => value.action === 'START')).toHaveLength(1);
    hook.unmount();
    const reopened = renderHook(() => useDesktopExecution(prepared));
    await waitFor(() => expect(reopened.result.current.entries).toHaveLength(1));
    expect(reopened.result.current.blocksStart).toBe(true);
    await act(async () => {await reopened.result.current.recover(reopened.result.current.entries[0]);});
    expect(execute).toHaveBeenLastCalledWith({action: 'RECOVER', requestId});
    expect(execute.mock.calls.filter(([value]) => value.action === 'START')).toHaveLength(1);
  });
  it('permits explicit START retry only after current configuration authorization, with same UUID', async () => {
    execute.mockImplementationOnce(async value=>value.action==='LIST'?{state:'LIST',requests:[request]}:{state:'RESEARCH_LIST',requests:[]});
    const hook = renderHook(() => useDesktopExecution(prepared));
    await waitFor(() => expect(hook.result.current.loaded).toBe(true));
    const entry = hook.result.current.entries[0];
    await act(async () => {await hook.result.current.recover(entry, true);});
    expect(execute).toHaveBeenCalledTimes(2);
    await act(async () => {await hook.result.current.recover(entry, true, async () => ({...command, configurationSha256: 'b'.repeat(64)}));});
    expect(execute).toHaveBeenCalledTimes(2);
    await act(async () => {await hook.result.current.recover(entry, true, async () => command);});
    expect(execute).toHaveBeenLastCalledWith({action: 'RECOVER', requestId, retry: true, humanConfirmed: true});
  });
  it('retains the same original UUID after an actual UI timeout and ignores the late response', async () => {
    let finish!: (result: DesktopExecutionResult) => void;
    const hook = renderHook(() => useDesktopExecution(prepared));
    await waitFor(() => expect(hook.result.current.loaded).toBe(true));
    vi.useFakeTimers();
    execute.mockImplementationOnce(() => new Promise(resolve => {finish = resolve;}));
    let pending!: Promise<void>;
    await act(async () => {pending = hook.result.current.start(command);});
    expect(hook.result.current.entries[0].requestId).toBe(requestId);
    await act(async () => {await vi.advanceTimersByTimeAsync(30_001); await pending;});
    expect(hook.result.current.busy).toBe(false);
    expect(hook.result.current.entries[0].state).toBe('UNKNOWN');
    await act(async () => {await hook.result.current.start({...command, requestId: crypto.randomUUID()});});
    expect(execute.mock.calls.filter(([value]) => value.action === 'START')).toHaveLength(1);
    await act(async () => {finish({state: 'RECORDED', receipt});});
    expect(hook.result.current.entries[0].receipt).toBeUndefined();
  });
  it('keeps cancellation UUID before dispatch and never creates a second cancel after unknown', async () => {
    let cancellation: ReturnType<typeof executionOperationSchema.parse> | null = null;
    execute.mockImplementation(async value => {
      if (value.action === 'LIST') return {state: 'LIST', requests: cancellation ? [request, cancellation] : [request]};
      if(value.action==='RESEARCH_LIST')return {state:'RESEARCH_LIST',requests:[]};
      if (value.action === 'RECOVER') return {state: 'RECORDED', receipt};
      if (value.action === 'CANCEL') cancellation = executionOperationSchema.parse({schema_version: 'execution-runtime-v1',
        operation: 'CANCEL', request_id: value.requestId, device_id: profileId, credential_version: 1, task_id: value.taskId});
      return {state: 'UNKNOWN', requestId: value.requestId};
    });
    const hook = renderHook(() => useDesktopExecution(prepared));
    await waitFor(() => expect(hook.result.current.entries).toHaveLength(1));
    await act(async () => {await hook.result.current.recover(hook.result.current.entries[0]);});
    await act(async () => {await hook.result.current.cancel(hook.result.current.entries[0], false);});
    expect(execute.mock.calls.filter(([value]) => value.action === 'CANCEL')).toHaveLength(0);
    await act(async () => {await hook.result.current.cancel(hook.result.current.entries[0], true);});
    const cancelId = hook.result.current.entries.find(entry => entry.operation === 'CANCEL')!.requestId;
    await act(async () => {await hook.result.current.cancel(hook.result.current.entries[0], true);});
    expect(execute.mock.calls.filter(([value]) => value.action === 'CANCEL')).toHaveLength(1);
    hook.unmount();
    const reopened = renderHook(() => useDesktopExecution(prepared));
    await waitFor(() => expect(reopened.result.current.entries).toHaveLength(2));
    expect(reopened.result.current.entries.find(entry => entry.operation === 'CANCEL')!.requestId).toBe(cancelId);
  });
});
