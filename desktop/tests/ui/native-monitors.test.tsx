// @vitest-environment jsdom
// Synthetic UI contract evidence, not actual platform collection.
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {afterEach,beforeEach,describe,it,expect,vi} from 'vitest';
import {NativeMonitorPlans} from '../../src/renderer/pages/tasks/NativeMonitorPlans';
import type {AppContextValue} from '../../src/renderer/app/context';
import {parseRoute} from '../../src/renderer/domain/routes';
import {clearLocalDrafts} from '../../src/renderer/app/hooks';
let context:AppContextValue;
vi.mock('../../src/renderer/app/context',()=>({useApp:()=>context}));
const id='11111111-1111-4111-8111-111111111111';
const base={planId:id,profileVersionId:id,strategyVersionId:id,configurationSha256:'a'.repeat(64),state:'ACTIVE',revision:1,
 schedule:{kind:'interval',times:[],interval:1,start:'09:00',end:'18:00',timezone:'Asia/Shanghai',policyVersion:1},
 nextDueAt:'2026-09-11T09:00:00Z',localState:'DETACHED',taskId:null,lastError:null};
beforeEach(()=>{
 clearLocalDrafts();sessionStorage.clear();localStorage.clear();
 context={session:{authenticated:true,userId:crypto.randomUUID()},route:parseRoute('#/monitors'),navigate:vi.fn(),
  service:{profiles:vi.fn().mockResolvedValue([]),monitorCollection:{execute:vi.fn().mockResolvedValue({state:'LIST',supported:true,plans:[base],serverTime:null})}}} as unknown as AppContextValue;
});
afterEach(()=>cleanup());
describe('monitor page real service wiring',()=>{
 it('unlocks a definitive pre-submit BUSY without treating a missing receipt as success',async()=>{
  const execute=vi.mocked(context.service.monitorCollection!.execute);
  execute.mockImplementation(async c=>c.action==='LIST'?{state:'LIST',supported:true,plans:[base],serverTime:null} as any:{state:'BUSY'});
  render(<NativeMonitorPlans/>);await screen.findByText('本机未接管');
  fireEvent.click(screen.getByRole('button',{name:'暂停计划'}));fireEvent.click(screen.getByRole('button',{name:'确认执行'}));
  await waitFor(()=>expect(execute.mock.calls.some(([c])=>c.action==='SET_STATE')).toBe(true));
  await waitFor(()=>expect(screen.queryByRole('button',{name:'核对原请求'})).toBeNull());
  expect((screen.getByRole('button',{name:'暂停计划'}) as HTMLButtonElement).disabled).toBe(false);
  fireEvent.click(screen.getByRole('button',{name:'暂停计划'}));fireEvent.click(screen.getByRole('button',{name:'确认执行'}));
  await waitFor(()=>expect(execute.mock.calls.filter(([c])=>c.action==='SET_STATE')).toHaveLength(2));
  expect(execute.mock.calls.filter(([c])=>c.action==='RECEIPT')).toHaveLength(0);
 });
 it('does not auto attach from a list; confirms pause and retains unknown original request across remount',async()=>{
  const execute=vi.mocked(context.service.monitorCollection!.execute);
  execute.mockImplementation(async c=>c.action==='LIST'?{state:'LIST',supported:true,plans:[base],serverTime:null} as any:
   c.action==='SET_STATE'?{state:'UNKNOWN',requestId:c.requestId}:{state:'NOT_FOUND'});
  const view=render(<NativeMonitorPlans/>);await screen.findByText('本机未接管');
  expect(execute.mock.calls.every(([c])=>c.action==='LIST')).toBe(true);
  fireEvent.click(screen.getByRole('button',{name:'暂停计划'}));
  expect(execute.mock.calls.every(([c])=>c.action==='LIST')).toBe(true);
  fireEvent.click(screen.getByRole('button',{name:'确认执行'}));
  await screen.findByRole('button',{name:'核对原请求'});
  const command=execute.mock.calls.find(([c])=>c.action==='SET_STATE')![0];
  expect(command).toMatchObject({planId:id,expectedRevision:1,state:'PAUSED',humanConfirmed:true});
  view.unmount();render(<NativeMonitorPlans/>);
  fireEvent.click(await screen.findByRole('button',{name:'核对原请求'}));
  await waitFor(()=>expect(execute).toHaveBeenCalledWith({action:'RECEIPT',command}));
  expect(execute.mock.calls.filter(([c])=>c.action==='SET_STATE')).toHaveLength(1);
 });
 it('renders detached and no collection claim when deployment support is disabled',async()=>{
  vi.mocked(context.service.monitorCollection!.execute).mockResolvedValue({state:'LIST',supported:false,plans:[base],serverTime:null} as any);
  render(<NativeMonitorPlans/>);await screen.findByText('本机未接管');
  expect((screen.getByRole('button',{name:'在本机运行'}) as HTMLButtonElement).disabled).toBe(true);
  expect(screen.queryByText('采集成功')).toBeNull();
 });
});
