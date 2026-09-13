// @vitest-environment jsdom
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {act,cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {NativeReplySync} from '../../src/renderer/pages/followups/NativeReplySync';
import {nativeOutreachLedgerKey,writeNativeOutreachRecord} from '../../src/renderer/pages/outreach/nativeOutreachLedger';
import {PUBLIC_SAMPLE} from '../../src/renderer/pages/Opportunities';
import type {Session} from '../../src/renderer/domain/models';
import type {ReplyEvidence} from '../../src/shared/replyEvidence';
import {nativeReplyCommandSchema,nativeReplyResultSchema} from '../../src/shared/nativeReply';

const id=()=>crypto.randomUUID();
let session:Session,opportunity:any,requestId:string,command:ReturnType<typeof vi.fn>;
function saveOriginal(state:'PENDING'|'SENT'='PENDING'){
  const key=nativeOutreachLedgerKey(session,opportunity.id,'comment')!;
  writeNativeOutreachRecord(key,{state,binding:{tenantId:session.accountScope!.id,requestId,claimId:id(),contextSha256:'a'.repeat(64)}});
}
function evidence(replyRequestId=requestId):ReplyEvidence {
  return {revision:1,event:{schema_version:'reply-event-v1',event_id:id(),user_id:session.userId!,tenant_id:session.accountScope!.id,
    opportunity_id:opportunity.id,source_id:id(),outreach_request_id:replyRequestId,profile_version_id:id(),state:'ACTIVE',observed_at:'2026-09-12T01:00:00Z',
    corrects_event_id:null,reason:null,kind:'PLATFORM_REPLY',platform:'XIAOHONGSHU',channel:'comment',external_reply_id:'r1',sender_public_id:'buyer',body:'reply',received_at:'2026-09-12T00:59:00Z',read_state:'UNKNOWN',read_at:null},verification:{
      authority:'DEVICE_ATTESTED_PLATFORM_REPLY',schemaVersion:'device-reply-attestation-v1',deviceId:id(),credentialVersion:1,claimId:id(),
      contextSha256:'b'.repeat(64),requestSha256:'c'.repeat(64),replyEventSha256:'d'.repeat(64),verifiedAt:'2026-09-12T01:00:00Z',
    }};
}
beforeEach(()=>{
  localStorage.clear();requestId=id();session={authenticated:true,userId:id(),accountScope:{id:id(),version:1}};
  opportunity={...PUBLIC_SAMPLE,id:id(),sample:false,platform:'xhs'};
  command=vi.fn().mockResolvedValue({state:'SYNCED',requestId,coverage:'PARTIAL',observed:3,recorded:2});
  Object.defineProperty(window,'yikeDesktop',{configurable:true,value:{nativeReplyCommand:command}});
});
afterEach(()=>{cleanup();delete (window as any).yikeDesktop;vi.restoreAllMocks();});

it('accepts only the strict renderer command and bounded result contract',()=>{
  expect(nativeReplyCommandSchema.safeParse({action:'SYNC',opportunityId:id(),requestId:id()}).success).toBe(true);
  expect(nativeReplyCommandSchema.safeParse({action:'SYNC',opportunityId:id(),requestId:id(),body:'private'}).success).toBe(false);
  expect(nativeReplyResultSchema.safeParse({state:'SYNCED',requestId:id(),coverage:'COMPLETE',observed:-1,recorded:0}).success).toBe(false);
});

it('offers an empty-evidence ledger request and sends only the exact sync payload',async()=>{
  saveOriginal();render(<NativeReplySync session={session} opportunity={opportunity} evidence={[]} onSynced={vi.fn()}/>);
  const technical=screen.getByText(`原请求编号：${requestId}`).closest('details');
  expect(technical).not.toBeNull();expect(technical!.open).toBe(false);
  fireEvent.click(screen.getByRole('button',{name:'同步此联系的回复'}));
  await screen.findByText('部分范围读取：3 条；保存并核实：2 条（包含去重结果）。');
  expect(command).toHaveBeenCalledWith({action:'SYNC',opportunityId:opportunity.id,requestId});
});

it('deduplicates ledger and evidence requests and refreshes after partial success or failure',async()=>{
  saveOriginal('SENT');const reload=vi.fn();const view=render(<NativeReplySync session={session} opportunity={opportunity} evidence={[evidence()]} onSynced={reload}/>);
  expect(screen.getAllByRole('button',{name:'同步此联系的回复'})).toHaveLength(1);
  fireEvent.click(screen.getByRole('button',{name:'同步此联系的回复'}));await screen.findByText(/部分范围读取/);expect(reload).toHaveBeenCalledOnce();
  command.mockResolvedValueOnce({state:'FAILED',error:'SOURCE_UNAVAILABLE',recorded:1});
  fireEvent.click(screen.getByRole('button',{name:'同步此联系的回复'}));
  await screen.findByText('原生回复来源暂不可用。已保存并核实：1 条（包含去重结果）。');expect(reload).toHaveBeenCalledTimes(2);view.unmount();
});

it('does not expose an id field and explains missing originals and desktop bridge',()=>{
  delete (window as any).yikeDesktop;
  const view=render(<NativeReplySync session={session} opportunity={opportunity} evidence={[]} onSynced={vi.fn()}/>);
  expect(screen.queryByRole('textbox')).toBeNull();expect(screen.queryByText(/手工填写请求/)).toBeNull();expect(screen.getByText(/需先完成并核实原生联系/)).toBeTruthy();view.unmount();
  render(<NativeReplySync session={session} opportunity={opportunity} evidence={[evidence()]} onSynced={vi.fn()}/>);
  expect(screen.getByText(/请在意客AI桌面客户端中同步/)).toBeTruthy();expect(command).not.toHaveBeenCalled();
});

it('never calls native sync for sample, logged-out, or non-XHS opportunities',()=>{
  const props={session,opportunity,evidence:[evidence()],onSynced:vi.fn()};
  const view=render(<NativeReplySync {...props} opportunity={{...opportunity,sample:true}}/>);view.rerender(<NativeReplySync {...props} session={{authenticated:false}}/>);view.rerender(<NativeReplySync {...props} opportunity={{...opportunity,platform:'douyin'}}/>);
  expect(screen.queryByRole('button',{name:/同步此联系的回复/})).toBeNull();expect(command).not.toHaveBeenCalled();
});

it('ignores a late result after identity and opportunity change',async()=>{
  saveOriginal();let release!:(value:any)=>void;command.mockReturnValue(new Promise(resolve=>{release=resolve;}));
  const reload=vi.fn(),view=render(<NativeReplySync session={session} opportunity={opportunity} evidence={[]} onSynced={reload}/>);
  fireEvent.click(screen.getByRole('button',{name:'同步此联系的回复'}));
  const next={...opportunity,id:id()};view.rerender(<NativeReplySync session={{...session,userId:id()}} opportunity={next} evidence={[]} onSynced={reload}/>);
  await act(async()=>release({state:'SYNCED',requestId,coverage:'COMPLETE',observed:1,recorded:1}));
  expect(screen.queryByText(/完整范围读取/)).toBeNull();expect(reload).not.toHaveBeenCalled();
});

it('treats a mismatched or malformed result as unconfirmed and does not reload',async()=>{
  saveOriginal();const reload=vi.fn();command.mockResolvedValue({state:'SYNCED',requestId:id(),coverage:'COMPLETE',observed:1,recorded:1});
  render(<NativeReplySync session={session} opportunity={opportunity} evidence={[]} onSynced={reload}/>);
  fireEvent.click(screen.getByRole('button',{name:'同步此联系的回复'}));await screen.findByText('本次同步结果未确认，请稍后核对保存证据。');expect(reload).not.toHaveBeenCalled();
});

it('distinguishes multiple contacts with stable ordinals and preserves exact request binding',async()=>{
  const first='11111111-1111-4111-8111-111111111111',second='22222222-2222-4222-8222-222222222222';
  const view=render(<NativeReplySync session={session} opportunity={opportunity} evidence={[evidence(second),evidence(first)]} onSynced={vi.fn()}/>);
  expect(screen.getByRole('button',{name:'同步此联系的回复 · 联系 1'})).toBeTruthy();
  expect(screen.getByRole('button',{name:'同步此联系的回复 · 联系 2'})).toBeTruthy();
  view.rerender(<NativeReplySync session={session} opportunity={opportunity} evidence={[evidence(first),evidence(second)]} onSynced={vi.fn()}/>);
  fireEvent.click(screen.getByRole('button',{name:'同步此联系的回复 · 联系 2'}));
  await waitFor(()=>expect(command).toHaveBeenCalledWith({action:'SYNC',opportunityId:opportunity.id,requestId:second}));
  expect(screen.getByText(`原请求编号：${second}`).closest('details')!.open).toBe(false);
});
