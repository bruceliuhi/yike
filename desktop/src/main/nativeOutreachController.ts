/** Main-owned consent flow. Renderer commands contain intent, never device/profile authority. */
import {createHash,randomUUID} from 'node:crypto';
import {z} from 'zod';
import {nativeOutreachCommandSchema,nativeOutreachDraftSchema,type NativeOutreachResult,type NativeOutreachError,type NativeOutreachBinding} from '../shared/nativeOutreach';
import {connectionRegistryRowSchema} from '../shared/platformConnection';
import {parseConnectionReceipt} from '../shared/connectionOperation';
import type {createDeviceIdentityController,DeviceWorkerScope} from './deviceIdentityController';
import type {createConnectionProfileStore} from './connectionProfileStore';
import {parseNativeOutreachContext,parseNativeOutreachObservation,type OutreachContext,type NativeOutreachChannel} from './outreachConsumer';
import {createOutreachDispatchSession} from './outreachDispatchSession';
import {draftBindingSchema,type OutreachConfirmation} from './outreachConfirmationProtocol';
import {canonicalJson} from './outreachDispatchSigner';
import {signOutreachConfirmation} from './outreachConfirmationSigner';

type SessionOptions=Parameters<typeof createOutreachDispatchSession>[0];
export type NativeOutreachDriver=NativeOutreachChannel & {stop():Promise<void>;cleanupConfirmed():boolean};
export interface NativeOutreachControllerOptions {
  serviceOrigin:string;
  identity:Pick<ReturnType<typeof createDeviceIdentityController>,'openWorkerScope'|'getStatus'>;
  store:Pick<ReturnType<typeof createConnectionProfileStore>,'read'>;
  vault:SessionOptions['vault'];journal:SessionOptions['journal'];outbox:SessionOptions['outbox'];
  driver(context:Readonly<OutreachContext>,profileId:string):NativeOutreachDriver;
  now?:()=>number;
}
const uuid=z.string().uuid();
const latestSchema=z.object({binding:draftBindingSchema,status:z.literal('SUCCEEDED'),confirmed:z.literal(true),
  snapshot:z.object({draft:nativeOutreachDraftSchema,accountScope:z.object({id:uuid,version:z.literal(1)}).strict(),
    profileVersionId:uuid,sourceEvidenceVersion:uuid}).strict()}).strict();
const rowsSchema=z.object({items:z.array(connectionRegistryRowSchema).max(10000)}).strict();
const queuedSchema=z.object({requestId:uuid,state:z.literal('QUEUED'),deliveryConfirmed:z.literal(false),dispatchAllowed:z.literal(false)}).strict();
const cancelledSchema=z.object({requestId:uuid,state:z.literal('CANCELLED'),deliveryConfirmed:z.literal(false),dispatchAllowed:z.literal(false)}).strict();
type Flow={id:string;scope:DeviceWorkerScope;context:OutreachContext;profileId:string;input:OutreachConfirmation['context'];
  binding:NativeOutreachBinding;expires:number;abort:AbortController;driver:NativeOutreachDriver|null;used:boolean;
  timer:ReturnType<typeof setInterval>|null;stopping:Promise<void>|null};
class Failure extends Error {constructor(readonly code:NativeOutreachError){super(code);}}
const fail=(code:NativeOutreachError):never=>{throw new Failure(code);};
const failed=(error:NativeOutreachError):NativeOutreachResult=>({state:'FAILED',error});
const same=(a:unknown,b:unknown)=>canonicalJson(a)===canonicalJson(b);
function freeze<T>(value:T):T {if(value && typeof value==='object'){for(const v of Object.values(value))freeze(v);Object.freeze(value);}return value;}

