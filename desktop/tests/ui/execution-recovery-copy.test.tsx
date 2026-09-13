// @vitest-environment jsdom
import {afterEach,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,within} from '@testing-library/react';
import {DesktopExecutionRequests} from '../../src/renderer/pages/tasks/DesktopExecutionRequests';

afterEach(cleanup);
const execution=(entry:any)=>({identity:{},loaded:true,busy:false,error:'',entries:[entry],refresh:vi.fn(),recover:vi.fn(),cancel:vi.fn()});
it.each([
  ['UNKNOWN','结果尚未确认'],['NOT_FOUND','暂未查到记录'],['SERVICE_UNAVAILABLE','服务暂不可用'],
  ['SESSION_CHANGED','登录身份已变化'],['BUSY','正在处理'],['KEY_MISSING','本机验证信息不可用'],
  ['SIGNED_OUT','请先登录'],['DEVICE_NOT_READY','本机尚未就绪'],['INVALID_REQUEST','请求信息无法核实'],
  ['FAILED','查询未完成'],['NEW_INTERNAL_STATE','结果尚未确认'],
])('uses a customer status for %s and preserves guarded original-request recovery',(state,label)=>{
  const entry={requestId:'internal-request',operation:'START',state};
  const model=execution(entry);
  render(<DesktopExecutionRequests execution={model as any} canRetryStart validateStart={vi.fn()}/>);
  expect(screen.queryByText(new RegExp(state))).toBeNull();
  expect(screen.getByText(`原请求待核对（${label}）；未查到不表示请求失败。`).closest('details')).toBeNull();
  fireEvent.click(screen.getByRole('button',{name:'查询原执行请求'}));
  expect(model.recover).toHaveBeenLastCalledWith(entry,false,expect.any(Function));
  fireEvent.click(screen.getByRole('checkbox',{name:/我确认核对后重试/}));
  fireEvent.click(screen.getByRole('button',{name:'核对并重试原执行请求'}));
  expect(model.recover).toHaveBeenLastCalledWith(entry,true,expect.any(Function));
});
it('removes quote-token teaching while retaining non-replay research recovery',()=>{
  const model=execution({requestId:'internal-request',kind:'RESEARCH',operation:'START',state:'UNKNOWN'});
  render(<DesktopExecutionRequests execution={model as any} canRetryStart validateStart={vi.fn()}/>);
  expect(screen.queryByText(/报价令牌/)).toBeNull();
  expect(screen.getByText('查询仅核对原研究进度，不会重复启动研究。')).toBeTruthy();
  expect(screen.getByRole('button',{name:'恢复原研究请求'})).toBeTruthy();
  expect(screen.queryByRole('checkbox')).toBeNull();
});
it('removes task identity and keeps cancellation confirmation attached to its entry',()=>{
  const entry={requestId:'internal-request',operation:'START',receipt:{operation:'START',task_id:'internal-task'}};
  const model=execution(entry);
  render(<DesktopExecutionRequests execution={model as any} canRetryStart={false} validateStart={vi.fn()}/>);
  expect(document.body.textContent).not.toMatch(/internal-task|internal-request/);
  const checkbox=screen.getByRole('checkbox',{name:'我确认取消此任务'});
  const button=screen.getByRole('button',{name:'确认取消此任务'}) as HTMLButtonElement;
  expect(button.disabled).toBe(true);
  fireEvent.click(checkbox);fireEvent.click(button);
  expect(model.cancel).toHaveBeenCalledWith(entry,true);
});
it('distinguishes multiple records and repeats the selected label in cancellation',()=>{
  const first={requestId:'request-a',operation:'START',receipt:{operation:'START',task_id:'task-a'}};
  const second={requestId:'request-b',operation:'START',receipt:{operation:'START',task_id:'task-b'}};
  const model={...execution(first),entries:[second,first]};
  const view=render(<DesktopExecutionRequests execution={model as any} canRetryStart={false} validateStart={vi.fn()}/>);
  const card=screen.getByRole('heading',{name:'启动任务 · 记录 2'}).closest('article')!;
  expect(card.textContent).not.toContain('task-b');
  fireEvent.click(within(card).getByRole('checkbox',{name:'我确认取消记录 2 对应的任务'}));
  fireEvent.click(within(card).getByRole('button',{name:'确认取消记录 2 对应的任务'}));
  expect(model.cancel).toHaveBeenCalledWith(second,true);
  view.rerender(<DesktopExecutionRequests execution={{...model,entries:[first,second]} as any} canRetryStart={false} validateStart={vi.fn()}/>);
  fireEvent.click(within(screen.getByRole('heading',{name:'启动任务 · 记录 2'}).closest('article')!).getByRole('button',{name:'确认取消记录 2 对应的任务'}));
  expect(model.cancel).toHaveBeenLastCalledWith(second,true);
});
