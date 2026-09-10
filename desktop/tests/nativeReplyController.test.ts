import {expect,it,vi} from 'vitest';
import {createHash,generateKeyPairSync,randomUUID,verify} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {createNativeReplyController} from '../src/main/nativeReplyController';
import {canonicalJson} from '../src/main/outreachDispatchSigner';
const hash=(x:unknown)=>createHash('sha256').update(canonicalJson(x)).digest('hex');
function fixture(){
 const userId=randomUUID(),tenantId=randomUUID(),deviceId=randomUUID(),connectionId=randomUUID(),profileId=randomUUID();
 const opportunityId=randomUUID(),requestId=randomUUID(),claimId=randomUUID(),sessionId=randomUUID();
 const account='a'.repeat(24),buyer='b'.repeat(24),root='c'.repeat(24),now=new Date().toISOString(),serviceOrigin='https://pilot.example';
 const draft={opportunityId,channel:'comment',content:'请问还需要方案吗',savedContent:'请问还需要方案吗',version:1,accountId:account,recipient:buyer};
 const plain={schemaVersion:'outreach-context-v1',ownerUserId:userId,accountScope:{id:tenantId,version:1},profileVersionId:randomUUID(),
 binding:{opportunityId,channel:'comment',requestId:randomUUID(),contentHash:'a'.repeat(64)},draft,
 source:{sourceId:randomUUID(),evidenceVersion:randomUUID(),evidenceSha256:'b'.repeat(64),platform:'XIAOHONGSHU',kind:'POST',url:'https://www.xiaohongshu.com/explore/'+'d'.repeat(24),excerpt:'需要方案'},
 target:{action:'POST_COMMENT',authorPublicId:buyer,postId:'d'.repeat(24),commentId:null},
 connection:{deviceId,connectionId,connectionVersion:2,accountPublicId:account,platform:'XIAOHONGSHU'},
 channelCapability:{status:'UNVERIFIED',reason:'CHANNEL_CHECK_REQUIRED'},authorization:'NOT_GRANTED'};
 const context={...plain,contextSha256:hash(plain)};
 const source={schemaVersion:'reply-sync-context-v1',context,claimId,claimedAt:new Date(Date.now()-60000).toISOString(),rootCommentId:root,deviceId,credentialVersion:1};
 const registration={request_id:randomUUID(),action:'REGISTER',device_id:deviceId,connection_id:null,expected_connection_version:0,platform:'XIAOHONGSHU',account_public_id:account,session_ref:`vault://platform/${profileId}`};
 const verification={...registration,action:'VERIFY',request_id:randomUUID(),connection_id:connectionId,expected_connection_version:1};
 const record:any={version:1,scope:{serviceOrigin,userId,deviceId,platform:'XIAOHONGSHU'},flowId:randomUUID(),profileId,state:'RESOLVED',registration,verification};
 const row={connection_id:connectionId,device_id:deviceId,platform:'XIAOHONGSHU',account_public_id:account,status:'CONNECTED',connection_version:2,connected_at:now,disconnected_at:null};
 const pair=generateKeyPairSync('ed25519'),key={scope:{serviceOrigin,userId,deviceId},publicKey:pair.publicKey.export({format:'jwk'}).x!,privateKey:pair.privateKey.export({format:'pem',type:'pkcs8'}).toString()};
 const calls:any[]=[],events:any[]=[],abort=new AbortController();let current=true,clean=true,dedup=false,failAt=0;
 const batch:any={status:'PARTIAL',items:[{externalReplyId:'e'.repeat(24),senderPublicId:buyer,body:'请发方案',receivedAt:now,observedAt:now,readState:'UNKNOWN'}]};
 const driver={check:vi.fn(async()=>({status:'AVAILABLE',contextSha256:context.contextSha256,deviceId,connectionId,connectionVersion:2,accountPublicId:account,recipientId:buyer,checkedAt:now})),readReplies:vi.fn(async()=>batch),execute:vi.fn(),stop:vi.fn(async()=>{}),cleanupConfirmed:()=>clean};
 const requestOutreach=vi.fn(async(input:any)=>{
  calls.push(input);const {operation,payload}=input;
  if(operation==='replies.source')return {ok:true,status:200,data:source};
  const request=payload.request,wire=canonicalJson({protocol:'yike-platform-reply-v1',tenant_id:tenantId,user_id:userId,session_digest:'f'.repeat(64),request});
  if(operation==='replies.prepare')return {ok:true,status:200,data:{signing_payload:wire}};
  expect(driver.stop).toHaveBeenCalled();expect(clean).toBe(true);
  expect(verify(null,Buffer.from(wire),pair.publicKey,Buffer.from(payload.signature,'base64url'))).toBe(true);
  if(failAt&&events.length+1===failAt)return {ok:false,status:503,error:'unavailable'};
  const event=dedup?{...request.event,event_id:randomUUID()}:request.event;events.push(event);
  return {ok:true,status:200,data:{event,revision:1,verification:{authority:'DEVICE_ATTESTED_PLATFORM_REPLY',schemaVersion:'device-reply-attestation-v1',deviceId,credentialVersion:1,claimId,contextSha256:context.contextSha256,requestSha256:hash({...request,event}),replyEventSha256:hash(event),verifiedAt:now}}};
 });
 const scope:any={session:{userId,sessionId,isCurrent:()=>current},device:{deviceId,credentialVersion:1},signal:abort.signal,close:vi.fn(),transport:{requestOutreach,requestConnection:async(input:any)=>({ok:true,status:200,data:input.operation==='connections.current'?{items:[row]}:{request_id:verification.request_id,device_id:deviceId,action:'VERIFY',state:'SUCCEEDED',connection_id:connectionId,connection_version:2,connection_status:'CONNECTED',error_code:null}})}};
 const identity={getStatus:()=>({state:'READY' as const,deviceId,credentialVersion:1}),openWorkerScope:async()=>({ok:true as const,scope})};
 const factory=vi.fn(()=>driver);
 const controller=createNativeReplyController({serviceOrigin,identity,store:{read:async()=>record},vault:{read:async()=>key},driver:factory});
 const command={action:'SYNC',opportunityId,requestId};
 return {controller,command,driver,factory,calls,events,source,row,record,batch,scope,context,requestOutreach,
  unclean:()=>{clean=false;},dedup:()=>{dedup=true;},failAt:(n:number)=>{failAt=n;},logout:()=>{current=false;abort.abort();}};
}
it('reads exact original root then stops, signs original request and records partial coverage',async()=>{
 const f=fixture();try{
 expect(await f.controller.execute(f.command)).toEqual({state:'SYNCED',requestId:f.command.requestId,coverage:'PARTIAL',observed:1,recorded:1});
 expect(f.driver.readReplies).toHaveBeenCalledWith(f.context,{rootCommentId:f.source.rootCommentId,claimedAt:f.source.claimedAt},expect.any(AbortSignal));
 expect(f.driver.execute).not.toHaveBeenCalled();expect(f.events[0].outreach_request_id).toBe(f.command.requestId);
 expect(f.events[0].outreach_request_id).not.toBe(f.context.binding.requestId);
 expect(f.events[0].received_at).toMatch(/(?:\.\d{6})?Z$/);expect(f.scope.close).toHaveBeenCalled();
 }finally{await f.controller.stop();}
});
it('accepts server semantic deduplication without reporting new replies',async()=>{
 const f=fixture();f.dedup();expect(await f.controller.execute(f.command)).toMatchObject({state:'SYNCED',recorded:1});await f.controller.stop();
});
it.skipIf(!process.env.YIKE_REPLY_PYTHON)('preserves real Python reply contract canonical timestamps including microseconds',async()=>{
 const f=fixture(),stamp=new Date().toISOString().replace('Z','456+00:00');
 f.batch.items[0].receivedAt=stamp;f.batch.items[0].observedAt=stamp;
 expect(await f.controller.execute(f.command)).toMatchObject({state:'SYNCED'});
 const canonical=execFileSync(process.env.YIKE_REPLY_PYTHON!,['-c',
  'import sys,json; from pilot.reply_contract import PlatformReplyEvent; print(json.dumps(PlatformReplyEvent.model_validate(json.load(sys.stdin)).model_dump(),ensure_ascii=False,sort_keys=True,separators=(",",":")))'],
  {cwd:process.cwd().endsWith('/desktop')?'..':process.cwd(),input:JSON.stringify(f.events[0]),encoding:'utf8'}).trim();
 expect(canonical).toBe(canonicalJson(f.events[0]));await f.controller.stop();
});
it.each(['owner','opportunity','digest','connection','profile'] as const)('rejects mismatched %s before any browser opens',async kind=>{
 const f=fixture();
 if(kind==='owner')f.context.ownerUserId=randomUUID();
 if(kind==='opportunity')f.command.opportunityId=randomUUID();
 if(kind==='digest')f.context.contextSha256='0'.repeat(64);
 if(kind==='connection')f.row.connection_version=3;
 if(kind==='profile')f.record.verification.session_ref='vault://platform/'+randomUUID();
 expect(await f.controller.execute(f.command)).toMatchObject({state:'FAILED',recorded:0});expect(f.factory).not.toHaveBeenCalled();await f.controller.stop();
});
it('does not upload on unconfirmed cleanup and permanently reports stop failure',async()=>{
 const f=fixture();f.unclean();expect(await f.controller.execute(f.command)).toMatchObject({state:'FAILED',error:'SOURCE_STOP_FAILED',recorded:0});
 expect(f.calls.map(c=>c.operation)).toEqual(['replies.source']);await expect(f.controller.stop()).rejects.toThrow();
});
it('preserves confirmed count on a later failed upload',async()=>{
 const f=fixture();f.batch.items.push({...f.batch.items[0],externalReplyId:'f'.repeat(24)});f.failAt(2);
 expect(await f.controller.execute(f.command)).toMatchObject({state:'FAILED',recorded:1});await f.controller.stop();
});
it('logout during reading stops without uploading and simultaneous sync is busy',async()=>{
 const f=fixture();let release!:()=>void;f.driver.readReplies.mockImplementationOnce(async()=>{await new Promise<void>(r=>release=r);return f.batch;});
 const pending=f.controller.execute(f.command);await vi.waitFor(()=>expect(f.driver.readReplies).toHaveBeenCalled());
 expect(await f.controller.execute(f.command)).toMatchObject({state:'FAILED',error:'BUSY'});
 f.logout();release();expect(await pending).toMatchObject({state:'FAILED',recorded:0});expect(f.events).toHaveLength(0);await f.controller.stop();
});