export function createNativeOutreachController(options:NativeOutreachControllerOptions) {
  const now=options.now??Date.now;
  let active:Flow|null=null,busy=false,closed=false,poisoned=false;
  function scopeGuard(scope:DeviceWorkerScope) {
    const status=options.identity.getStatus();
    if(closed || !scope.signal || scope.signal.aborted || !scope.session.isCurrent() || status.state!=='READY' ||
      status.deviceId!==scope.device.deviceId || status.credentialVersion!==scope.device.credentialVersion)fail('SESSION_CHANGED');
  }
  function guard(f:Flow) {
    scopeGuard(f.scope);
    if(active!==f || f.abort.signal.aborted)fail('SESSION_CHANGED');
    if(!Number.isFinite(now()) || now()>=f.expires)fail('FLOW_EXPIRED');
  }
  async function request(scope:DeviceWorkerScope,operation:string,payload?:unknown,connection=false) {
    scopeGuard(scope);
    const fn=connection?scope.transport.requestConnection:scope.transport.requestOutreach;
    if(!fn)fail('OUTREACH_FAILED');
    const response=await fn({operation,...(payload===undefined?{}:{payload})});scopeGuard(scope);
    if(!response.ok)fail('OUTREACH_FAILED');return response.data;
  }
  function stopFlow(f:Flow):Promise<void> {
    if(f.stopping)return f.stopping;
    f.abort.abort();if(f.timer){clearInterval(f.timer);f.timer=null;}
    f.stopping=(async()=>{
      try {if(f.driver){await f.driver.stop();if(!f.driver.cleanupConfirmed())throw Error();}}
      catch {poisoned=true;throw new Failure('SOURCE_STOP_FAILED');}
      finally {f.scope.close();if(!poisoned && active===f)active=null;}
    })();void f.stopping.catch(()=>{});return f.stopping;
  }
  async function facts(scope:DeviceWorkerScope,draft:z.infer<typeof nativeOutreachDraftSchema>) {
    const record=await options.store.read({serviceOrigin:options.serviceOrigin,userId:scope.session.userId,
      deviceId:scope.device.deviceId,platform:'XIAOHONGSHU'});scopeGuard(scope);
    if(!record || record.state!=='RESOLVED' || !record.registration || !record.verification ||
      record.scope.serviceOrigin!==options.serviceOrigin || record.scope.userId!==scope.session.userId ||
      record.scope.deviceId!==scope.device.deviceId || record.scope.platform!=='XIAOHONGSHU')fail('CONNECTION_CHANGED');
    const op=record.verification;
    if(op.action!=='VERIFY' || op.device_id!==scope.device.deviceId || op.platform!=='XIAOHONGSHU' ||
      op.session_ref!==`vault://platform/${record.profileId}` || op.account_public_id!==draft.accountId ||
      record.registration.account_public_id!==op.account_public_id)fail('CONNECTION_CHANGED');
    const receipt=parseConnectionReceipt(await request(scope,'connections.receipt',{request_id:op.request_id},true),op);
    if(receipt.state!=='SUCCEEDED')fail('CONNECTION_CHANGED');
    const rows=rowsSchema.parse(await request(scope,'connections.current',undefined,true)).items;
    if(new Set(rows.map(r=>r.connection_id)).size!==rows.length)fail('CONNECTION_CHANGED');
    const matches=rows.filter(r=>r.device_id===scope.device.deviceId && r.platform==='XIAOHONGSHU' && r.account_public_id===draft.accountId && r.status==='CONNECTED');
    if(matches.length!==1)fail('CONNECTION_CHANGED');const row=matches[0];
    if(row.connection_id!==receipt.connection_id || row.connection_version!==receipt.connection_version)fail('CONNECTION_CHANGED');
    const latest=latestSchema.parse(await request(scope,'outreach.draft.latest',{opportunityId:draft.opportunityId,channel:draft.channel}));
    const s=latest.snapshot,d=s.draft,b=latest.binding;
    const digest=createHash('sha256').update(JSON.stringify([d.opportunityId,d.channel,d.version,d.content,d.accountId,d.recipient,s.profileVersionId,s.sourceEvidenceVersion,s.accountScope])).digest('hex');
    if(!same(d,draft) || d.content!==d.savedContent || !d.content.trim() || b.opportunityId!==d.opportunityId || b.channel!==d.channel || b.contentHash!==digest)fail('DRAFT_CHANGED');
    const input={binding:b,deviceId:scope.device.deviceId,connectionId:row.connection_id,connectionVersion:row.connection_version};
    const context=parseNativeOutreachContext(await request(scope,'outreach.context',input));
    const {contextSha256,...snapshot}=context;
    if(createHash('sha256').update(canonicalJson(snapshot)).digest('hex')!==contextSha256 || !same(context.binding,b) ||
      !same(context.draft,d) || !same(context.accountScope,s.accountScope) || context.ownerUserId!==scope.session.userId ||
      context.profileVersionId!==s.profileVersionId || context.source.evidenceVersion!==s.sourceEvidenceVersion ||
      context.connection.deviceId!==input.deviceId || context.connection.connectionId!==input.connectionId ||
      context.connection.connectionVersion!==input.connectionVersion || context.connection.accountPublicId!==d.accountId ||
      context.connection.platform!=='XIAOHONGSHU' || context.source.platform!=='XIAOHONGSHU' ||
      d.recipient && d.recipient!==context.target.authorPublicId)fail('DRAFT_CHANGED');
    return {context:freeze(context),input:freeze(input),profileId:uuid.parse(record.profileId)};
  }
  function session(channel:NativeOutreachChannel,flow?:Flow) {
    const identity=flow?{openWorkerScope:async()=>{
      guard(flow);const opened=await options.identity.openWorkerScope();guard(flow);
      if(opened.ok && (opened.scope.session.userId!==flow.scope.session.userId || opened.scope.session.sessionId!==flow.scope.session.sessionId ||
        opened.scope.device.deviceId!==flow.scope.device.deviceId || opened.scope.device.credentialVersion!==flow.scope.device.credentialVersion)){
        opened.scope.close();fail('SESSION_CHANGED');}
      return opened;
    }}:options.identity;
    return createOutreachDispatchSession({...options,identity,channel});
  }
  const noChannel:NativeOutreachChannel={check:async()=>{throw Error();},execute:async()=>{throw Error();}};
  async function confirm(f:Flow):Promise<NativeOutreachResult> {
    guard(f);
    const fresh=await facts(f.scope,f.context.draft);guard(f);
    if(!same(fresh.context,f.context) || fresh.profileId!==f.profileId || !same(fresh.input,f.input))fail('DRAFT_CHANGED');
    f.driver=options.driver(f.context,f.profileId);
    const signal=AbortSignal.any([f.abort.signal,f.scope.signal!]);
    const checked=parseNativeOutreachObservation(await f.driver.check(f.context,signal));guard(f);
    const age=now()-Date.parse(checked.checkedAt),c=f.context;
    if(age < -5000 || age>5000 || !Number.isFinite(age) || checked.contextSha256!==c.contextSha256 ||
      checked.deviceId!==c.connection.deviceId || checked.connectionId!==c.connection.connectionId ||
      checked.connectionVersion!==c.connection.connectionVersion || checked.accountPublicId!==c.connection.accountPublicId ||
      checked.recipientId!==c.target.authorPublicId)fail('CHANNEL_UNVERIFIED');
    const value:OutreachConfirmation={requestId:f.binding.requestId,context:f.input,contextSha256:c.contextSha256,
      credentialVersion:f.scope.device.credentialVersion,humanConfirmed:true,channelCheck:{status:'AVAILABLE',observedAt:checked.checkedAt}};
    const key=await options.vault.read({serviceOrigin:options.serviceOrigin,userId:f.scope.session.userId,deviceId:f.scope.device.deviceId});guard(f);
    if(!key)fail('DEVICE_NOT_READY');
    const prepared=await request(f.scope,'outreach.confirmation.prepare',{request:value});guard(f);
    const signed=signOutreachConfirmation({key,prepared,expected:{serviceOrigin:options.serviceOrigin,userId:f.scope.session.userId,tenantId:f.binding.tenantId,request:value}});
    let receipt:unknown;
    try {receipt=await request(f.scope,'outreach.confirmation.apply',signed);guard(f);}catch{fail('CONFIRMATION_UNCONFIRMED');}
    const queued=queuedSchema.safeParse(receipt);
    if(!queued.success || queued.data.requestId!==f.binding.requestId)fail('CONFIRMATION_UNCONFIRMED');
    const channel:NativeOutreachChannel={
      async check(context,abort) {
        guard(f);if(!same(context,f.context))fail('DRAFT_CHANGED');
        const elapsed=now()-Date.parse(checked.checkedAt);
        if(elapsed < -5000 || elapsed>5000){
          await f.driver!.stop();
          if(!f.driver!.cleanupConfirmed()){poisoned=true;fail('SOURCE_STOP_FAILED');}
          guard(f);f.driver=options.driver(f.context,f.profileId);
        }
        // Existing driver owns its <=5s read-only cache; never manufacture a new timestamp.
        return f.driver!.check(context,abort);
      },
      async execute(context,operation,abort){guard(f);if(!same(context,f.context))fail('DRAFT_CHANGED');return f.driver!.execute(context,operation,abort);},
    };
    return {state:'RESULT',binding:f.binding,result:await session(channel,f).dispatch(f.binding,signal)};
  }
  return {
    async execute(raw:unknown):Promise<NativeOutreachResult> {
      const parsed=nativeOutreachCommandSchema.safeParse(raw);if(!parsed.success)return failed('INVALID_REQUEST');
      const command=parsed.data;
      if(poisoned)return failed('SOURCE_STOP_FAILED');if(closed)return failed('SESSION_CHANGED');
      if(command.action==='CANCEL'){
        if(!active || active.id!==command.flowId)return failed('INVALID_REQUEST');
        try{await stopFlow(active);return {state:'CANCELLED'};}catch{return failed('SOURCE_STOP_FAILED');}
      }
      if(busy)return failed('BUSY');busy=true;
      let scope:DeviceWorkerScope|undefined;
      try {
        if(command.action==='PREPARE'){
          if(active)return failed('BUSY');
          const opened=await options.identity.openWorkerScope();if(!opened.ok)return failed('DEVICE_NOT_READY');
          scope={...opened.scope,session:{...opened.scope.session},device:{...opened.scope.device}};scopeGuard(scope);
          const prepared=await facts(scope,command.draft);scopeGuard(scope);
          const f:Flow={id:randomUUID(),scope,...prepared,binding:freeze({tenantId:prepared.context.accountScope.id,requestId:command.requestId,
            claimId:randomUUID(),contextSha256:prepared.context.contextSha256}),expires:now()+120000,abort:new AbortController(),driver:null,used:false,timer:null,stopping:null};
          active=f;scope=undefined;
          f.timer=setInterval(()=>{try{guard(f);}catch{void stopFlow(f).catch(()=>{});}},100);f.timer.unref?.();
          return {state:'PREPARED',flowId:f.id,binding:f.binding,context:f.context};
        }
        if(command.action==='CONFIRM'){
          const f=active;if(!f || f.id!==command.flowId || f.used)return failed('INVALID_REQUEST');f.used=true;
          try{return await confirm(f);}finally{await stopFlow(f).catch(()=>{});}
        }
        if(active)return failed('BUSY');
        if(command.action==='CANCEL_QUEUED'){
          const opened=await options.identity.openWorkerScope();if(!opened.ok)return failed('DEVICE_NOT_READY');scope=opened.scope;
          const receipt=cancelledSchema.parse(await request(scope,'outreach.confirmation.cancel',{requestId:command.binding.requestId}));
          if(receipt.requestId!==command.binding.requestId)fail('CONFIRMATION_UNCONFIRMED');
          return {state:'RESULT',binding:command.binding,result:{state:'RECONCILED',serverAccepted:true,receipt}};
        }
        const s=session(noChannel),signal=new AbortController().signal;
        const result=command.action==='RECONCILE'?await s.reconcile(command.binding,signal):await s.resumeResult(command.binding,signal);
        return {state:'RESULT',binding:command.binding,result};
      }catch(error){return failed(poisoned?'SOURCE_STOP_FAILED':error instanceof Failure?error.code:'OUTREACH_FAILED');}
      finally{try{scope?.close();}catch{}busy=false;}
    },
    async stop(){closed=true;if(active)await stopFlow(active);if(poisoned)throw new Failure('SOURCE_STOP_FAILED');},
  };
}
