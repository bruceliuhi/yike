// @vitest-environment jsdom
import {afterEach,beforeEach,it,expect,vi} from 'vitest';
import {act,cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {WorkbenchPage} from '../../src/renderer/pages/Workbench';
import {CandidatesPage} from '../../src/renderer/pages/Opportunities';
import {parseRoute} from '../../src/renderer/domain/routes';
import type {AppContextValue} from '../../src/renderer/app/context';
import {clearLocalDrafts} from '../../src/renderer/app/hooks';
import {candidate} from '../visual/fixtures';
let context:AppContextValue;
vi.mock('../../src/renderer/app/context',()=>({useApp:()=>context}));
const taskId='11111111-1111-4111-8111-111111111111',other='22222222-2222-4222-8222-222222222222';
beforeEach(()=>{
 context={session:{authenticated:true,userId:'user',accountScope:{id:taskId,version:1}},route:parseRoute('#/workbench'),navigate:vi.fn(),notify:vi.fn(),
  service:{profiles:vi.fn().mockResolvedValue([]),connections:vi.fn().mockResolvedValue([]),opportunities:vi.fn().mockResolvedValue([]),
   tasks:vi.fn().mockRejectedValue(new Error('old unavailable')),taskFeed:{list:vi.fn().mockResolvedValue({items:[{task_id:taskId}],next_cursor:null}),get:vi.fn().mockImplementation(async id=>({task_id:id,name:'制造企业需求'}))},
   candidates:vi.fn().mockImplementation(async q=>({items:[],page:1,pageSize:10,total:0,...(q.taskId?{taskId:q.taskId}:{})})),
  }} as unknown as AppContextValue;
});
afterEach(()=>{cleanup();clearLocalDrafts();sessionStorage.clear();localStorage.clear();});
it('uses a bounded real task feed on the homepage and never falls back after a feed error',async()=>{
 const view=render(<WorkbenchPage/>);fireEvent.click(screen.getByText('全部待办与准备步骤'));
 const button=await screen.findByRole('button',{name:/创建获客任务.*已有任务/});
 expect(context.service.taskFeed!.list).toHaveBeenCalledWith({limit:1},expect.any(AbortSignal));
 expect(context.service.tasks).not.toHaveBeenCalled();fireEvent.click(button);expect(context.navigate).toHaveBeenCalledWith('/collection');
 view.unmount();vi.mocked(context.service.taskFeed!.list).mockRejectedValue(new Error('feed unavailable'));
 render(<WorkbenchPage/>);fireEvent.click(screen.getByText('全部待办与准备步骤'));
 await waitFor(()=>expect(screen.getByRole('button',{name:/创建获客任务.*待核验/})).toBeTruthy());
 expect(context.service.tasks).not.toHaveBeenCalled();
});
it('carries task filter through status changes, validates echo and returns to the task',async()=>{
 context.route=parseRoute(`#/candidates?task=${taskId}`);const view=render(<CandidatesPage/>);
 await waitFor(()=>expect(context.service.candidates).toHaveBeenCalledWith(expect.objectContaining({taskId,status:undefined}),expect.any(AbortSignal)));
 expect(screen.getByText(/当前最新版本/)).toBeTruthy();
 expect(await screen.findByRole('heading',{name:'制造企业需求 · 发现线索'})).toBeTruthy();
 fireEvent.change(screen.getByLabelText('候选复核状态筛选'),{target:{value:'IMPORTED'}});
 await waitFor(()=>expect(context.service.candidates).toHaveBeenLastCalledWith(expect.objectContaining({taskId,status:'IMPORTED'}),expect.any(AbortSignal)));
 fireEvent.click(screen.getByRole('button',{name:'返回采集任务'}));expect(context.navigate).toHaveBeenCalledWith(`/collection?task=${taskId}`);
 vi.mocked(context.service.candidates).mockResolvedValue({items:[],page:1,pageSize:10,total:0,taskId});
 context.route=parseRoute(`#/candidates?task=${other}`);view.rerender(<CandidatesPage/>);
 await screen.findByText(/返回线索与采集任务不匹配/);
});
it('drops selected old-task details and late results after switching task',async()=>{
 context.route=parseRoute(`#/candidates?task=${taskId}`);
 vi.mocked(context.service.candidates).mockResolvedValue({items:[candidate],page:1,pageSize:10,total:1,taskId});
 const view=render(<CandidatesPage/>);fireEvent.click(await screen.findByRole('button',{name:`查看候选${candidate.title}`}));
 let resolve!:(v:any)=>void;
 vi.mocked(context.service.candidates).mockImplementationOnce(()=>new Promise(r=>resolve=r));
 context.route=parseRoute(`#/candidates?task=${other}`);view.rerender(<CandidatesPage/>);
 await waitFor(()=>expect(resolve).toBeTypeOf('function'));
 expect(screen.queryByRole('button',{name:`查看候选${candidate.title}`})).toBeNull();
 context.route=parseRoute(`#/candidates?task=${taskId}`);
 vi.mocked(context.service.candidates).mockResolvedValue({items:[],page:1,pageSize:10,total:0,taskId});view.rerender(<CandidatesPage/>);
 await act(async()=>resolve({items:[{...candidate,title:'旧任务晚到'}],page:1,pageSize:10,total:1,taskId:other}));
 expect(screen.queryByText('旧任务晚到')).toBeNull();
});
