// @vitest-environment jsdom
import {act, cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import type {AppContextValue} from '../../src/renderer/app/context';
import {useDesktopExecution} from '../../src/renderer/pages/tasks/useDesktopExecution';
import {DesktopExecutionRequests} from '../../src/renderer/pages/tasks/DesktopExecutionRequests';
import {executionOperationSchema} from '../../src/shared/executionOperation';
import type {ForegroundCollectionCommand, ForegroundCollectionResult} from '../../src/shared/foregroundCollection';

let context: AppContextValue;
const requestId = '11111111-1111-4111-8111-111111111111';
const taskId = '22222222-2222-4222-8222-222222222222';
const original = executionOperationSchema.parse({schema_version:'execution-runtime-v1', request_id:requestId, operation:'START',
  device_id:requestId, credential_version:1, profile_version_id:'profile', strategy_version_id:'strategy', configuration_sha256:'a'.repeat(64),
  targets:[{platform:'XIAOHONGSHU',access_mode:'PLATFORM_ACCOUNT',connection_id:requestId,connection_version:2}]});
const receipt = {schema_version:'execution-runtime-v1',request_id:requestId,operation:'START',task_id:taskId,run_id:taskId,
  status:'PENDING',stop_confirmed:false,platform_runs:[{platform:'XIAOHONGSHU',platform_run_id:taskId,status:'PENDING'}]};
const status = {state:'STATUS' as const, taskId, localState:'UPLOAD_UNKNOWN' as const, serverStatus:'RUNNING' as const,
  stopConfirmed:false,recordsUsed:0,recoverable:true};
let collect: ReturnType<typeof vi.fn<(command:ForegroundCollectionCommand)=>Promise<ForegroundCollectionResult>>>;
vi.mock('../../src/renderer/app/context', () => ({useApp:() => context}));
function Harness() {
  const execution = useDesktopExecution(null);
  return <DesktopExecutionRequests execution={execution} canRetryStart={false} validateStart={async () => {throw new Error();}} />;
}
beforeEach(() => {
  collect = vi.fn(async () => status);
  context = {session:{authenticated:true,userId:'owner-a'},service:{
    execution:{execute:vi.fn(async command => command.action==='LIST' ? {state:'LIST',requests:[original]} : {state:'RECORDED',receipt})},
    foregroundCollection:{execute:collect},
  }} as unknown as AppContextValue;
});
afterEach(() => {cleanup(); vi.useRealTimers();});
async function ready() {
  await screen.findByText(requestId);
  fireEvent.click(screen.getByRole('button',{name:'查询原执行请求'}));
  await screen.findByText(/原启动回执/);
}

describe('existing task request foreground controls', () => {
  it('queries current state separately and recovers only after explicit original-batch confirmation', async () => {
    render(<Harness />); await ready();
    expect(collect).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button',{name:'读取当前采集状态'}));
    await screen.findByText(/本机采集状态：上传结果待核对/);
    expect(screen.getByText(/服务端任务状态：运行中/)).toBeTruthy();
    expect(screen.getByText(/停止确认：尚未确认/)).toBeTruthy();
    const recover = screen.getByRole('button',{name:'核对并恢复原批次'}) as HTMLButtonElement;
    expect(recover.disabled).toBe(true);
    fireEvent.click(screen.getByRole('checkbox',{name:/我确认仅恢复原批次/}));
    fireEvent.click(recover);
    await waitFor(() => expect(collect).toHaveBeenLastCalledWith({action:'RECOVER',taskId,humanConfirmed:true,retry:true}));
    expect(vi.mocked(context.service.execution!.execute).mock.calls.every(([command]) => command.action !== 'START')).toBe(true);
  });
  it('drops late state when the authenticated workspace changes', async () => {
    let resolve!: (value:ForegroundCollectionResult)=>void;
    collect.mockImplementation(() => new Promise(done => {resolve=done;}));
    const view = render(<Harness />); await ready();
    fireEvent.click(screen.getByRole('button',{name:'读取当前采集状态'}));
    await waitFor(() => expect(collect).toHaveBeenCalled());
    context = {...context,session:{authenticated:true,userId:'owner-b'}};
    view.rerender(<Harness />);
    await act(async () => resolve(status));
    expect(screen.queryByText(/本机采集状态：上传结果待核对/)).toBeNull();
  });
  it('bounds waiting and does not turn an unknown response into completion', async () => {
    render(<Harness />); await ready();
    collect.mockImplementation(() => new Promise(() => {}));
    vi.useFakeTimers();
    fireEvent.click(screen.getByRole('button',{name:'读取当前采集状态'}));
    await act(async () => {await vi.advanceTimersByTimeAsync(30_001);});
    expect(screen.getByText(/执行响应未核实/)).toBeTruthy();
    expect(screen.queryByText(/本机采集状态：已完成/)).toBeNull();
    expect((screen.getByRole('button',{name:'读取当前采集状态'}) as HTMLButtonElement).disabled).toBe(false);
  });
});
