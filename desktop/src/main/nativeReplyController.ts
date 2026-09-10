/** Main-owned explicit reply sync. Renderer supplies only an original-request hint. */
import {createHash,randomUUID} from 'node:crypto';
import {z} from 'zod';
import {nativeReplyCommandSchema,type NativeReplyResult,type NativeReplyError} from '../shared/nativeReply';
import {connectionRegistryRowSchema} from '../shared/platformConnection';
import {parseConnectionReceipt} from '../shared/connectionOperation';
import {readReplyEvidence} from '../shared/replyEvidence';
import {canonicalJson} from './outreachDispatchSigner';
import {signNativeReply} from './nativeReplySigner';
import {nativeReplyRequestSchema,parseNativeReplyBatch,type NativeReplyRequest} from './nativeReplyProtocol';
import {parseNativeOutreachContext,parseNativeOutreachObservation,type OutreachContext} from './outreachConsumer';
import type {NativeOutreachControllerOptions} from './nativeOutreachController';
import type {DeviceWorkerScope} from './deviceIdentityController';
import type {createPlatformOutreachDriver} from './platformOutreachDriver';

type Driver=Pick<ReturnType<typeof createPlatformOutreachDriver>,'check'|'readReplies'|'stop'|'cleanupConfirmed'>;
type Options=Pick<NativeOutreachControllerOptions,'serviceOrigin'|'identity'|'store'|'vault'> & {
  driver(context:Readonly<OutreachContext>,profileId:string):Driver;
};
const uuid=z.string().uuid(),time=z.string().datetime({offset:true});
const sourceSchema=z.object({schemaVersion:z.literal('reply-sync-context-v1'),context:z.unknown(),claimId:uuid,
  claimedAt:time,rootCommentId:z.string().regex(/^[a-f0-9]{24}$/),deviceId:uuid,
  credentialVersion:z.number().int().positive().max(2147483647)}).strict();
const rowsSchema=z.object({items:z.array(connectionRegistryRowSchema).max(10000)}).strict();
const hash=(value:unknown)=>createHash('sha256').update(canonicalJson(value)).digest('hex');
class Failure extends Error {constructor(readonly code:NativeReplyError){super(code);}}
const fail=(code:NativeReplyError):never=>{throw new Failure(code);};
const failed=(error:NativeReplyError,recorded=0):NativeReplyResult=>({state:'FAILED',error,recorded});
function freeze<T>(value:T):T {if(value&&typeof value==='object'){Object.values(value).forEach(freeze);Object.freeze(value);}return value;}
// Pydantic normalizes UTC timestamps to zero or six fractional digits. Preserve
// the reader's microseconds so signing compares the same bytes as the server.
function eventTime(raw:string):string {
  time.parse(raw);
  const fraction=(raw.match(/\.(\d+)(?:Z|[+-]\d{2}:\d{2})$/)?.[1]??'').slice(0,6).padEnd(6,'0');
  return new Date(raw).toISOString().slice(0,19)+(fraction==='000000'?'':'.'+fraction)+'Z';
}

