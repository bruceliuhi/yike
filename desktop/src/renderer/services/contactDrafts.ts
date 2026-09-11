import type {ApiOperation} from '../../shared/contracts';
import {contactDraftLatestSchema,contactDraftOperationSchema,contactDraftSaveSchema} from '../../shared/contactDrafts';
import {draftSaveReceiptSchema,readDraftSaveReceipt,snapshotDigest,type DraftSaveBinding,type DraftSaveReceipt} from '../domain/shortCoach';
import type {Session} from '../domain/models';
import {ServiceError} from './contracts';
import type {ContactDraftService} from './shortCoach';

type Transport=(operation:ApiOperation,path:string,method?:string,payload?:unknown,signal?:AbortSignal)=>Promise<unknown>;
const abort=(signal?:AbortSignal)=>signal?.throwIfAborted();
const sessionKey=(session:Session)=>JSON.stringify([session.authenticated,session.userId,session.accountScope?.id,session.accountScope?.version]);
function checkScope(scope:{id:string;version:number}|null,current:Session){
 if(scope?.id!==current.accountScope?.id||scope?.version!==current.accountScope?.version)
  throw new Error('草稿不属于当前客户空间，输入及原请求保护已保留。');
}

/** Owner is always resolved by server authentication. Reads do not create a
 * predecessor; only the editor's explicit adoption/success advances its base. */
export function createContactDraftService(transport:Transport,session:()=>Promise<Session>):ContactDraftService {
 async function active(signal?:AbortSignal){
  abort(signal);const current=await session();abort(signal);
  if(!current.authenticated||!current.userId)throw new Error('请先登录再读取或保存草稿。');
  return current;
 }
 async function unchanged(before:Session,signal?:AbortSignal){
  if(sessionKey(await active(signal))!==sessionKey(before))throw new Error('账户已切换，原草稿操作尚未确认，请在原账户核对。');
 }
 async function receive(raw:unknown,binding:DraftSaveBinding,before:Session,signal?:AbortSignal){
  const receipt=await readDraftSaveReceipt(raw,binding);
  if(receipt.snapshot){
   if(receipt.snapshot.draft.opportunityId!==binding.opportunityId||receipt.snapshot.draft.channel!==binding.channel)
    throw new Error('草稿快照与商机或用途不一致，保护继续保留。');
   checkScope(receipt.snapshot.accountScope,before);
  }
  await unchanged(before,signal);
  return receipt;
 }
 return {
  async save(input){
   // The editor removes confirmation metadata from its snapshot; strip only
   // undefined (not a real fingerprint) for strict wire validation.
   const draft={...input.snapshot.draft};
   if(draft.confirmedFingerprint===undefined)delete draft.confirmedFingerprint;
   const value=contactDraftSaveSchema.parse({...input,snapshot:{...input.snapshot,draft}});
   const before=await active();checkScope(value.snapshot.accountScope,before);
   if(await snapshotDigest(value.snapshot)!==value.binding.contentHash)throw new Error('草稿摘要与正文不一致，尚未提交。');
   await unchanged(before);
   const raw=await transport('contactDrafts.save','/contact-drafts','POST',value,undefined);
   return receive(raw,value.binding,before);
  },
  async operation(binding){
   const value=contactDraftOperationSchema.parse(binding),before=await active();
   const raw=await transport('contactDrafts.operation','/contact-drafts/operation','POST',value,undefined);
   return receive(raw,value,before);
  },
  async latest(opportunityId,channel,signal){
   const value=contactDraftLatestSchema.parse({opportunityId,channel}),before=await active(signal);
   let raw:unknown;
   try{
    raw=await transport('contactDrafts.latest',`/opportunities/${encodeURIComponent(value.opportunityId)}/contact-drafts/${value.channel}`,'GET',value,signal);
   }catch(error){
    await unchanged(before,signal);
    if(error instanceof ServiceError&&error.status===404&&error.code==='draft_not_found')return null;
    throw error;
   }
   abort(signal);
   const receipt:DraftSaveReceipt=draftSaveReceiptSchema.parse(raw);
   if(receipt.status!=='SUCCEEDED'||receipt.binding.opportunityId!==value.opportunityId||receipt.binding.channel!==value.channel)
    throw new Error('最新草稿回执不匹配，当前文字未更改。');
   contactDraftOperationSchema.parse(receipt.binding);
   return receive(receipt,receipt.binding,before,signal);
  },
 };
}
