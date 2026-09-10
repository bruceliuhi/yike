import {describe,it,expect,vi} from 'vitest';
import {createHash,generateKeyPairSync,randomUUID,verify} from 'node:crypto';
import {createNativeOutreachController} from '../src/main/nativeOutreachController';
import {createServiceClient} from '../src/main/serviceClient';
import {execFileSync} from 'node:child_process';
import {signOutreachConfirmation} from '../src/main/outreachConfirmationSigner';

const canonical=(v:any):string=>v && typeof v==='object' && !Array.isArray(v)?'{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+canonical(v[k])).join(',')+'}':JSON.stringify(v);
const hash=(v:unknown)=>createHash('sha256').update(canonical(v)).digest('hex');
function fixture(){
  const userId=randomUUID(),tenantId=randomUUID(),deviceId=randomUUID(),connectionId=randomUUID(),profileId=randomUUID(),opportunityId=randomUUID(),sessionId=randomUUID();
  const serviceOrigin='https://service.example',draft={opportunityId,channel:'dm' as const,content:'需求还在吗？',savedContent:'需求还在吗？',version:1,accountId:'account123',recipient:'buyer123'};
  const snapshot={draft,accountScope:{id:tenantId,version:1},profileVersionId:randomUUID(),sourceEvidenceVersion:randomUUID()};
  const binding={opportunityId,channel:'dm',requestId:randomUUID(),contentHash:createHash('sha256').update(JSON.stringify([opportunityId,'dm',1,draft.content,draft.accountId,draft.recipient,snapshot.profileVersionId,snapshot.sourceEvidenceVersion,snapshot.accountScope])).digest('hex')};
  const plain={schemaVersion:'outreach-context-v1',binding,ownerUserId:userId,accountScope:snapshot.accountScope,profileVersionId:snapshot.profileVersionId,draft,
    source:{sourceId:randomUUID(),evidenceVersion:snapshot.sourceEvidenceVersion,evidenceSha256:'b'.repeat(64),platform:'XIAOHONGSHU',kind:'POST',url:'https://www.xiaohongshu.com/explore/abc123',excerpt:'synthetic demand'},
    target:{action:'DIRECT_MESSAGE',authorPublicId:'buyer123',postId:'abc123',commentId:null},
    connection:{deviceId,connectionId,connectionVersion:2,accountPublicId:draft.accountId,platform:'XIAOHONGSHU'},channelCapability:{status:'UNVERIFIED',reason:'CHANNEL_CHECK_REQUIRED'},authorization:'NOT_GRANTED'};
  const context={...plain,contextSha256:hash(plain)};
  const registration={request_id:randomUUID(),action:'REGISTER' as const,device_id:deviceId,connection_id:null,expected_connection_version:0,platform:'XIAOHONGSHU' as const,account_public_id:draft.accountId,session_ref:`vault://platform/${profileId}`};
  const verification={...registration,request_id:randomUUID(),action:'VERIFY' as const,connection_id:connectionId,expected_connection_version:1};
  const record={version:1 as const,scope:{serviceOrigin,userId,deviceId,platform:'XIAOHONGSHU' as const},flowId:randomUUID(),profileId,state:'RESOLVED' as const,registration,verification};
  const row={connection_id:connectionId,device_id:deviceId,account_public_id:draft.accountId,platform:'XIAOHONGSHU',status:'CONNECTED',connection_version:2,connected_at:new Date().toISOString(),disconnected_at:null};
  const pair=generateKeyPairSync('ed25519'),key={scope:{serviceOrigin,userId,deviceId},publicKey:pair.publicKey.export({format:'jwk'}).x!,privateKey:pair.privateKey.export({format:'pem',type:'pkcs8'}).toString()};
  let queued=false,current=true,consumed=false,now=Date.now(),badReceipt=false,corruptDigest=false,clean=true,changedDraft=false,loseApply=false;
  const calls:any[]=[],outbox=new Map<string,any>();let original:any;
  const payload=(request:any,protocol:string)=>canonical({protocol,tenant_id:tenantId,user_id:userId,session_digest:'c'.repeat(64),request});
  const service=createServiceClient({baseUrl:serviceOrigin,clearSession:async()=>{},fetch:async(url,opts)=>{
    const path=new URL(url).pathname,body=opts.body?JSON.parse(String(opts.body)):undefined;calls.push({path,body});let data:any;
    if(path.includes('/contact-drafts/'))data={binding,snapshot:changedDraft?{...snapshot,draft:{...draft,content:'changed'}}:snapshot,status:'SUCCEEDED',confirmed:true};
    else if(path==='/api/ui/outreach/context')data=context;
    else if(path==='/api/ui/outreach/signing-payload')data={signing_payload:payload(body.request,'yike-outreach-confirmation-v1'),requestId:body.request.requestId,requestSha256:corruptDigest?'f'.repeat(64):hash(body.request)};
    else if(path==='/api/ui/outreach/queue'){
      expect(verify(null,Buffer.from(payload(body.request,'yike-outreach-confirmation-v1')),pair.publicKey,Buffer.from(body.signature,'base64url'))).toBe(true);
      expect(Object.keys(body.request.context).sort()).toEqual(['binding','connectionId','connectionVersion','deviceId']);
      queued=true;original=body.request;data={requestId:badReceipt?randomUUID():original.requestId,state:'QUEUED',deliveryConfirmed:false,dispatchAllowed:false};
      if(loseApply)throw Error('synthetic lost response');
    } else if(path==='/api/ui/outreach/dispatch/signing-payload')data={signing_payload:payload(body.request,'yike-outreach-dispatch-v1')};
    else if(path==='/api/ui/outreach/dispatch'){
      expect(queued).toBe(true);expect(verify(null,Buffer.from(payload(body.request,'yike-outreach-dispatch-v1')),pair.publicKey,Buffer.from(body.signature,'base64url'))).toBe(true);
      const r=body.request;data=r.action==='CLAIM'?{requestId:r.requestId,claimId:r.claimId,state:'UNKNOWN',deliveryConfirmed:false,dispatchAllowed:true,dispatchBefore:new Date(Date.now()+25000).toISOString(),context}:
        {requestId:r.requestId,claimId:r.claimId,resultId:r.resultId,state:'SENT',deliveryConfirmed:true,dispatchAllowed:false,dispatchBefore:new Date(Date.now()+25000).toISOString(),evidenceAuthority:'DEVICE_ATTESTED_PLATFORM_RECEIPT'};
    } else if(path.endsWith('/cancel'))data={requestId:path.split('/').at(-2),state:'CANCELLED',deliveryConfirmed:false,dispatchAllowed:false};
    else data={requestId:path.split('/').at(-1),state:'UNKNOWN',deliveryConfirmed:false,dispatchAllowed:false};
    return new Response(JSON.stringify(data),{headers:{'content-type':'application/json'}});
  }});
  const connection=vi.fn(async(raw:any)=>({ok:true as const,status:200,data:raw.operation==='connections.current'?{items:[row]}:{request_id:verification.request_id,device_id:deviceId,action:'VERIFY',state:'SUCCEEDED',connection_id:connectionId,connection_version:2,connection_status:'CONNECTED',error_code:null}}));
  const identity={getStatus:()=>({state:'READY' as const,deviceId,credentialVersion:1}),openWorkerScope:async()=>{const abort=new AbortController();return {ok:true as const,scope:{session:{userId,sessionId,isCurrent:()=>current && !abort.signal.aborted},device:{deviceId,credentialVersion:1},signal:abort.signal,transport:{requestOutreach:service.requestOutreach,requestConnection:connection,requestCandidate:service.requestCandidate,requestExecution:service.requestExecution},close:()=>abort.abort()}};}};
  const run={check:vi.fn(async()=>({status:'AVAILABLE',contextSha256:context.contextSha256,deviceId,connectionId,connectionVersion:2,accountPublicId:draft.accountId,recipientId:draft.recipient,checkedAt:new Date().toISOString()})),
    execute:vi.fn(async()=>({status:'SENT',confirmed:true,proof:{kind:'ACCEPTED',externalId:'fixture-receipt',sha256:'d'.repeat(64),observedAt:new Date().toISOString()}})),stop:vi.fn(async()=>{}),cleanupConfirmed:()=>clean};
  const driver=vi.fn(()=>run);
  const controller=createNativeOutreachController({serviceOrigin,identity,store:{read:async()=>record},vault:{read:async()=>key},driver,now:()=>now,
    journal:{consumed:async()=>consumed,consume:async()=>{const created=!consumed;consumed=true;return {created};}},outbox:{read:async(_s,r)=>outbox.get(r)??null,put:async(_s,r)=>{outbox.set(r.requestId,r);return r;}}});
  const prepare=()=>controller.execute({action:'PREPARE',requestId:randomUUID(),draft});
  return {controller,prepare,driver,run,calls,context,profileId,row,record,service,connection,setBadReceipt:()=>{badReceipt=true;},setDigest:()=>{corruptDigest=true;},setLoseApply:()=>{loseApply=true;},setUnclean:()=>{clean=false;},setChanged:()=>{changedDraft=true;},expire:()=>{now+=120001;},logout:()=>{current=false;}};
}
describe('private native confirmation controller (synthetic fixtures, no external sending)',()=>{
  it('freezes original profile and public context, checks only after consent, queues then dispatches once',async()=>{
    const f=fixture();try {const p=await f.prepare();expect(p.state).toBe('PREPARED');if(p.state!=='PREPARED')throw Error();
      expect(f.driver).not.toHaveBeenCalled();expect(JSON.stringify(p)).not.toContain(f.profileId);
      const result=await f.controller.execute({action:'CONFIRM',flowId:p.flowId,humanConfirmed:true});
      expect(result).toMatchObject({state:'RESULT',binding:p.binding,result:{state:'RESULT_RECORDED',receipt:{state:'SENT'}}});
      expect(f.driver).toHaveBeenCalledWith(f.context,f.profileId);expect(f.run.execute).toHaveBeenCalledTimes(1);
      expect(await f.controller.execute({action:'CONFIRM',flowId:p.flowId,humanConfirmed:true})).toMatchObject({state:'FAILED'});
      expect(await f.service.request({operation:'outreach.confirmation.prepare',payload:{}})).toMatchObject({ok:false});
    }finally{await f.controller.stop();}
  });
  it.each(['setBadReceipt','setDigest'] as const)('never claims after an unconfirmed or altered 122 response: %s',async change=>{
    const f=fixture();try {const p=await f.prepare();if(p.state!=='PREPARED')throw Error();f[change]();
      expect(await f.controller.execute({action:'CONFIRM',flowId:p.flowId,humanConfirmed:true})).toMatchObject({state:change==='setDigest'?'NOT_SUBMITTED':'FAILED'});
      expect(f.calls.some(c=>c.path.includes('/dispatch'))).toBe(false);expect(f.run.execute).not.toHaveBeenCalled();
    }finally{await f.controller.stop();}
  });
  it.each(['expire','logout','setChanged'] as const)('rejects a changed or expired preparation: %s',async change=>{
    const f=fixture();try {const p=await f.prepare();if(p.state!=='PREPARED')throw Error();f[change]();
      expect(await f.controller.execute({action:'CONFIRM',flowId:p.flowId,humanConfirmed:true})).toMatchObject({state:'NOT_SUBMITTED',binding:p.binding});
      expect(f.run.execute).not.toHaveBeenCalled();expect(f.driver).not.toHaveBeenCalled();
    }finally{await f.controller.stop();}
  });
  it('rejects current connection/version mismatch against the original VERIFY receipt',async()=>{
    const f=fixture();try {f.row.connection_version=3;expect(await f.prepare()).toMatchObject({state:'FAILED'});expect(f.driver).not.toHaveBeenCalled();}finally{await f.controller.stop();}
  });
  it('reports an original check failure as NOT_SUBMITTED only after confirmed cleanup',async()=>{
    const f=fixture();try {const p=await f.prepare();if(p.state!=='PREPARED')throw Error();
      f.run.check.mockRejectedValueOnce(Error('synthetic channel failure'));
      expect(await f.controller.execute({action:'CONFIRM',flowId:p.flowId,humanConfirmed:true})).toMatchObject({state:'NOT_SUBMITTED',binding:p.binding});
      expect(f.run.stop).toHaveBeenCalledTimes(1);expect(f.calls.some(c=>c.path==='/api/ui/outreach/queue')).toBe(false);
      expect(await f.controller.execute({action:'CONFIRM',flowId:p.flowId,humanConfirmed:true})).toMatchObject({state:'FAILED'});
    }finally{await f.controller.stop();}
  });
  it('retains ambiguity after apply response loss even when local cleanup succeeded',async()=>{
    const f=fixture();try {const p=await f.prepare();if(p.state!=='PREPARED')throw Error();f.setLoseApply();
      expect(await f.controller.execute({action:'CONFIRM',flowId:p.flowId,humanConfirmed:true})).toMatchObject({state:'FAILED',error:'CONFIRMATION_UNCONFIRMED'});
      expect(f.run.stop).toHaveBeenCalledTimes(1);expect(f.calls.some(c=>c.path.includes('/dispatch'))).toBe(false);
    }finally{await f.controller.stop();}
  });
  it('never labels unconfirmed cleanup NOT_SUBMITTED',async()=>{
    const f=fixture();const p=await f.prepare();if(p.state!=='PREPARED')throw Error();f.setUnclean();f.run.check.mockRejectedValueOnce(Error('synthetic check failure'));
    expect(await f.controller.execute({action:'CONFIRM',flowId:p.flowId,humanConfirmed:true})).toMatchObject({state:'FAILED',error:'SOURCE_STOP_FAILED'});
    await expect(f.controller.stop()).rejects.toThrow('SOURCE_STOP_FAILED');
  });
  it('retains one original timeout proof after the timer cleans an unused flow',async()=>{
    vi.useFakeTimers();const f=fixture();try{const p=await f.prepare();if(p.state!=='PREPARED')throw Error();f.expire();
      await vi.advanceTimersByTimeAsync(100);
      expect(await f.controller.execute({action:'CONFIRM',flowId:randomUUID(),humanConfirmed:true})).toMatchObject({state:'FAILED'});
      expect(await f.controller.execute({action:'CONFIRM',flowId:p.flowId,humanConfirmed:true})).toEqual({state:'NOT_SUBMITTED',binding:p.binding,error:'FLOW_EXPIRED'});
      expect(await f.controller.execute({action:'CONFIRM',flowId:p.flowId,humanConfirmed:true})).toMatchObject({state:'FAILED'});
      expect(f.calls.some(c=>c.path==='/api/ui/outreach/queue')).toBe(false);
    }finally{await f.controller.stop();vi.useRealTimers();}
  });
  it('cancellation never queues, recovery never claims, and failed cleanup poisons new flows',async()=>{
    const f=fixture();const p=await f.prepare();if(p.state!=='PREPARED')throw Error();
    expect(await f.controller.execute({action:'CANCEL',flowId:p.flowId})).toEqual({state:'CANCELLED'});
    expect(await f.controller.execute({action:'RESUME_RESULT',binding:p.binding})).toMatchObject({state:'RESULT',result:{state:'UNKNOWN',reason:'NO_SAVED_RESULT'}});
    expect(await f.controller.execute({action:'RECONCILE',binding:p.binding})).toMatchObject({state:'RESULT',result:{state:'RECONCILED'}});
    expect(await f.controller.execute({action:'CANCEL_QUEUED',binding:p.binding})).toMatchObject({state:'RESULT',result:{state:'RECONCILED',receipt:{requestId:p.binding.requestId,state:'CANCELLED'}}});
    expect(f.calls.some(c=>c.path.includes('/dispatch'))).toBe(false);
    const p2=await f.prepare();if(p2.state!=='PREPARED')throw Error();f.setUnclean();
    expect(await f.controller.execute({action:'CONFIRM',flowId:p2.flowId,humanConfirmed:true})).toMatchObject({state:'RESULT'});
    expect(await f.prepare()).toEqual({state:'FAILED',error:'SOURCE_STOP_FAILED'});
    await expect(f.controller.stop()).rejects.toThrow('SOURCE_STOP_FAILED');
  });
  it('cancels a pending read-only check before confirmation transport and never admits another confirmation',async()=>{
    const f=fixture();try {const p=await f.prepare();if(p.state!=='PREPARED')throw Error();
      let entered!:()=>void,release!:()=>void;
      const started=new Promise<void>(r=>{entered=r;}),wait=new Promise<void>(r=>{release=r;});
      const check=f.run.check.getMockImplementation()!;
      f.run.check.mockImplementationOnce(async()=>{entered();await wait;return check();});
      const pending=f.controller.execute({action:'CONFIRM',flowId:p.flowId,humanConfirmed:true});await started;
      expect(await f.controller.execute({action:'CONFIRM',flowId:p.flowId,humanConfirmed:true})).toMatchObject({state:'FAILED',error:'BUSY'});
      expect(await f.controller.execute({action:'CANCEL',flowId:p.flowId})).toEqual({state:'CANCELLED'});release();
      expect(await pending).toMatchObject({state:'FAILED'});expect(f.calls.some(c=>c.path.endsWith('/signing-payload'))).toBe(false);
    }finally{await f.controller.stop();}
  });
  it.skipIf(!process.env.YIKE_CONFIRMATION_PYTHON)('matches actual Python Confirmation.model_dump/signing_payload and verifies Ed25519 bytes',()=>{
    const deviceId=randomUUID(),userId=randomUUID(),tenantId=randomUUID(),serviceOrigin='https://service.example',pair=generateKeyPairSync('ed25519');
    const request={requestId:randomUUID(),context:{binding:{opportunityId:randomUUID(),channel:'dm' as const,requestId:randomUUID(),contentHash:'a'.repeat(64)},deviceId,connectionId:randomUUID(),connectionVersion:2},contextSha256:'b'.repeat(64),credentialVersion:1,humanConfirmed:true as const,channelCheck:{status:'AVAILABLE' as const,observedAt:'2026-09-12T01:00:00Z'}};
    const python=process.env.YIKE_CONFIRMATION_PYTHON!;
    const script="import json,sys\nfrom types import SimpleNamespace\nfrom pilot.outreach_queue import Confirmation,signing_payload\nfrom pilot.execution_runtime import _hash\nv=json.load(sys.stdin)\nr=Confirmation.model_validate(v['request'])\nprint(json.dumps(dict(signing_payload=signing_payload(v['tenant'],SimpleNamespace(user_id=v['user'],revocation_key='c'*64),r),requestId=r.requestId,requestSha256=_hash(r.model_dump()))))";
    const prepared=JSON.parse(execFileSync(python,['-c',script],{cwd:'..',input:JSON.stringify({request,tenant:tenantId,user:userId}),encoding:'utf8'}));
    const signed=signOutreachConfirmation({key:{scope:{serviceOrigin,userId,deviceId},privateKey:pair.privateKey.export({format:'pem',type:'pkcs8'}).toString(),publicKey:pair.publicKey.export({format:'jwk'}).x!},prepared,expected:{serviceOrigin,userId,tenantId,request}});
    expect(verify(null,Buffer.from(prepared.signing_payload),pair.publicKey,Buffer.from(signed.signature,'base64url'))).toBe(true);
  });
});
