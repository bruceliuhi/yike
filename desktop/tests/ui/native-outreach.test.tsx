// @vitest-environment jsdom
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {act,cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {SendConfirmation} from '../../src/renderer/pages/Outreach';
import {ContactEditor} from '../../src/renderer/pages/outreach/ContactEditor';
import {PUBLIC_SAMPLE} from '../../src/renderer/pages/Opportunities';
import {parseRoute} from '../../src/renderer/domain/routes';
import type {AppContextValue} from '../../src/renderer/app/context';
import type {ContactDraft,Opportunity,PlatformConnection} from '../../src/renderer/domain/models';
import type {NativeOutreachCommand,NativeOutreachResult} from '../../src/shared/nativeOutreach';
let app:AppContextValue;
vi.mock('../../src/renderer/app/context',()=>({useApp:()=>app}));
const id=()=>crypto.randomUUID();
let row:Opportunity,draft:ContactDraft,connection:PlatformConnection;
let prepared:Extract<NativeOutreachResult,{state:'PREPARED'}>;
let command:ReturnType<typeof vi.fn<(command:NativeOutreachCommand)=>Promise<NativeOutreachResult>>>;
const close=vi.fn();
beforeEach(()=>{
  localStorage.clear();sessionStorage.clear();close.mockClear();
  const tenantId=id(),userId=id(),opportunityId=id(),deviceId=id();
  row={...PUBLIC_SAMPLE,id:opportunityId,sample:false,platform:'xhs',profileStatus:'CONFIRMED',sourceStatus:'OPEN',profileVersionId:id(),comment:'完整人工确认文字'};
  draft={opportunityId,channel:'comment',content:row.comment,savedContent:row.comment,version:1,accountId:'original-account',recipient:'original-buyer'};
  connection={platform:'xhs',status:'CONNECTED',accountId:draft.accountId,accountName:'屏幕账号昵称',capabilities:[]};
  prepared={state:'PREPARED',flowId:id(),binding:{tenantId,requestId:id(),claimId:id(),contextSha256:'a'.repeat(64)},context:{
    schemaVersion:'outreach-context-v1',binding:{opportunityId,channel:'comment',requestId:id(),contentHash:'b'.repeat(64)},ownerUserId:userId,
    accountScope:{id:tenantId,version:1},profileVersionId:row.profileVersionId,
    draft:{...draft},source:{sourceId:id(),evidenceVersion:id(),evidenceSha256:'c'.repeat(64),platform:'XIAOHONGSHU',kind:'POST',url:'https://www.xiaohongshu.com/explore/abc',excerpt:'主进程返回的固定原文'},
    target:{action:'POST_COMMENT',authorPublicId:'original-buyer',postId:'abc',commentId:null},connection:{deviceId,connectionId:id(),connectionVersion:1,accountPublicId:'original-account',platform:'XIAOHONGSHU'},
    channelCapability:{status:'UNVERIFIED',reason:'CHANNEL_CHECK_REQUIRED'},authorization:'NOT_GRANTED',contextSha256:'a'.repeat(64),
  }};
  command=vi.fn(async(value:NativeOutreachCommand):Promise<NativeOutreachResult>=>{
    if(value.action==='PREPARE'){prepared={...prepared,binding:{...prepared.binding,requestId:value.requestId}};return prepared;}
    if(value.action==='CANCEL')return {state:'CANCELLED'};
    return {state:'RESULT',binding:prepared.binding,result:{state:'UNKNOWN',serverAccepted:false,reason:'UNCONFIRMED'}};
  });
  Object.defineProperty(window,'yikeDesktop',{configurable:true,value:{nativeOutreachCommand:command}});
  app={session:{authenticated:true,userId,accountScope:{id:tenantId,version:1}},service:{connections:vi.fn().mockResolvedValue([connection]),verifyContact:vi.fn(),send:vi.fn()} as unknown as AppContextValue['service'],route:parseRoute('#/outreach'),navigate:vi.fn(),notify:vi.fn(),refreshSession:vi.fn()};
});
afterEach(()=>{cleanup();vi.restoreAllMocks();delete (window as unknown as {yikeDesktop?:unknown}).yikeDesktop;});
const view=()=> <SendConfirmation row={row} draft={draft} connection={connection} onClose={close}/>;
async function prepare(){fireEvent.click(screen.getByRole('button',{name:'核对发送信息'}));await screen.findByText('主进程返回的固定原文');}
async function confirm(){fireEvent.click(screen.getByRole('checkbox',{name:'我已核对联系对象、发送账号和内容'}));fireEvent.click(screen.getByRole('button',{name:'确认并发送'}));await waitFor(()=>expect(command.mock.calls.some(([c])=>c.action==='CONFIRM')).toBe(true));}
function saved(){return Object.keys(localStorage).filter(key=>key.startsWith('yike.ui.native-outreach.')).map(key=>({key,value:localStorage.getItem(key)!}));}
function result(state:'SENT'|'UNKNOWN'|'QUEUED'|'CANCELLED'):NativeOutreachResult{return {state:'RESULT',binding:prepared.binding,result:{state:'RECONCILED',serverAccepted:true,receipt:{requestId:prepared.binding.requestId,...(state!=='QUEUED'?{claimId:prepared.binding.claimId,dispatchBefore:new Date().toISOString()}:{}),state,dispatchAllowed:false,deliveryConfirmed:state==='SENT',...(state==='SENT'?{evidenceAuthority:'DEVICE_ATTESTED_PLATFORM_RECEIPT'}:{})}}};}
it('shows the native frozen context and durably reads back metadata before explicit CONFIRM, without the legacy sender',async()=>{
  render(view());await prepare();
  expect(screen.getByText('original-account')).toBeTruthy();expect(screen.getByText('original-buyer')).toBeTruthy();
  expect((screen.getByRole('button',{name:'确认并发送'}) as HTMLButtonElement).disabled).toBe(true);
  command.mockImplementationOnce(async value=>{expect(value.action).toBe('CONFIRM');expect(saved()).toHaveLength(1);expect(saved()[0].value).toContain(prepared.binding.requestId);expect(saved()[0].value).not.toContain(draft.content);return result('SENT');});
  await confirm();await screen.findByText(/渠道已确认发送成功/);
  expect(app.service.verifyContact).not.toHaveBeenCalled();expect(app.service.send).not.toHaveBeenCalled();
});
it.each(['throw','silent'])('blocks CONFIRM when durable storage %s fails',async mode=>{
  render(view());await prepare();
  vi.spyOn(Storage.prototype,'setItem').mockImplementation(()=>{if(mode==='throw')throw new Error('private path');});
  fireEvent.click(screen.getByRole('checkbox',{name:'我已核对联系对象、发送账号和内容'}));fireEvent.click(screen.getByRole('button',{name:'确认并发送'}));
  await screen.findByText(/恢复记录无法可靠保存/);expect(command.mock.calls.map(([v])=>v.action)).toEqual(['PREPARE']);
});
it('remounts uncertain sends as recovery-only, including queued cancellation and result resumption',async()=>{
  const first=render(view());await prepare();await confirm();await screen.findByText(/发送结果尚未确定/);first.unmount();
  command.mockClear();render(view());expect(command).not.toHaveBeenCalled();expect(screen.queryByRole('button',{name:'核对发送信息'})).toBeNull();
  const recordDetails=screen.getByText(/原请求编号：/).closest('details');
  expect(recordDetails).not.toBeNull();expect(recordDetails?.open).toBe(false);
  expect(recordDetails?.textContent).toContain(prepared.binding.requestId);
  command.mockResolvedValueOnce(result('QUEUED'));fireEvent.click(screen.getByRole('button',{name:'核对原发送结果'}));await screen.findByRole('button',{name:'取消原排队请求'});
  command.mockResolvedValueOnce(result('CANCELLED'));fireEvent.click(screen.getByRole('button',{name:'取消原排队请求'}));await screen.findByText(/原请求已取消/);
  expect(command.mock.calls.map(([v])=>v.action)).toEqual(['RECONCILE','CANCEL_QUEUED']);
});
it('resumes only the original result after remount and keeps SENT protected',async()=>{
  const first=render(view());await prepare();await confirm();await screen.findByText(/发送结果尚未确定/);first.unmount();command.mockClear();
  const second=render(view());command.mockResolvedValueOnce(result('SENT'));fireEvent.click(screen.getByRole('button',{name:'补报原发送结果'}));await screen.findByText(/渠道已确认发送成功/);second.unmount();
  render(view());expect(screen.getByText(/此版本已确认发送/)).toBeTruthy();expect(command.mock.calls.map(([v])=>v.action)).toEqual(['RESUME_RESULT']);
});
it('cancels an active flow on identity change, ignores late success, and retains original recovery metadata',async()=>{
  let release!:(value:NativeOutreachResult)=>void;
  const pending=new Promise<NativeOutreachResult>(resolve=>{release=resolve;});const current=render(view());await prepare();command.mockImplementationOnce(()=>pending);await confirm();
  const originalKey=saved()[0].key;app={...app,session:{...app.session,userId:id()}};current.rerender(view());
  await waitFor(()=>expect(command.mock.calls.some(([v])=>v.action==='CANCEL')).toBe(true));
  await act(async()=>{release(result('SENT'));});expect(app.notify).not.toHaveBeenCalled();expect(screen.queryByText(/渠道已确认发送成功/)).toBeNull();expect(localStorage.getItem(originalKey)).toContain(prepared.binding.requestId);
});
it('allows a connected XHS comment account with empty capabilities to be selected without claiming capability',async()=>{
  render(<ContactEditor row={row} renderConfirmation={()=>null}/>);await screen.findByRole('option',{name:'屏幕账号昵称 · xhs'});
  fireEvent.change(screen.getByRole('combobox',{name:'发送账号'}),{target:{value:'original-account'}});
  expect((screen.getByRole('combobox',{name:'发送账号'}) as HTMLSelectElement).value).toBe('original-account');expect(connection.capabilities).toEqual([]);
});
it('never executes a sample and retains legacy confirmation on plain web',()=>{
  row={...row,sample:true};const sample=render(view());expect(screen.queryByRole('button',{name:'核对发送信息'})).toBeNull();expect(command).not.toHaveBeenCalled();sample.unmount();
  row={...row,sample:false};delete (window as unknown as {yikeDesktop?:unknown}).yikeDesktop;render(view());expect(screen.queryByRole('button',{name:'核对发送信息'})).toBeNull();
});
it('cancels preparation when the same account gets a new connection registration',async()=>{
  connection={...connection,registration:{connectionId:id(),deviceId:id(),version:1,connectedAt:new Date().toISOString(),disconnectedAt:null}};
  const current=render(view());await prepare();connection={...connection,registration:{...connection.registration!,version:2}};current.rerender(view());
  await waitFor(()=>expect(command.mock.calls.some(([v])=>v.action==='CANCEL')).toBe(true));
  expect((screen.getByRole('button',{name:'确认并发送'}) as HTMLButtonElement).disabled).toBe(true);
});
it('retains unknown metadata and suppresses a late success after explicit modal close',async()=>{
  let release!:(value:NativeOutreachResult)=>void;const pending=new Promise<NativeOutreachResult>(resolve=>{release=resolve;});
  render(view());await prepare();command.mockImplementationOnce(()=>pending);await confirm();fireEvent.click(screen.getByRole('button',{name:'返回修改'}));
  await act(async()=>{release(result('SENT'));});expect(close).toHaveBeenCalledOnce();expect(screen.queryByText(/渠道已确认发送成功/)).toBeNull();expect(saved()[0].value).toContain('PENDING');
});
it('keeps unresolved metadata visible in the editor after closing the confirmation',async()=>{
  const initial=render(view());await prepare();await confirm();await screen.findByText(/发送结果尚未确定/);initial.unmount();
  render(<ContactEditor row={row} renderConfirmation={()=>null}/>);expect(screen.getByText(/原生发送结果待核对/)).toBeTruthy();expect(screen.getByRole('button',{name:'查看原发送记录'})).toBeTruthy();
});
it('retires only the original pending binding after a trusted NOT_SUBMITTED from CONFIRM, without automatically preparing again',async()=>{
  render(view());await prepare();
  command.mockImplementationOnce(async()=>({state:'NOT_SUBMITTED',binding:prepared.binding,error:'CHANNEL_UNVERIFIED'} as unknown as NativeOutreachResult));
  await confirm();await screen.findByText('尚未提交发送，请重新核对后确认。');
  expect(saved()).toEqual([]);expect(screen.getByRole('button',{name:'核对发送信息'})).toBeTruthy();
  expect((screen.getByRole('checkbox',{name:'我已核对联系对象、发送账号和内容'}) as HTMLInputElement).checked).toBe(false);
  expect(command.mock.calls.map(([value])=>value.action)).toEqual(['PREPARE','CONFIRM']);
});
it('keeps protection when NOT_SUBMITTED is for a different binding',async()=>{
  render(view());await prepare();
  command.mockImplementationOnce(async()=>({state:'NOT_SUBMITTED',binding:{...prepared.binding,claimId:id()},error:'CHANNEL_UNVERIFIED'} as unknown as NativeOutreachResult));
  await confirm();await screen.findByRole('button',{name:'核对原发送结果'});
  expect(saved()[0].value).toContain('PENDING');expect(saved()[0].value).toContain(prepared.binding.claimId);
  expect(screen.queryByRole('button',{name:'核对发送信息'})).toBeNull();expect(screen.queryByText('尚未提交发送，请重新核对后确认。')).toBeNull();
});
