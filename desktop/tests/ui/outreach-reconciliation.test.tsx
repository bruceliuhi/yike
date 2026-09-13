// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { SendConfirmation, contactFingerprint } from '../../src/renderer/pages/Outreach';
import { PUBLIC_SAMPLE } from '../../src/renderer/pages/Opportunities';
import { clearLocalDrafts } from '../../src/renderer/app/hooks';
import { operationLedgerKey } from '../../src/renderer/app/operationLedger';
import { parseRoute } from '../../src/renderer/domain/routes';
import type { AppContextValue } from '../../src/renderer/app/context';
import type { ContactDraft, Opportunity, PlatformConnection } from '../../src/renderer/domain/models';
import type { SendRequestBinding } from '../../src/renderer/domain/outreach';
import type { YikeService } from '../../src/renderer/services/contracts';
let context:AppContextValue;let row:Opportunity;let draft:ContactDraft;let connection:PlatformConnection;
vi.mock('../../src/renderer/app/context',()=>({useApp:()=>context}));
const ledger=()=>operationLedgerKey('send-attempts',context.session.userId!);
const entries=()=>JSON.parse(localStorage.getItem(ledger())||'{}');
const mount=()=>render(<SendConfirmation row={row} draft={draft} connection={connection} onClose={vi.fn()}/>);
const sendButton=()=>screen.getByRole('button',{name:'确认并发送'}) as HTMLButtonElement;
const pending=(version=2):SendRequestBinding=>{
 const binding={requestId:'TEST-original-request',opportunityId:row.id,channel:draft.channel,version};
 localStorage.setItem(ledger(),JSON.stringify({[JSON.stringify([row.id,draft.channel,version,binding.requestId])]:'PENDING'}));return binding;
};
async function submit(){
 fireEvent.click(screen.getByRole('button',{name:'核验发送条件'}));
 await screen.findByText('TEST 已核验对象');
 fireEvent.click(screen.getByRole('checkbox',{name:'我已核对联系对象、发送账号和内容'}));
 fireEvent.click(sendButton());
 await waitFor(()=>expect(context.service.outreach!.send).toHaveBeenCalledOnce());
}
beforeEach(()=>{
 localStorage.clear();sessionStorage.clear();
 row={...PUBLIC_SAMPLE,id:'TEST-opportunity',sample:false,profileStatus:'CONFIRMED',sourceStatus:'OPEN',profileVersionId:'TEST-profile'};
 draft={opportunityId:row.id,channel:'comment',content:'TEST 草稿',savedContent:'TEST 草稿',version:2,accountId:'TEST-account',recipient:'TEST 对象'};
 connection={platform:'xhs',status:'CONNECTED',accountId:draft.accountId,capabilities:['comment']};
 context={service:{verifyContact:vi.fn().mockImplementation(()=>Promise.resolve({allowed:true,fingerprint:contactFingerprint(draft,row,connection),confirmationToken:'TEST-token',expiresAt:new Date(Date.now()+60000).toISOString(),opportunityId:row.id,accountId:draft.accountId,channel:draft.channel,recipientId:'TEST-recipient',recipientLabel:'TEST 已核验对象'})),send:vi.fn(),outreach:{queue:vi.fn(),send:vi.fn(),reconcile:vi.fn()}} as unknown as YikeService,
 session:{authenticated:true,userId:crypto.randomUUID()},route:parseRoute('#/outreach?confirm=send'),navigate:vi.fn(),notify:vi.fn(),refreshSession:vi.fn()};
});
afterEach(()=>{cleanup();vi.useRealTimers();});
describe('original send request reconciliation',()=>{
 it.each(['SENT','FAILED'] as const)('clears only the settled send error after authoritative %s reconciliation',async status=>{
  vi.mocked(context.service.outreach!.send).mockRejectedValue(new Error('TEST 发送断线，结果未知'));
  mount();await submit();
  await screen.findByText('TEST 发送断线，结果未知');
  const request=vi.mocked(context.service.outreach!.send).mock.calls[0][1];
  vi.mocked(context.service.outreach!.reconcile).mockResolvedValue({requestId:request.requestId,opportunityId:row.id,channel:draft.channel,version:draft.version,status,confirmed:true,confirmedNotDelivered:true} as never);
  fireEvent.click(screen.getByRole('button',{name:'核对原发送结果'}));
  await waitFor(()=>expect(Object.values(entries())).not.toContain('PENDING'));
  expect(screen.queryByText('TEST 发送断线，结果未知')).toBeNull();
  expect(context.notify).toHaveBeenCalledWith(status==='SENT'?'原请求已确认发送成功，不会重复发送。':'原请求已确认未送达；请重新核验并确认后发送。',status==='SENT'?'success':'info');
  expect(context.service.outreach!.send).toHaveBeenCalledOnce();
 });
 it.each(['UNKNOWN','wrong request'] as const)('retains the original send error and lock when reconciliation is %s',async outcome=>{
  vi.mocked(context.service.outreach!.send).mockRejectedValue(new Error('TEST 原发送错误'));
  mount();await submit();await screen.findByText('TEST 原发送错误');
  const request=vi.mocked(context.service.outreach!.send).mock.calls[0][1];
  vi.mocked(context.service.outreach!.reconcile).mockResolvedValue({requestId:outcome==='wrong request'?'different':request.requestId,opportunityId:row.id,channel:draft.channel,version:draft.version,status:outcome==='UNKNOWN'?'UNKNOWN':'SENT',confirmed:true} as never);
  fireEvent.click(screen.getByRole('button',{name:'核对原发送结果'}));
  await waitFor(()=>expect(context.service.outreach!.reconcile).toHaveBeenCalledOnce());
  await waitFor(()=>expect((screen.getByRole('button',{name:'核对原发送结果'}) as HTMLButtonElement).disabled).toBe(false));
  expect(screen.getByText('TEST 原发送错误')).toBeTruthy();
  expect(Object.values(entries())).toContain('PENDING');
 });
 it('does not clear a separate verification error when an older operation is settled',async()=>{
  vi.mocked(context.service.verifyContact).mockRejectedValue(new Error('TEST 当前核验读取失败'));
  const view=mount();
  fireEvent.click(screen.getByRole('button',{name:'核验发送条件'}));
  await screen.findByText('TEST 当前核验读取失败');
  const original=pending();
  vi.mocked(context.service.outreach!.reconcile).mockResolvedValue({...original,status:'FAILED',confirmed:true,confirmedNotDelivered:true});
  view.rerender(<SendConfirmation row={row} draft={draft} connection={connection} onClose={vi.fn()}/>);
  fireEvent.click(screen.getByRole('button',{name:'核对原发送结果'}));
  await waitFor(()=>expect(Object.values(entries())).not.toContain('PENDING'));
  expect(screen.getByText('TEST 当前核验读取失败')).toBeTruthy();
  expect(context.service.outreach!.send).not.toHaveBeenCalled();
 });
 it.each(['original-request pending','legacy pending','same-version sent'])('does not dispatch if %s appears while the final verification is pending',async kind=>{
  mount();
  fireEvent.click(screen.getByRole('button',{name:'核验发送条件'}));
  await screen.findByText('TEST 已核验对象');
  const proof = await vi.mocked(context.service.verifyContact).mock.results[0].value;
  let resolve!: (value: typeof proof)=>void;
  vi.mocked(context.service.verifyContact).mockImplementationOnce(()=>new Promise(r=>{resolve=r}));
  fireEvent.click(screen.getByRole('checkbox',{name:'我已核对联系对象、发送账号和内容'}));
  fireEvent.click(sendButton());
  await waitFor(()=>expect(context.service.verifyContact).toHaveBeenCalledTimes(2));
  const key = JSON.stringify(kind === 'legacy pending' ? [row.id,draft.channel] : kind === 'same-version sent' ? [row.id,draft.channel,draft.version] : [row.id,draft.channel,1,'TEST-earlier-request']);
  const latest = {[key]: kind === 'same-version sent' ? 'SENT' : 'PENDING'};
  // Write without a storage event: the final updater must re-read persistence,
  // rather than relying on a rerender having observed another window's lock.
  localStorage.setItem(ledger(),JSON.stringify(latest));
  await act(async()=>resolve(proof));
  await screen.findByText('核验期间发现已有发送记录，请先核对原请求，当前未重复发送。');
  expect(entries()).toEqual(latest);
  expect(context.service.outreach!.send).not.toHaveBeenCalled();
  expect(context.service.send).not.toHaveBeenCalled();
 });
 it('does not call a legacy FAILED string a confirmed non-delivery',async()=>{
  context.service.outreach=undefined;
  vi.mocked(context.service.send).mockResolvedValue({status:'FAILED'});
  mount();fireEvent.click(screen.getByRole('button',{name:'核验发送条件'}));
  await screen.findByText('TEST 已核验对象');
  fireEvent.click(screen.getByRole('checkbox',{name:'我已核对联系对象、发送账号和内容'}));
  fireEvent.click(sendButton());
  await waitFor(()=>expect(context.notify).toHaveBeenCalledWith('发送请求已提交，结果尚待渠道确认。','info'));
  expect(Object.values(entries())).toContain('PENDING');
  expect(sendButton().disabled).toBe(true);
  expect(context.notify).not.toHaveBeenCalledWith('渠道已确认未送达，请重新核验后再决定是否发送。','info');
 });
 it('times out an unresolved send without unlocking and ignores a late unqueried result',async()=>{
  vi.useFakeTimers(); let resolve!: (value: any)=>void;
  vi.mocked(context.service.outreach!.send).mockImplementation(()=>new Promise(r=>{resolve=r}));
  mount();
  await act(async()=>{fireEvent.click(screen.getByRole('button',{name:'核验发送条件'}));});
  fireEvent.click(screen.getByRole('checkbox',{name:'我已核对联系对象、发送账号和内容'}));
  await act(async()=>{fireEvent.click(sendButton());});
  expect(context.service.outreach!.send).toHaveBeenCalledOnce();
  await act(async()=>{await vi.advanceTimersByTimeAsync(30_001);});
  expect(screen.getByText('发送等待超时，结果尚未确定，请核对原发送结果。')).toBeTruthy();
  expect((screen.getByRole('button',{name:'核对原发送结果'}) as HTMLButtonElement).disabled).toBe(false);
  const request = vi.mocked(context.service.outreach!.send).mock.calls[0][1];
  await act(async()=>resolve({...request,opportunityId:row.id,channel:draft.channel,version:2,status:'SENT',confirmed:true}));
  expect(Object.values(entries())).toContain('PENDING');expect(sendButton().disabled).toBe(true);
 });
 it('persists an opaque original request before sending and never blindly retries unknown',async()=>{
  vi.mocked(context.service.outreach!.send).mockImplementation(async(_draft,request)=>{
   expect(Object.keys(entries())[0]).toContain(request.requestId);
   return {...request,opportunityId:row.id,channel:draft.channel,version:draft.version,status:'UNKNOWN'};
  });
  mount();await submit();
  await screen.findByRole('button',{name:'核对原发送结果'});
  expect(sendButton().disabled).toBe(true);
  expect(JSON.stringify(entries())).not.toContain('TEST 草稿');
  expect(JSON.stringify(entries())).not.toContain('TEST-token');
  fireEvent.click(sendButton());expect(context.service.outreach!.send).toHaveBeenCalledTimes(1);
  expect(context.service.send).not.toHaveBeenCalled();
 });
 it.each(['SENT','FAILED'] as const)('settles only a matching definitive %s receipt',async status=>{
  const original=pending();
  vi.mocked(context.service.outreach!.reconcile).mockResolvedValue({...original,status,confirmed:true,confirmedNotDelivered:true} as never);
  mount();fireEvent.click(screen.getByRole('button',{name:'核对原发送结果'}));
  await waitFor(()=>expect(context.service.outreach!.reconcile).toHaveBeenCalledWith(original));
  await waitFor(()=>expect(Object.values(entries())).not.toContain('PENDING'));
  if(status==='SENT'){expect(Object.values(entries())).toContain('SENT');expect(sendButton().disabled).toBe(true);}
  else {expect(entries()).toEqual({});expect(sendButton().disabled).toBe(true);await screen.findByRole('button',{name:'核验发送条件'});}
  expect(context.service.outreach!.send).not.toHaveBeenCalled();
 });
 it.each(['UNKNOWN','PENDING','not found','network error','wrong request','wrong opportunity','wrong channel','wrong version','unconfirmed failed','unconfirmed sent'])('keeps protection for %s',async kind=>{
  const original=pending();
  const receipt:any={...original,status:'SENT',confirmed:true};
  if(kind==='UNKNOWN'||kind==='PENDING')receipt.status=kind;
  if(kind==='wrong request')receipt.requestId='other';
  if(kind==='wrong opportunity')receipt.opportunityId='other';
  if(kind==='wrong channel')receipt.channel='dm';
  if(kind==='wrong version')receipt.version=3;
  if(kind==='unconfirmed failed')receipt.status='FAILED';
  if(kind==='unconfirmed sent')receipt.confirmed=false;
  if(kind==='not found'||kind==='network error')vi.mocked(context.service.outreach!.reconcile).mockRejectedValue(new Error(kind));
  else vi.mocked(context.service.outreach!.reconcile).mockResolvedValue(receipt);
  mount();fireEvent.click(screen.getByRole('button',{name:'核对原发送结果'}));
  await waitFor(()=>expect(context.service.outreach!.reconcile).toHaveBeenCalledOnce());
  await waitFor(()=>expect((screen.getByRole('button',{name:'核对原发送结果'}) as HTMLButtonElement).disabled).toBe(false));
  expect(Object.values(entries())).toContain('PENDING');expect(sendButton().disabled).toBe(true);
  expect(context.service.outreach!.send).not.toHaveBeenCalled();
 });
 it('keeps the original version across draft edits, clearing drafts and same-user remount',async()=>{
  const original=pending(1);mount();cleanup();act(()=>clearLocalDrafts());
  vi.mocked(context.service.outreach!.reconcile).mockResolvedValue({...original,status:'SENT',confirmed:true});
  mount();fireEvent.click(screen.getByRole('button',{name:'核对原发送结果'}));
  await waitFor(()=>expect(context.service.outreach!.reconcile).toHaveBeenCalledWith(original));
  await waitFor(()=>expect(entries()[JSON.stringify([row.id,'comment',1])]).toBe('SENT'));
  expect(entries()[JSON.stringify([row.id,'comment',2])]).toBeUndefined();
 });
 it('does not expose or query another user operation',()=>{
  pending();context={...context,session:{authenticated:true,userId:crypto.randomUUID()}};
  mount();expect(screen.queryByText(/TEST-original-request/)).toBeNull();
  expect(screen.queryByRole('button',{name:'核对原发送结果'})).toBeNull();
 });
 it('legacy pending locks without original IDs cannot be queried or retried',()=>{
  localStorage.setItem(ledger(),JSON.stringify({[JSON.stringify([row.id,draft.channel])]:'PENDING'}));
  mount();expect(sendButton().disabled).toBe(true);
  expect(screen.queryByRole('button',{name:'核对原发送结果'})).toBeNull();
  expect(screen.getByText(/此次发送无法直接核对/)).toBeTruthy();
 });
 it('a missing reconciliation adapter keeps the lock and reports unavailable',async()=>{
  pending();context.service.outreach=undefined;mount();
  fireEvent.click(screen.getByRole('button',{name:'核对原发送结果'}));
  await screen.findByText('触达队列与发送结果核对服务尚未接通。');
  expect(Object.values(entries())).toContain('PENDING');
 });
 it('a sample cannot use a forged pending request to query customer data',()=>{
  pending();row={...row,sample:true};mount();
  expect(screen.queryByRole('button',{name:'核对原发送结果'})).toBeNull();
  expect(sendButton().disabled).toBe(true);
 });
 it('malformed send results keep their durable lock for reconciliation',async()=>{
  vi.mocked(context.service.outreach!.send).mockResolvedValue({status:'SENT'} as never);
  mount();await submit();await screen.findByRole('button',{name:'核对原发送结果'});
  expect(Object.values(entries())).toContain('PENDING');expect(sendButton().disabled).toBe(true);
 });
});
