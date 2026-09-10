import {describe,it,expect,vi} from 'vitest';
import {createHash,generateKeyPairSync,randomUUID,verify} from 'node:crypto';
import {createServer} from 'node:http';
import {createServiceClient} from '../src/main/serviceClient';
import {createOutreachDispatchSession} from '../src/main/outreachDispatchSession';

const canonical=(value:any):string=>value && typeof value==='object' && !Array.isArray(value)
  ? '{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+canonical(value[k])).join(',')+'}' : JSON.stringify(value);
async function fixture(){
  const userId=randomUUID(),tenantId=randomUUID(),deviceId=randomUUID(),sessionId=randomUUID(),requestId=randomUUID(),claimId=randomUUID(),opportunityId=randomUUID();
  const snapshot={schemaVersion:'outreach-context-v1',binding:{opportunityId,channel:'dm',requestId:randomUUID(),contentHash:'a'.repeat(64)},ownerUserId:userId,
    accountScope:{id:tenantId,version:1},profileVersionId:randomUUID(),draft:{opportunityId,channel:'dm',content:'需求还在吗？',savedContent:'需求还在吗？',version:1,accountId:'account-1',recipient:'buyer-1'},
    source:{sourceId:randomUUID(),evidenceVersion:randomUUID(),evidenceSha256:'b'.repeat(64),platform:'BILIBILI',kind:'POST',url:'https://www.bilibili.com/video/BV1demo/',excerpt:'synthetic demand'},
    target:{action:'DIRECT_MESSAGE',authorPublicId:'buyer-1',postId:'BV1demo',commentId:null},connection:{deviceId,connectionId:randomUUID(),connectionVersion:1,accountPublicId:'account-1',platform:'BILIBILI'},
    channelCapability:{status:'UNVERIFIED',reason:'CHANNEL_CHECK_REQUIRED'},authorization:'NOT_GRANTED'};
  const contextSha256=createHash('sha256').update(canonical(snapshot)).digest('hex'),context={...snapshot,contextSha256};
  const binding={tenantId,requestId,claimId,contextSha256};const pair=generateKeyPairSync('ed25519');
  let claimed=false,consumed=false,current=true,state='UNKNOWN',failResult=false,changeOnClaim=false;const calls:string[]=[];
  const deadline=new Date(Date.now()+25_000).toISOString();
  const payload=(request:unknown)=>canonical({protocol:'yike-outreach-dispatch-v1',tenant_id:tenantId,user_id:userId,session_digest:'d'.repeat(64),request});
  const receipt=()=>({requestId,claimId,state,deliveryConfirmed:state==='SENT',dispatchAllowed:false,dispatchBefore:deadline,...(state==='SENT'?{evidenceAuthority:'DEVICE_ATTESTED_PLATFORM_RECEIPT'}:{})});
  const server=createServer(async(req,res)=>{
    let text='';for await(const chunk of req)text+=chunk;const body=text?JSON.parse(text):null;
    res.setHeader('content-type','application/json');calls.push(req.method+' '+req.url);
    if(req.method==='GET'){res.end(JSON.stringify(receipt()));return;}
    if(req.url?.endsWith('/signing-payload')){res.end(JSON.stringify({signing_payload:payload(body.request)}));return;}
    if(!verify(null,Buffer.from(payload(body.request)),pair.publicKey,Buffer.from(body.signature,'base64url'))){res.statusCode=403;res.end('{}');return;}
    if(body.request.action==='CLAIM'){
      if(changeOnClaim)current=false;
      const data=claimed?receipt():{...receipt(),dispatchAllowed:true,context};claimed=true;res.end(JSON.stringify(data));return;
    }
    if(failResult){res.statusCode=503;res.end('{}');return;}
    state=body.request.outcome.status;res.end(JSON.stringify({...receipt(),resultId:body.request.resultId}));
  });
  await new Promise<void>(resolve=>server.listen(0,'127.0.0.1',resolve));const address=server.address();if(!address || typeof address==='string')throw new Error();
  const serviceOrigin='http://127.0.0.1:'+address.port;
  const service=createServiceClient({baseUrl:serviceOrigin,fetch,clearSession:async()=>{}});
  const key={scope:{serviceOrigin,userId,deviceId},publicKey:pair.publicKey.export({format:'jwk'}).x!,privateKey:pair.privateKey.export({format:'pem',type:'pkcs8'}).toString()};
  const close=vi.fn();const channel={check:vi.fn(async()=>({status:'AVAILABLE',contextSha256,deviceId,connectionId:context.connection.connectionId,connectionVersion:1,accountPublicId:'account-1',recipientId:'buyer-1',checkedAt:new Date().toISOString()})),
    execute:vi.fn(async()=>({status:'SENT',confirmed:true,proof:{kind:'ACCEPTED',externalId:'fixture-receipt',sha256:'c'.repeat(64),observedAt:new Date().toISOString()}}))};
  const controller=createOutreachDispatchSession({serviceOrigin,identity:{openWorkerScope:async()=>({ok:true as const,scope:{session:{userId,sessionId,isCurrent:()=>current},device:{deviceId,credentialVersion:1},transport:{requestOutreach:service.requestOutreach},close}})},
    vault:{read:async()=>key},journal:{consumed:async()=>consumed,consume:async()=>{if(consumed)return{created:false};consumed=true;return{created:true};}},channel});
  return {controller,binding,channel,calls,service,close,setFailResult:()=>{failResult=true;},changeOnClaim:()=>{changeOnClaim=true;},
    dispose:()=>new Promise<void>((resolve,reject)=>{server.close(error=>error?reject(error):resolve());server.closeAllConnections();})};
}
describe('private outreach session over real HTTP with synthetic platform/server fixtures',()=>{
  it('claims, consumes once, signs a result and only then reports server recording',async()=>{
    const f=await fixture();try {
      expect(await f.controller.dispatch(f.binding,new AbortController().signal)).toMatchObject({state:'RESULT_RECORDED',receipt:{state:'SENT',dispatchAllowed:false}});
      expect(f.calls).toHaveLength(4);expect(f.channel.execute).toHaveBeenCalledTimes(1);
      expect(await f.controller.dispatch(f.binding,new AbortController().signal)).toMatchObject({state:'UNKNOWN'});
      expect(f.channel.execute).toHaveBeenCalledTimes(1);
      expect(await f.controller.reconcile(f.binding,new AbortController().signal)).toMatchObject({state:'RECONCILED',receipt:{state:'SENT'}});
      expect(f.calls.at(-1)).toBe('GET /api/ui/outreach/queue/'+f.binding.requestId);
      expect(await f.service.request({operation:'outreach.dispatch.receipt',payload:{requestId:f.binding.requestId}})).toMatchObject({ok:false});
    } finally {await f.dispose();}
  });
  it('keeps a native fact pending when RESULT cannot be recorded; never sends again',async()=>{
    const f=await fixture();try {f.setFailResult();
      expect(await f.controller.dispatch(f.binding,new AbortController().signal)).toMatchObject({state:'RESULT_PENDING',outcome:{status:'SENT'}});
      expect(f.calls).toHaveLength(4);
      expect(await f.controller.reconcile(f.binding,new AbortController().signal)).toMatchObject({state:'RECONCILED',receipt:{state:'UNKNOWN'}});
      expect(f.channel.execute).toHaveBeenCalledTimes(1);
    } finally {await f.dispose();}
  });
  it('a session change while CLAIM is in flight prevents any native action',async()=>{
    const f=await fixture();try {f.changeOnClaim();
      expect(await f.controller.dispatch(f.binding,new AbortController().signal)).toMatchObject({state:'UNKNOWN'});
      expect(f.calls).toHaveLength(2);expect(f.channel.execute).not.toHaveBeenCalled();expect(f.close).toHaveBeenCalled();
    } finally {await f.dispose();}
  });
  it('a late native receipt survives session loss as pending, without another HTTP write',async()=>{
    const f=await fixture();try {
      const abort=new AbortController();
      f.channel.execute.mockImplementationOnce(async()=>{abort.abort();return{status:'SENT',confirmed:true,proof:{kind:'ACCEPTED',externalId:'fixture-late',sha256:'c'.repeat(64),observedAt:new Date().toISOString()}};});
      expect(await f.controller.dispatch(f.binding,abort.signal)).toMatchObject({state:'RESULT_PENDING',outcome:{status:'SENT'}});
      expect(f.calls).toHaveLength(2);expect(f.channel.execute).toHaveBeenCalledTimes(1);
    } finally {await f.dispose();}
  });
});
