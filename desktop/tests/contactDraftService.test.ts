import {webcrypto} from 'node:crypto';
import {describe,it,expect,vi} from 'vitest';
import {createContactDraftService} from '../src/renderer/services/contactDrafts';
import {snapshotDigest,type DraftSaveInput} from '../src/renderer/domain/shortCoach';
import {ServiceError} from '../src/renderer/services/contracts';
import {validatedOperation} from '../src/main/servicePolicy';
import {mapOpportunity} from '../src/renderer/services/client';
import {capturedEvidenceFixture} from './fixtures/opportunitySourceEvidence';

Object.defineProperty(globalThis,'crypto',{value:webcrypto,configurable:true});
const uuid=(n:number)=>`00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
const scope={id:uuid(1),version:1};
const session=async()=>({authenticated:true,userId:uuid(2),accountScope:scope});
async function input():Promise<DraftSaveInput>{
 const snapshot={draft:{opportunityId:uuid(3),channel:'dm' as const,version:2,
  content:'你好，知识库项目还在找团队吗？',savedContent:'',accountId:'account',recipient:'buyer'},
  accountScope:scope,profileVersionId:uuid(4),sourceEvidenceVersion:uuid(5)};
 return {binding:{opportunityId:uuid(3),channel:'dm',requestId:uuid(6),contentHash:await snapshotDigest(snapshot)},snapshot,previousRequestId:null};
}
const receipt=(value:DraftSaveInput)=>({binding:value.binding,status:'SUCCEEDED',confirmed:true,
 snapshot:{...value.snapshot,draft:{...value.snapshot.draft,savedContent:value.snapshot.draft.content}}});
describe('persisted contact draft service',()=>{
 it('uses captured source identity when ordinary detail has no legacy version fields',()=>{
  const evidence=capturedEvidenceFixture();
  const row=mapOpportunity({opportunity_id:'TEST-o',
   profile_version_id:'TEST-p',source_evidence:evidence,source_status:'BLOCKED'});
  if(row.sourceEvidence?.status!=='CAPTURED')throw new Error('fixture not captured');
  expect(row.sourceEvidenceVersion).toBe(row.sourceEvidence.snapshot.source.version_id);
  expect(row.sourceObservedAt).toBe(new Date(row.sourceEvidence.snapshot.observation.observed_at).toISOString());
  expect(row.sourceStatus).toBe('BLOCKED');
 });
 it('saves exact predecessor and reads/reconciles only fixed routes',async()=>{
  const value=await input(),result=receipt(value),transport=vi.fn().mockResolvedValue(result);
  const service=createContactDraftService(transport,session);
  expect(await service.save(value)).toEqual(result);
  expect(transport).toHaveBeenCalledWith('contactDrafts.save','/contact-drafts','POST',value,undefined);
  expect(await service.operation(value.binding)).toEqual(result);
  expect(await service.latest!(uuid(3),'dm')).toEqual(result);
  for(const [operation,payload,path] of [
   ['contactDrafts.save',value,'/api/ui/contact-drafts'],
   ['contactDrafts.operation',value.binding,'/api/ui/contact-drafts/operation'],
   ['contactDrafts.latest',{opportunityId:uuid(3),channel:'dm'},`/api/ui/opportunities/${uuid(3)}/contact-drafts/dm`],
  ] as const)expect(validatedOperation({operation,payload})?.path).toBe(path);
  expect(validatedOperation({operation:'contactDrafts.latest',payload:{opportunityId:'../../session',channel:'dm'}})).toBeNull();
  expect(validatedOperation({operation:'contactDrafts.save',payload:{...value,tenant_id:uuid(9)}})).toBeNull();
 });
 it('validates hash, recipient scope and session before saving, rejects malformed receipts',async()=>{
  const value=await input(),transport=vi.fn().mockResolvedValue(receipt(value));
  const service=createContactDraftService(transport,session);
  await expect(service.save({...value,snapshot:{...value.snapshot,draft:{...value.snapshot.draft,recipient:'other'}}})).rejects.toThrow();
  await expect(service.save({...value,snapshot:{...value.snapshot,accountScope:{id:uuid(9),version:1}}})).rejects.toThrow();
  await expect(createContactDraftService(transport,async()=>({authenticated:false})).save(value)).rejects.toThrow();
  expect(transport).not.toHaveBeenCalled();
  transport.mockResolvedValue({...receipt(value),binding:{...value.binding,requestId:uuid(9)}});
  await expect(service.operation(value.binding)).rejects.toThrow();
  transport.mockResolvedValue({...receipt(value),snapshot:{...value.snapshot,draft:{...value.snapshot.draft,content:'changed',savedContent:'changed'}}});
  await expect(service.latest!(uuid(3),'dm')).rejects.toThrow();
 });
 it('only a verified missing latest draft is empty; operation errors stay unknown',async()=>{
  const value=await input(),transport=vi.fn().mockRejectedValue(new ServiceError('draft_not_found','missing',404));
  const service=createContactDraftService(transport,session);
  expect(await service.latest!(uuid(3),'dm')).toBeNull();
  await expect(service.operation(value.binding)).rejects.toThrow('missing');
  for(const code of ['HTTP_404','draft_request_conflict','NETWORK_ERROR']){
   transport.mockRejectedValue(new ServiceError(code,'unknown',code==='HTTP_404'?404:409));
   await expect(service.latest!(uuid(3),'dm')).rejects.toThrow('unknown');
   await expect(service.save(value)).rejects.toThrow('unknown');
  }
 });
 it('rejects a self-consistent snapshot attached to another opportunity binding',async()=>{
  const value=await input(),snapshot={...value.snapshot,draft:{...value.snapshot.draft,opportunityId:uuid(9),savedContent:value.snapshot.draft.content}};
  const forged={...receipt(value),snapshot,binding:{...value.binding,contentHash:await snapshotDigest(snapshot)}};
  const transport=vi.fn().mockResolvedValue(forged);
  await expect(createContactDraftService(transport,session).latest!(uuid(3),'dm')).rejects.toThrow();
 });
 it('rejects late replies after account change or cancellation without re-dispatch',async()=>{
  const value=await input(),current=await session();let active=current;
  const transport=vi.fn().mockImplementation(async()=>{active={...current,userId:uuid(9)};return receipt(value);});
  await expect(createContactDraftService(transport,async()=>active).save(value)).rejects.toThrow();
  expect(transport).toHaveBeenCalledTimes(1);
  const abort=new AbortController();abort.abort();transport.mockClear();
  await expect(createContactDraftService(transport,session).latest!(uuid(3),'dm',abort.signal)).rejects.toThrow();
  expect(transport).not.toHaveBeenCalled();
 });
});
