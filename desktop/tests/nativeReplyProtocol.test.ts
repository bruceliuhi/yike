import {generateKeyPairSync,randomUUID,verify} from 'node:crypto';
import {expect,it,vi} from 'vitest';
import {parseNativeReplyBatch,validatedNativeReplyOperation} from '../src/main/nativeReplyProtocol';
import {signNativeReply} from '../src/main/nativeReplySigner';
import {canonicalJson} from '../src/main/outreachDispatchSigner';
import {createServiceClient} from '../src/main/serviceClient';

function fixture():any {
 const userId=randomUUID(),tenantId=randomUUID(),deviceId=randomUUID(),now=new Date().toISOString();
 const request={deviceId,credentialVersion:1,claimId:randomUUID(),contextSha256:'a'.repeat(64),event:{
  schema_version:'reply-event-v1',kind:'PLATFORM_REPLY',event_id:randomUUID(),tenant_id:tenantId,user_id:userId,
  opportunity_id:randomUUID(),source_id:randomUUID(),profile_version_id:randomUUID(),outreach_request_id:randomUUID(),
  state:'ACTIVE',observed_at:now,corrects_event_id:null,reason:null,platform:'XIAOHONGSHU',channel:'comment',
  external_reply_id:'b'.repeat(24),sender_public_id:'c'.repeat(24),body:'想了解具体方案',received_at:now,read_state:'UNKNOWN',read_at:null}};
 const pair=generateKeyPairSync('ed25519'),serviceOrigin='https://pilot.example';
 return {key:{scope:{serviceOrigin,userId,deviceId},privateKey:pair.privateKey.export({format:'pem',type:'pkcs8'}).toString(),publicKey:pair.publicKey.export({format:'jwk'}).x},
  prepared:{signing_payload:canonicalJson({protocol:'yike-platform-reply-v1',user_id:userId,tenant_id:tenantId,session_digest:'d'.repeat(64),request})},
  expected:{serviceOrigin,userId,tenantId,request},pair};
}
it('signs only the matching canonical reply domain and event with the scoped Ed25519 key',()=>{
 const f=fixture(),signed=signNativeReply({key:f.key,prepared:f.prepared,expected:f.expected});
 expect(signed.request).toEqual(f.expected.request);
 expect(verify(null,Buffer.from(f.prepared.signing_payload),f.pair.publicKey,Buffer.from(signed.signature,'base64url'))).toBe(true);
});
it.each(['domain','request','tenant','event-owner','canonical','key'])('rejects mismatched %s without exposing content',change=>{
 const f=fixture(),raw=JSON.parse(f.prepared.signing_payload);
 if(change==='domain')raw.protocol='yike-outreach-dispatch-v1';
 if(change==='request')raw.request.event.body='another body';
 if(change==='tenant')raw.tenant_id=randomUUID();
 if(change==='event-owner'){raw.request.event.user_id=randomUUID();f.expected.request=raw.request;}
 if(change==='key')f.key.scope.deviceId=randomUUID();
 f.prepared.signing_payload=change==='canonical'?JSON.stringify(raw,null,2):canonicalJson(raw);
 expect(()=>signNativeReply({key:f.key,prepared:f.prepared,expected:f.expected})).toThrow('REPLY_SIGNING_FAILED');
});
it('private service performs fixed reads while public API rejects the operation',async()=>{
 const payload={requestId:randomUUID(),deviceId:randomUUID(),credentialVersion:1};
 expect(validatedNativeReplyOperation({operation:'replies.source',payload:{...payload,tenantId:randomUUID()}})).toBeNull();
 const fetch=vi.fn(async(_url:string,_options:RequestInit)=>new Response('{}',{headers:{'content-type':'application/json'}}));
 const client=createServiceClient({baseUrl:'https://pilot.example',fetch,clearSession:async()=>{}});
 expect((await client.request({operation:'replies.source',payload})).ok).toBe(false);
 expect((await client.requestOutreach({operation:'replies.source',payload})).ok).toBe(true);
 expect(fetch.mock.calls[0][0]).toBe('https://pilot.example/api/ui/replies/sync-context');
 expect(JSON.parse((fetch.mock.calls[0] as any)[1].body)).toEqual(payload);
});
it('rejects other authors, duplicate IDs, future/old events and unknown completion',()=>{
 const now=new Date().toISOString(),author='a'.repeat(24),claimed=new Date(Date.now()-60000).toISOString();
 const item={externalReplyId:'b'.repeat(24),senderPublicId:author,body:'请发方案',receivedAt:now,observedAt:now,readState:'UNKNOWN'};
 expect(parseNativeReplyBatch({status:'PARTIAL',items:[item]},author,claimed).status).toBe('PARTIAL');
 for(const value of [{status:'UNKNOWN',items:[]},{status:'COMPLETE',items:[item,item]},
   {status:'COMPLETE',items:[{...item,senderPublicId:'c'.repeat(24)}]},
   {status:'COMPLETE',items:[{...item,receivedAt:'2020-01-01T00:00:00Z'}]},
   {status:'COMPLETE',items:[{...item,observedAt:'2099-01-01T00:00:00Z'}]}])
  expect(()=>parseNativeReplyBatch(value,author,claimed)).toThrow();
});
