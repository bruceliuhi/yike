/** Main-process component. Only private authenticated transport may supply grants.
 * This module neither exposes IPC nor installs a platform sender. */
import {createHash} from 'node:crypto';
import {z} from 'zod';
import type {OutreachConsumptionJournal} from './outreachConsumptionJournal';

const uuid=z.string().regex(/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
const sha=z.string().regex(/^[a-f0-9]{64}$/);
const version=z.number().int().min(1).max(2_147_483_647);
const opaque=z.string().min(1).max(512).refine(v=>v===v.trim() && !/[\x00-\x1f\x7f]/.test(v));
const time=z.string().datetime({offset:true});
const channel=z.enum(['comment','dm']);
const platform=z.enum(['BILIBILI','DOUYIN','XIAOHONGSHU','ZHIHU']);
const contextSchema=z.object({
  schemaVersion:z.literal('outreach-context-v1'),
  binding:z.object({opportunityId:uuid,channel,requestId:uuid,contentHash:sha}).strict(),
  ownerUserId:uuid,accountScope:z.object({id:uuid,version:z.literal(1)}).strict(),profileVersionId:uuid,
  draft:z.object({opportunityId:uuid,channel,content:z.string().min(1).max(8000),savedContent:z.string().max(8000),
    version,accountId:opaque,recipient:z.string().max(512)}).strict(),
  source:z.object({sourceId:uuid,evidenceVersion:uuid,evidenceSha256:sha,platform,kind:z.enum(['POST','COMMENT']),
    url:z.string().min(1).max(2048),excerpt:z.string().max(20000)}).strict(),
  target:z.object({action:z.enum(['DIRECT_MESSAGE','POST_COMMENT','COMMENT_REPLY']),authorPublicId:opaque,
    postId:opaque,commentId:opaque.nullable()}).strict(),
  connection:z.object({deviceId:uuid,connectionId:uuid,connectionVersion:version,accountPublicId:opaque,platform}).strict(),
  channelCapability:z.object({status:z.literal('UNVERIFIED'),reason:z.literal('CHANNEL_CHECK_REQUIRED')}).strict(),
  authorization:z.literal('NOT_GRANTED'),contextSha256:sha,
}).strict();
const expectedSchema=z.object({serviceOrigin:z.string().max(2048),userId:uuid,tenantId:uuid,deviceId:uuid,
  sessionId:z.string().min(1).max(256),requestId:uuid,claimId:uuid,contextSha256:sha}).strict();
const grantSchema=z.object({requestId:uuid,claimId:uuid,state:z.literal('UNKNOWN'),deliveryConfirmed:z.literal(false),
  dispatchAllowed:z.literal(true),dispatchBefore:time,context:contextSchema}).strict();
const checkSchema=z.object({status:z.literal('AVAILABLE'),contextSha256:sha,deviceId:uuid,connectionId:uuid,
  connectionVersion:version,accountPublicId:opaque,recipientId:opaque,checkedAt:time}).strict();
const proof=z.object({kind:z.enum(['ACCEPTED','REJECTED_NOT_DELIVERED']),
  externalId:z.string().regex(/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/),sha256:sha,observedAt:time}).strict();
const outcomeSchema=z.discriminatedUnion('status',[
  z.object({status:z.literal('UNKNOWN'),confirmed:z.null().optional(),confirmedNotDelivered:z.null().optional(),proof:z.null().optional()}).strict(),
  z.object({status:z.literal('SENT'),confirmed:z.literal(true),confirmedNotDelivered:z.null().optional(),proof:proof.extend({kind:z.literal('ACCEPTED')})}).strict(),
  z.object({status:z.literal('FAILED'),confirmed:z.literal(true),confirmedNotDelivered:z.literal(true),proof:proof.extend({kind:z.literal('REJECTED_NOT_DELIVERED')})}).strict(),
]);
export type OutreachContext=z.infer<typeof contextSchema>;
export type OutreachExpected=z.infer<typeof expectedSchema>;
export type NativeOutreachOutcome=z.infer<typeof outcomeSchema>;
export interface NativeOutreachChannel {
  /** Read-only, actual original account/target/channel check; never send here. */
  check(context:Readonly<OutreachContext>,signal:AbortSignal):Promise<unknown>;
  /** Fixed isolated profile; driver must check cancellation/account at action point. */
  execute(context:Readonly<OutreachContext>,operation:Readonly<{requestId:string;claimId:string;dispatchBefore:string}>,signal:AbortSignal):Promise<unknown>;
}
type Reason='INVALID_GRANT'|'SESSION_CHANGED'|'CANCELLED'|'PERMIT_EXPIRED'|'CHANNEL_UNVERIFIED'|'ALREADY_CONSUMED'|'CONSUMPTION_UNAVAILABLE'|'EXECUTION_UNKNOWN'|'RESULT_INVALID';
type Result={state:'UNKNOWN';reason:Reason;serverAccepted:false}|{
  state:'RESULT_READY';requestId:string;claimId:string;serverAccepted:false;outcome:NativeOutreachOutcome;
};
class ConsumerError extends Error {constructor(readonly reason:Reason){super(reason);}}
function fail(reason:Reason):never {throw new ConsumerError(reason);}
function canonical(value:unknown):string {
  if(typeof value==='string'){
    for(const c of value)if(/^[\ud800-\udfff]$/.test(c))throw new Error();
    return JSON.stringify(value);
  }
  if(value===null || typeof value==='boolean' || typeof value==='number' && Number.isSafeInteger(value))return JSON.stringify(value);
  if(Array.isArray(value))return '['+value.map(canonical).join(',')+']';
  if(value && typeof value==='object')return '{'+Object.entries(value).sort(([a],[b])=>a<b?-1:a>b?1:0).map(([k,v])=>JSON.stringify(k)+':'+canonical(v)).join(',')+'}';
  throw new Error();
}
function freeze<T>(value:T):T {
  if(value && typeof value==='object'){for(const child of Object.values(value))freeze(child);Object.freeze(value);}
  return value;
}
const domains={BILIBILI:['bilibili.com','b23.tv'],DOUYIN:['douyin.com','iesdouyin.com'],XIAOHONGSHU:['xiaohongshu.com','xhslink.com'],ZHIHU:['zhihu.com']};
function safeUrl(context:OutreachContext):boolean {
  try {
    const raw=context.source.url,u=new URL(raw),decoded=decodeURIComponent(raw);
    return ['https:','http:'].includes(u.protocol) && !u.username && !u.password && !u.port &&
      !raw.includes('\\') && !/[\x00-\x20\x7f-\x9f]/.test(decoded) &&
      domains[context.source.platform].some(d=>u.hostname===d || u.hostname.endsWith('.'+d)) &&
      !Array.from(u.searchParams.keys()).some(k=>/token|cookie|session|authorization|signature|password|secret/i.test(decodeURIComponent(k)));
  }catch{return false;}
}

export function createOutreachConsumer(options:{journal:OutreachConsumptionJournal;channel:NativeOutreachChannel;
  isCurrent(expected:Readonly<OutreachExpected>):boolean;now?:()=>number}) {
  const now=options.now ?? Date.now;
  return {async consume(rawExpected:unknown,rawGrant:unknown,signal:AbortSignal):Promise<Result>{
    let expected:OutreachExpected,grant:z.infer<typeof grantSchema>;
    try {
      if(Buffer.byteLength(JSON.stringify(rawGrant),'utf8')>160_000)throw new Error();
      expected=freeze(expectedSchema.parse(rawExpected));grant=freeze(grantSchema.parse(rawGrant));
      const origin=new URL(expected.serviceOrigin);
      const local=origin.protocol==='http:' && ['localhost','127.0.0.1','[::1]'].includes(origin.hostname);
      if(origin.origin!==expected.serviceOrigin || origin.username || origin.password || !(origin.protocol==='https:' || local))throw new Error();
      const c=grant.context,{contextSha256,...snapshot}=c;
      if(grant.requestId!==expected.requestId || grant.claimId!==expected.claimId || contextSha256!==expected.contextSha256 ||
        createHash('sha256').update(canonical(snapshot),'utf8').digest('hex')!==contextSha256 ||
        c.ownerUserId!==expected.userId || c.accountScope.id!==expected.tenantId || c.connection.deviceId!==expected.deviceId ||
        c.binding.opportunityId!==c.draft.opportunityId || c.binding.channel!==c.draft.channel || c.draft.content!==c.draft.savedContent ||
        c.source.platform!==c.connection.platform || c.draft.accountId!==c.connection.accountPublicId ||
        c.draft.recipient && c.draft.recipient!==c.target.authorPublicId || !safeUrl(c) ||
        (c.source.kind==='POST')!==(c.target.commentId===null) ||
        c.target.action!==(c.draft.channel==='dm'?'DIRECT_MESSAGE':c.source.kind==='POST'?'POST_COMMENT':'COMMENT_REPLY'))throw new Error();
    }catch{return {state:'UNKNOWN',reason:'INVALID_GRANT',serverAccepted:false};}
    const c=grant.context,scope={serviceOrigin:expected.serviceOrigin,userId:expected.userId,tenantId:expected.tenantId};
    function guard(){
      if(signal.aborted)fail('CANCELLED');
      if(!options.isCurrent(expected))fail('SESSION_CHANGED');
      const current=now(),deadline=Date.parse(grant.dispatchBefore);
      if(!Number.isFinite(current) || deadline<=current || deadline-current>35_000)fail('PERMIT_EXPIRED');
    }
    try {
      guard();
      try {if(await options.journal.consumed(scope,expected.requestId))fail('ALREADY_CONSUMED');}
      catch(e){if(e instanceof ConsumerError)throw e;fail('CONSUMPTION_UNAVAILABLE');}
      guard();
      let checked:z.infer<typeof checkSchema>;
      try {checked=checkSchema.parse(await options.channel.check(c,signal));}catch{fail('CHANNEL_UNVERIFIED');}
      function checkFresh(){
        const age=now()-Date.parse(checked.checkedAt);
        if(checked.contextSha256!==expected.contextSha256 || checked.deviceId!==expected.deviceId ||
          checked.connectionId!==c.connection.connectionId || checked.connectionVersion!==c.connection.connectionVersion ||
          checked.accountPublicId!==c.connection.accountPublicId || checked.recipientId!==c.target.authorPublicId ||
          !Number.isFinite(age) || age < -5_000 || age>5_000)fail('CHANNEL_UNVERIFIED');
      }
      guard();checkFresh();
      let created:boolean;
      try {created=(await options.journal.consume(scope,{requestId:expected.requestId,claimId:expected.claimId,
        contextSha256:expected.contextSha256,deviceId:expected.deviceId})).created;}
      catch{fail('CONSUMPTION_UNAVAILABLE');}
      if(!created)fail('ALREADY_CONSUMED');
      // No path after this point removes the consumed marker or retries execution.
      guard();checkFresh();const started=now();
      let raw:unknown;
      try {raw=await options.channel.execute(c,Object.freeze({requestId:expected.requestId,claimId:expected.claimId,dispatchBefore:grant.dispatchBefore}),signal);}
      catch{fail('EXECUTION_UNKNOWN');}
      // Preserve valid late receipts as facts even if session/permission changed.
      const parsed=outcomeSchema.safeParse(raw);
      if(!parsed.success)fail('RESULT_INVALID');
      const outcome=parsed.data;
      if(outcome.proof && (Date.parse(outcome.proof.observedAt)<started-5_000 || Date.parse(outcome.proof.observedAt)>now()+5_000))fail('RESULT_INVALID');
      return {state:'RESULT_READY',requestId:expected.requestId,claimId:expected.claimId,serverAccepted:false,outcome};
    }catch(error){return {state:'UNKNOWN',reason:error instanceof ConsumerError?error.reason:'EXECUTION_UNKNOWN',serverAccepted:false};}
  }};
}
