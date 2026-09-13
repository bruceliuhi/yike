// @vitest-environment jsdom
import {act, cleanup, renderHook} from '@testing-library/react';
import {afterEach, beforeEach, expect, it, vi} from 'vitest';
import type {AppContextValue} from '../../src/renderer/app/context';
import {useDesktopExecution} from '../../src/renderer/pages/tasks/useDesktopExecution';
import type {DesktopExecutionCommand, DesktopExecutionResult} from '../../src/shared/desktopExecution';

let context: AppContextValue;
let execute: ReturnType<typeof vi.fn<(command: DesktopExecutionCommand) => Promise<DesktopExecutionResult>>>;
vi.mock('../../src/renderer/app/context', () => ({useApp: () => context}));
beforeEach(() => {
  vi.useFakeTimers();
  execute = vi.fn(async command => command.action === 'LIST'
    ? {state: 'LIST', requests: []} : {state: 'RESEARCH_LIST', requests: []});
  context = {service: {execution: {execute, researchContractVersion: 1}},
    session: {authenticated: true, userId: crypto.randomUUID()}} as unknown as AppContextValue;
});
afterEach(() => {cleanup(); vi.useRealTimers();});
const advance = async (ms = 0) => {await act(async () => {await vi.advanceTimersByTimeAsync(ms);});};

it.each(['LIST', 'RESEARCH_LIST'] as const)('recovers a transient %s BUSY without a user refresh', async action => {
  const normal = execute.getMockImplementation()!;
  let busy = true;
  execute.mockImplementation(async command => {
    if (command.action === action && busy) {busy = false; return {state: 'BUSY'};}
    return normal(command);
  });
  const {result} = renderHook(() => useDesktopExecution(null));
  await advance();
  expect(result.current.loaded).toBe(false);
  expect(result.current.error).toBe('');
  await advance(250);
  expect(result.current.loaded).toBe(true);
  expect(result.current.busy).toBe(false);
  expect(execute.mock.calls.filter(([command]) => command.action === action)).toHaveLength(2);
  expect(execute.mock.calls.every(([command]) => ['LIST', 'RESEARCH_LIST'].includes(command.action))).toBe(true);
});

it('bounds BUSY retries and keeps startup blocked rather than assuming empty history', async () => {
  execute.mockResolvedValue({state: 'BUSY'});
  const {result} = renderHook(() => useDesktopExecution(null));
  await advance(4000);
  expect(execute.mock.calls.filter(([command]) => command.action === 'LIST')).toHaveLength(4);
  expect(execute.mock.calls.filter(([command]) => command.action === 'RESEARCH_LIST')).toHaveLength(4);
  expect(result.current.loaded).toBe(false);
  expect(result.current.blocksStart).toBe(true);
  expect(result.current.error).not.toBe('');
  await advance(30_000);
  expect(execute).toHaveBeenCalledTimes(8);
});

it.each(['SESSION_CHANGED', 'SIGNED_OUT', 'SERVICE_UNAVAILABLE'] as const)('never retries a %s rejection', async state => {
  execute.mockResolvedValue({state});
  const {result} = renderHook(() => useDesktopExecution(null));
  await advance(4000);
  expect(execute.mock.calls.filter(([command]) => command.action === 'LIST')).toHaveLength(1);
  expect(result.current.loaded).toBe(false);
  expect(result.current.blocksStart).toBe(true);
});

it('does not run a delayed old-account query after sign-out', async () => {
  execute.mockResolvedValue({state: 'BUSY'});
  const {result, rerender} = renderHook(() => useDesktopExecution(null));
  await advance();
  const calls = execute.mock.calls.length;
  context = {...context, session: {...context.session, authenticated: false}};
  rerender();
  await advance(4000);
  expect(execute).toHaveBeenCalledTimes(calls);
  expect(result.current.loaded).toBe(false);
});

it('does not run a delayed query after the page unmounts', async () => {
  execute.mockResolvedValue({state: 'BUSY'});
  const {unmount} = renderHook(() => useDesktopExecution(null));
  await advance();
  const calls = execute.mock.calls.length;
  unmount();
  await advance(4000);
  expect(execute).toHaveBeenCalledTimes(calls);
});

it('keeps a BUSY start as a single explicit submission', async () => {
  const normal = execute.getMockImplementation()!;
  execute.mockImplementation(async command => command.action === 'START' ? {state: 'BUSY'} : normal(command));
  const {result} = renderHook(() => useDesktopExecution(null));
  await advance();
  const requestId = crypto.randomUUID();
  await act(async () => {await result.current.start({action: 'START', humanConfirmed: true, requestId,
    profileVersionId: crypto.randomUUID(), strategyVersionId: crypto.randomUUID(),
    configurationSha256: 'a'.repeat(64), targets: [{platform: 'PUBLIC_WEB', access_mode: 'PUBLIC_ANONYMOUS',
      connection_id: null, connection_version: null}]});});
  await advance(4000);
  expect(execute.mock.calls.filter(([command]) => command.action === 'START')).toHaveLength(1);
  expect(result.current.entries[0]).toMatchObject({requestId, state: 'BUSY'});
});

it('lets the new account load without sending the old delayed query', async () => {
  execute.mockResolvedValue({state: 'BUSY'});
  const {result, rerender} = renderHook(() => useDesktopExecution(null));
  await advance();
  const calls = execute.mock.calls.length;
  const fresh = vi.fn(async (command: DesktopExecutionCommand) => command.action === 'LIST'
    ? {state: 'LIST' as const, requests: []} : {state: 'RESEARCH_LIST' as const, requests: []});
  context = {...context, service: {...context.service, execution: {execute: fresh, researchContractVersion: 1}},
    session: {...context.session, userId: crypto.randomUUID()}};
  rerender();
  await advance(4000);
  expect(execute).toHaveBeenCalledTimes(calls);
  expect(fresh).toHaveBeenCalledTimes(2);
  expect(result.current.loaded).toBe(true);
  expect(result.current.error).toBe('');
});
