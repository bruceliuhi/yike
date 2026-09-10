// @vitest-environment jsdom
import {afterEach,beforeEach,it,expect,vi} from 'vitest';
import {act,cleanup,fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import {WorkbenchPage} from '../../src/renderer/pages/Workbench';
import {CandidatesPage} from '../../src/renderer/pages/Opportunities';
import {parseRoute} from '../../src/renderer/domain/routes';
import type {AppContextValue} from '../../src/renderer/app/context';
import {clearLocalDrafts} from '../../src/renderer/app/hooks';
import {candidate,profile} from '../visual/fixtures';
import {operationLedgerKey} from '../../src/renderer/app/operationLedger';
import {candidateRequestEntry,newCandidateRequestOperation} from '../../src/renderer/domain/candidateRequestOperation';
import {assessmentFixture,assessmentRequestFixture,candidateFixture} from '../fixtures/candidateReviewApi';
import type {Candidate} from '../../src/renderer/domain/candidates';
let context:AppContextValue;
vi.mock('../../src/renderer/app/context',()=>({useApp:()=>context}));
const taskId='11111111-1111-4111-8111-111111111111',other='22222222-2222-4222-8222-222222222222';
beforeEach(()=>{
 context={session:{authenticated:true,userId:'user',accountScope:{id:taskId,version:1}},route:parseRoute('#/workbench'),navigate:vi.fn(),notify:vi.fn(),
  service:{profiles:vi.fn().mockResolvedValue([profile]),connections:vi.fn().mockResolvedValue([]),opportunities:vi.fn().mockResolvedValue([]),
   tasks:vi.fn().mockRejectedValue(new Error('old unavailable')),taskFeed:{list:vi.fn().mockResolvedValue({items:[{task_id:taskId}],next_cursor:null}),get:vi.fn().mockImplementation(async id=>({task_id:id,name:'制造企业需求'}))},
   candidates:vi.fn().mockImplementation(async q=>({items:[],page:1,pageSize:10,total:0,...(q.taskId?{taskId:q.taskId}:{})})),reviewCandidate:vi.fn(),
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
it('does not expose or reconcile another task legacy review from a task result view',async()=>{
 const requestId='TEST.other-task-review';
 const key=JSON.stringify([candidate.id,'EXCLUDE',requestId,'a'.repeat(64)]);
 localStorage.setItem(operationLedgerKey('candidate-reviews','user'),JSON.stringify({[key]:'PENDING'}));
 context.route=parseRoute(`#/candidates?task=${other}`);
 render(<CandidatesPage/>);
 expect(await screen.findByText(/其他任务或当前筛选外的原请求仍已保留/)).toBeTruthy();
 expect(screen.queryByRole('button',{name:'核对原复核结果'})).toBeNull();
 fireEvent.click(screen.getByRole('button',{name:'前往全部线索核对'}));
 expect(context.navigate).toHaveBeenCalledWith('/candidates');
 expect(localStorage.getItem(operationLedgerKey('candidate-reviews','user'))).toContain(requestId);
});
it('keeps a legacy review ledger entry when its task-scoped candidate echo mismatches',async()=>{
 const requestId='TEST.current-task-review';
 const key=JSON.stringify([candidate.id,'EXCLUDE',requestId,'a'.repeat(64)]);
 localStorage.setItem(operationLedgerKey('candidate-reviews','user'),JSON.stringify({[key]:'PENDING'}));
 context.route=parseRoute(`#/candidates?task=${taskId}`);
 vi.mocked(context.service.candidates).mockImplementation(async q=>q?.reviewRequestId
  ? {items:[candidate],page:1,pageSize:1,total:1,taskId:other}
  : {items:[candidate],page:1,pageSize:10,total:1,taskId});
 render(<CandidatesPage/>);
 fireEvent.click(await screen.findByRole('button',{name:'核对本次结果'}));
 await waitFor(()=>expect(context.service.candidates).toHaveBeenCalledWith(expect.objectContaining({ids:[candidate.id],reviewRequestId:requestId,taskId})));
 expect(localStorage.getItem(operationLedgerKey('candidate-reviews','user'))).toContain(requestId);
 expect(screen.queryByText('候选已排除。')).toBeNull();
});
it('requires a task-scoped candidate echo before showing a recovered original request',async()=>{
 const row=candidateFixture() as Candidate;
 const operation=await newCandidateRequestOperation(assessmentRequestFixture(),context.session.accountScope!);
 const entry=candidateRequestEntry(operation);
 localStorage.setItem(operationLedgerKey('candidate-request-operations','user'),JSON.stringify({[entry.key]:entry.value}));
 context.route=parseRoute(`#/candidates?task=${taskId}`);
 context.service.candidateReview={getRequest:vi.fn().mockResolvedValue({kind:'assessment',requestId:operation.requestId,candidateId:row.id,assessment:assessmentFixture()})} as never;
 vi.mocked(context.service.candidates).mockImplementation(async q=>q?.ids
  ? {items:[row],page:1,pageSize:1,total:1,taskId:other}
  : {items:[row],page:1,pageSize:10,total:1,taskId});
 render(<CandidatesPage/>);
 fireEvent.click(await screen.findByRole('button',{name:'核对原请求'}));
 await waitFor(()=>expect(context.service.candidates).toHaveBeenCalledWith(expect.objectContaining({ids:[row.id],taskId})));
 expect(screen.queryByText(/原请求已核对成功/)).toBeNull();
 expect(localStorage.getItem(operationLedgerKey('candidate-request-operations','user'))).toContain(operation.requestId);
});
it('does not show an async recovered request after switching tasks',async()=>{
 const row=candidateFixture() as Candidate;
 const operation=await newCandidateRequestOperation(assessmentRequestFixture(),context.session.accountScope!);
 const entry=candidateRequestEntry(operation);
 localStorage.setItem(operationLedgerKey('candidate-request-operations','user'),JSON.stringify({[entry.key]:entry.value}));
 let resolve!:(value:unknown)=>void;
 context.service.candidateReview={getRequest:vi.fn(()=>new Promise(r=>{resolve=r;}))} as never;
 context.route=parseRoute(`#/candidates?task=${taskId}`);
 vi.mocked(context.service.candidates).mockResolvedValue({items:[row],page:1,pageSize:10,total:1,taskId});
 const view=render(<CandidatesPage/>);
 fireEvent.click(await screen.findByRole('button',{name:'核对原请求'}));
 await waitFor(()=>expect(resolve).toBeTypeOf('function'));
 context.route=parseRoute(`#/candidates?task=${other}`);
 vi.mocked(context.service.candidates).mockResolvedValue({items:[],page:1,pageSize:10,total:0,taskId:other});
 view.rerender(<CandidatesPage/>);
 await act(async()=>resolve({kind:'assessment',requestId:operation.requestId,candidateId:row.id,assessment:assessmentFixture()}));
 expect(screen.queryByText(/原请求已核对成功/)).toBeNull();
 expect(screen.queryByText(/已找回原请求记录/)).toBeNull();
});
it('drops an opened candidate confirmation when the task changes and cannot submit it',async()=>{
 context.route=parseRoute(`#/candidates?task=${taskId}`);
 vi.mocked(context.service.candidates).mockResolvedValue({items:[candidate],page:1,pageSize:10,total:1,taskId});
 const view=render(<CandidatesPage/>);
 fireEvent.click(await screen.findByRole('button',{name:`查看候选${candidate.title}`}));
 fireEvent.click(screen.getByRole('button',{name:'排除'}));
 const dialog=screen.getByRole('dialog',{name:'确认排除候选'});
 fireEvent.change(within(dialog).getByRole('textbox',{name:'候选排除原因'}),{target:{value:'TEST 切任务前原因'}});
 fireEvent.click(within(dialog).getByRole('checkbox'));
 context.route=parseRoute(`#/candidates?task=${other}`);
 vi.mocked(context.service.candidates).mockResolvedValue({items:[],page:1,pageSize:10,total:0,taskId:other});
 view.rerender(<CandidatesPage/>);
 await waitFor(()=>expect(screen.queryByRole('dialog',{name:'确认排除候选'})).toBeNull());
 expect(context.service.reviewCandidate).not.toHaveBeenCalled();
});
