// @vitest-environment jsdom
import {act, cleanup, renderHook, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {useDesktopExecution, type DesktopStartCommand} from '../../src/renderer/pages/tasks/useDesktopExecution';
import {executionOperationSchema} from '../../src/shared/executionOperation';
import type {StrategyReceipt} from '../../src/shared/researchStrategies';
import type {AppContextValue} from '../../src/renderer/app/context';
import type {DesktopExecutionCommand, DesktopExecutionResult} from '../../src/shared/desktopExecution';

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
let execute: ReturnType<typeof vi.fn<(command: DesktopExecutionCommand) => Promise<DesktopExecutionResult>>>;
beforeEach(() => {
  execute = vi.fn(async value => value.action === 'LIST' ? {state: 'LIST', requests: []} : {state: 'UNKNOWN', requestId: value.requestId});
  context = {service: {execution: {execute}}, session: {authenticated: true, userId: 'user'}, sessionReady: true} as unknown as AppContextValue;
});
afterEach(() => {cleanup(); vi.useRealTimers();});

describe('desktop execution original-request safety', () => {
  it('blocks START until LIST succeeds and never treats unreadable LIST as empty history', async () => {
    let finish!: (value: DesktopExecutionResult) => void;
    execute.mockImplementationOnce(() => new Promise(resolve => {finish = resolve;}));
    const hook = renderHook(() => useDesktopExecution(prepared));
    await waitFor(() => expect(execute).toHaveBeenCalledWith({action: 'LIST'}));
    await act(async () => {await hook.result.current.start(command);});
    expect(execute).toHaveBeenCalledTimes(1);
    await act(async () => {finish({state: 'FAILED', error: 'EXECUTION_SESSION_FAILED'});});
    expect(hook.result.current.loaded).toBe(false);
    await act(async () => {await hook.result.current.start(command);});
    expect(execute).toHaveBeenCalledTimes(1);
  });
  it('keeps original UUID on unknown START and discovers it after remount without another START', async () => {
    let stored = false;
    execute.mockImplementation(async value => {
      if (value.action === 'LIST') return {state: 'LIST', requests: stored ? [request] : []};
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
    execute.mockResolvedValueOnce({state: 'LIST', requests: [request]});
    const hook = renderHook(() => useDesktopExecution(prepared));
    await waitFor(() => expect(hook.result.current.loaded).toBe(true));
    const entry = hook.result.current.entries[0];
    await act(async () => {await hook.result.current.recover(entry, true);});
    expect(execute).toHaveBeenCalledTimes(1);
    await act(async () => {await hook.result.current.recover(entry, true, async () => ({...command, configurationSha256: 'b'.repeat(64)}));});
    expect(execute).toHaveBeenCalledTimes(1);
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