export function createNativeReplyController(options:Options){
  let closed=false,poisoned=false,running:Promise<NativeReplyResult>|null=null;
  let active:{abort:AbortController;stop:()=>Promise<void>}|null=null;
  async function run(command:{opportunityId:string;requestId:string}):Promise<NativeReplyResult>{
    let scope:DeviceWorkerScope|undefined,driver:Driver|undefined,stopping:Promise<void>|undefined;
    let timer:ReturnType<typeof setInterval>|undefined,recorded=0,answer:NativeReplyResult=failed('REPLY_SYNC_FAILED');
    const abort=new AbortController();
    const stopDriver=()=>stopping??(stopping=(async()=>{
      if(!driver)return;
      try{await driver.stop();if(!driver.cleanupConfirmed())throw Error();}
      catch{poisoned=true;throw new Failure('SOURCE_STOP_FAILED');}
    })());
    const abortRead=()=>{abort.abort();if(driver)void stopDriver().catch(()=>{});};
    active={abort,stop:async()=>{abortRead();if(driver)await stopDriver();}};
    function guard(){
      const status=options.identity.getStatus();
      if(closed||abort.signal.aborted||!scope?.signal||scope.signal.aborted||!scope.session.isCurrent()||
        status.state!=='READY'||status.deviceId!==scope.device.deviceId||status.credentialVersion!==scope.device.credentialVersion)fail('SESSION_CHANGED');
    }
    async function request(operation:string,payload?:unknown,connection=false){
      guard();const fn=connection?scope!.transport.requestConnection:scope!.transport.requestOutreach;
      if(!fn)fail('REPLY_SYNC_FAILED');
      const result=await fn({operation,...(payload===undefined?{}:{payload})});guard();
      if(!result.ok)fail(operation==='replies.source'?'SOURCE_UNAVAILABLE':'REPLY_SYNC_FAILED');return result.data;
    }
    try{
      if(closed)fail('SESSION_CHANGED');
      const opened=await options.identity.openWorkerScope();if(!opened.ok)fail('DEVICE_NOT_READY');
      scope={...opened.scope,session:{...opened.scope.session},device:{...opened.scope.device}};guard();
      scope.signal!.addEventListener('abort',abortRead,{once:true});
      timer=setInterval(()=>{try{guard();}catch{abortRead();}},100);timer.unref?.();
      const source=sourceSchema.parse(await request('replies.source',{requestId:command.requestId,...scope.device}));
      const context=freeze(parseNativeOutreachContext(source.context)),{contextSha256,...plain}=context;
      const c=context.connection,t=context.target,d=context.draft;
      if(source.deviceId!==scope.device.deviceId||source.credentialVersion!==scope.device.credentialVersion||
        context.ownerUserId!==scope.session.userId||context.binding.opportunityId!==command.opportunityId||d.opportunityId!==command.opportunityId||
        contextSha256!==hash(plain)||c.deviceId!==scope.device.deviceId||c.platform!=='XIAOHONGSHU'||context.source.platform!=='XIAOHONGSHU'||
        context.source.kind!=='POST'||t.action!=='POST_COMMENT'||t.commentId!==null||d.channel!=='comment'||context.binding.channel!=='comment'||
        d.content!==d.savedContent||d.accountId!==c.accountPublicId||d.recipient!==t.authorPublicId)fail('SOURCE_UNAVAILABLE');
      const record=await options.store.read({serviceOrigin:options.serviceOrigin,userId:scope.session.userId,deviceId:scope.device.deviceId,platform:'XIAOHONGSHU'});guard();
      if(!record||record.state!=='RESOLVED'||!record.registration||!record.verification||record.scope.serviceOrigin!==options.serviceOrigin||
        record.scope.userId!==scope.session.userId||record.scope.deviceId!==scope.device.deviceId||record.scope.platform!=='XIAOHONGSHU')fail('CONNECTION_CHANGED');
      const op=record.verification;
      if(op.action!=='VERIFY'||op.device_id!==c.deviceId||op.platform!=='XIAOHONGSHU'||op.account_public_id!==c.accountPublicId||
        op.session_ref!==`vault://platform/${record.profileId}`||record.registration.account_public_id!==c.accountPublicId)fail('CONNECTION_CHANGED');
      const receipt=parseConnectionReceipt(await request('connections.receipt',{request_id:op.request_id},true),op);
      const rows=rowsSchema.parse(await request('connections.current',undefined,true)).items;
      const matches=rows.filter(r=>r.device_id===c.deviceId&&r.platform===c.platform&&r.account_public_id===c.accountPublicId&&r.status==='CONNECTED');
      if(receipt.state!=='SUCCEEDED'||new Set(rows.map(r=>r.connection_id)).size!==rows.length||matches.length!==1||
        matches[0].connection_id!==c.connectionId||matches[0].connection_version!==c.connectionVersion||
        receipt.connection_id!==c.connectionId||receipt.connection_version!==c.connectionVersion)fail('CONNECTION_CHANGED');
      const key=await options.vault.read({serviceOrigin:options.serviceOrigin,userId:scope.session.userId,deviceId:scope.device.deviceId});guard();
      if(!key)fail('DEVICE_NOT_READY');
      driver=options.driver(context,uuid.parse(record.profileId));
      const signal=AbortSignal.any([abort.signal,scope.signal!]);
      const check=parseNativeOutreachObservation(await driver.check(context,signal));guard();
      const age=Date.now()-Date.parse(check.checkedAt);
      if(check.contextSha256!==contextSha256||check.deviceId!==c.deviceId||check.connectionId!==c.connectionId||check.connectionVersion!==c.connectionVersion||
        check.accountPublicId!==c.accountPublicId||check.recipientId!==t.authorPublicId||age < -5000||age>5000)fail('SOURCE_UNAVAILABLE');
      const batch=parseNativeReplyBatch(await driver.readReplies(context,{rootCommentId:source.rootCommentId,claimedAt:source.claimedAt},signal),t.authorPublicId,source.claimedAt);guard();
      await stopDriver();guard();
      for(const item of batch.items){
        const value:NativeReplyRequest=nativeReplyRequestSchema.parse({...scope.device,claimId:source.claimId,contextSha256,event:{
          schema_version:'reply-event-v1',kind:'PLATFORM_REPLY',event_id:randomUUID(),tenant_id:context.accountScope.id,user_id:scope.session.userId,
          opportunity_id:command.opportunityId,source_id:context.source.sourceId,profile_version_id:context.profileVersionId,outreach_request_id:command.requestId,
          state:'ACTIVE',observed_at:eventTime(item.observedAt),corrects_event_id:null,reason:null,platform:'XIAOHONGSHU',channel:'comment',
          external_reply_id:item.externalReplyId,sender_public_id:item.senderPublicId,body:item.body,received_at:eventTime(item.receivedAt),read_state:'UNKNOWN',read_at:null}});
        const prepared=await request('replies.prepare',{request:value});guard();
        const signed=signNativeReply({key,prepared,expected:{serviceOrigin:options.serviceOrigin,userId:scope.session.userId,tenantId:context.accountScope.id,request:value}});
        const saved=readReplyEvidence([await request('replies.record',signed)],{userId:scope.session.userId,tenantId:context.accountScope.id,opportunityId:command.opportunityId}).history[0];
        const e=saved.event,p=saved.verification,{event_id:_id,observed_at:_time,...expectedEvent}=value.event;
        const {event_id:_savedId,observed_at:savedTime,...actualEvent}=e;
        if(canonicalJson(expectedEvent)!==canonicalJson(actualEvent)||Date.parse(savedTime)>Date.parse(value.event.observed_at)||
          p.authority!=='DEVICE_ATTESTED_PLATFORM_REPLY'||p.deviceId!==c.deviceId||p.claimId!==source.claimId||p.contextSha256!==contextSha256||
          p.replyEventSha256!==hash(e)||p.requestSha256!==hash({...value,event:e,credentialVersion:p.credentialVersion}))fail('REPLY_SYNC_FAILED');
        recorded++;
      }
      answer={state:'SYNCED',requestId:command.requestId,coverage:batch.status,observed:batch.items.length,recorded};
    }catch(error){answer=failed(error instanceof Failure?error.code:'REPLY_SYNC_FAILED',recorded);}
    finally{
      if(timer)clearInterval(timer);scope?.signal?.removeEventListener('abort',abortRead);
      try{if(driver)await stopDriver();}catch{answer=failed('SOURCE_STOP_FAILED',recorded);}
      try{scope?.close();}catch{answer=failed('SESSION_CHANGED',recorded);}active=null;
    }
    return answer;
  }
  return {
    execute(raw:unknown):Promise<NativeReplyResult>{
      const parsed=nativeReplyCommandSchema.safeParse(raw);if(!parsed.success)return Promise.resolve(failed('INVALID_REQUEST'));
      if(poisoned)return Promise.resolve(failed('SOURCE_STOP_FAILED'));if(closed)return Promise.resolve(failed('SESSION_CHANGED'));
      if(running)return Promise.resolve(failed('BUSY'));
      const task=run(parsed.data);running=task;void task.finally(()=>{if(running===task)running=null;});return task;
    },
    async stop(){closed=true;await active?.stop();await running;if(poisoned)throw new Failure('SOURCE_STOP_FAILED');},
  };
}
