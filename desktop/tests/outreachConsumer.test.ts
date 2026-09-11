import {describe,it,expect,vi} from 'vitest';
import {createHash,randomUUID,randomBytes,createCipheriv,createDecipheriv} from 'node:crypto';
import {mkdtemp,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createOutreachConsumer} from '../src/main/outreachConsumer';
import {createOutreachConsumptionJournal} from '../src/main/outreachConsumptionJournal';

function canonical(value:unknown):string {
  if(Array.isArray(value))return '['+value.map(canonical).join(',')+']';
  if(value && typeof value==='object' && !Array.isArray(value)) return '{'+Object.entries(value).sort(([a],[b])=>a<b?-1:a>b?1:0).map(([k,v])=>JSON.stringify(k)+':'+canonical(v)).join(',')+'}';
  return JSON.stringify(value);
}
function fixture(){
  let now=Date.now();const requestId=randomUUID(),claimId=randomUUID(),deviceId=randomUUID(),tenantId=randomUUID(),userId=randomUUID(),opportunityId=randomUUID();
  const context={schemaVersion:'outreach-context-v1',binding:{opportunityId,channel:'dm',requestId:randomUUID(),contentHash:'a'.repeat(64)},
    ownerUserId:userId,accountScope:{id:tenantId,version:1},profileVersionId:randomUUID(),
    draft:{opportunityId,channel:'dm',content:'知识库项目还在找团队吗？',savedContent:'知识库项目还在找团队吗？',version:2,accountId:'our-account',recipient:'buyer-author'},
    source:{sourceId:randomUUID(),evidenceVersion:randomUUID(),evidenceSha256:'b'.repeat(64),platform:'BILIBILI',kind:'COMMENT',url:'https://www.bilibili.com/video/BV1public/',excerpt:'synthetic buyer demand'},
    target:{action:'DIRECT_MESSAGE',authorPublicId:'buyer-author',postId:'BV1public',commentId:'comment-1'},
    connection:{deviceId,connectionId:randomUUID(),connectionVersion:3,accountPublicId:'our-account',platform:'BILIBILI'},
    channelCapability:{status:'UNVERIFIED',reason:'CHANNEL_CHECK_REQUIRED'},authorization:'NOT_GRANTED'};
  const contextSha256=createHash('sha256').update(canonical(context)).digest('hex');
  const expected={serviceOrigin:'https://service.example',userId,tenantId,deviceId,sessionId:'session-current',requestId,claimId,contextSha256};
  const grant={requestId,claimId,state:'UNKNOWN',deliveryConfirmed:false,dispatchAllowed:true,dispatchBefore:new Date(now+20_000).toISOString(),context:{...context,contextSha256}};
  let used=false;
  const journal={consumed:vi.fn(async()=>used),consume:vi.fn(async()=>{if(used)return {created:false};used=true;return {created:true};})};
  const observation=()=>({status:'AVAILABLE',contextSha256,deviceId,connectionId:context.connection.connectionId,
    connectionVersion:3,accountPublicId:'our-account',recipientId:'buyer-author',checkedAt:new Date(now).toISOString()});
  const channel={check:vi.fn(async()=>observation()),execute:vi.fn(async()=>({status:'SENT',confirmed:true,
    proof:{kind:'ACCEPTED',externalId:'synthetic-receipt',sha256:'c'.repeat(64),observedAt:new Date(now).toISOString()}}))};
  const current=vi.fn(()=>true);const controller=createOutreachConsumer({journal,channel,isCurrent:current,now:()=>now});
  return {grant,expected,journal,channel,current,controller,observation,advance:(ms:number)=>{now+=ms;}};
}

describe('native outreach consumer (synthetic platform driver)',()=>{
  it.each(['missing','rejected','valid'] as const)('material references require final qualification: %s',async(mode)=>{
    const f=fixture(),{contextSha256:_old,...c}=f.grant.context;
    const context={...c,draft:{...c.draft,materialReferences:[{sourceProfileVersionId:c.profileVersionId,materialId:'m',materialVersion:4,extractionId:'e',quote:c.draft.content}]}};
    const contextSha256=createHash('sha256').update(canonical(context)).digest('hex');
    const expected={...f.expected,contextSha256},grant={...f.grant,context:{...context,contextSha256}};
    f.channel.check.mockImplementation(async()=>({...f.observation(),contextSha256}));
    const qualify=vi.fn(async()=>{expect(f.channel.check).toHaveBeenCalledOnce();expect(f.journal.consume).not.toHaveBeenCalled();
      if(mode==='rejected')throw new Error('revoked');return {state:'QUALIFIED',requestId:expected.requestId,claimId:expected.claimId,contextSha256,dispatchBefore:grant.dispatchBefore};});
    const consumer=createOutreachConsumer({journal:f.journal,channel:f.channel,isCurrent:f.current,...(mode==='missing'?{}:{qualify})});
    const result=await consumer.consume(expected,grant,new AbortController().signal);
    if(mode==='valid'){expect(result.state).toBe('RESULT_READY');expect(qualify).toHaveBeenCalledOnce();expect(f.channel.execute).toHaveBeenCalledOnce();}
    else {expect(result).toMatchObject({state:'UNKNOWN',reason:'MATERIAL_UNVERIFIED'});expect(f.channel.execute).not.toHaveBeenCalled();expect(f.journal.consume).not.toHaveBeenCalled();}
  });
  it('a reconstructed consumer with the real disk journal cannot repeat an uncertain action',async()=>{
    const directory=await mkdtemp(join(tmpdir(),'yike-consumer-integration-')),key=randomBytes(32);
    const protection={isEncryptionAvailable:()=>true,
      encryptString(text:string){const iv=randomBytes(12),cipher=createCipheriv('aes-256-gcm',key,iv);return Buffer.concat([iv,cipher.update(text,'utf8'),cipher.final(),cipher.getAuthTag()]);},
      decryptString(bytes:Buffer){const cipher=createDecipheriv('aes-256-gcm',key,bytes.subarray(0,12));cipher.setAuthTag(bytes.subarray(-16));return Buffer.concat([cipher.update(bytes.subarray(12,-16)),cipher.final()]).toString('utf8');}};
    try {
      const f=fixture();f.channel.execute.mockRejectedValueOnce(new Error('uncertain platform response'));
      const create=()=>createOutreachConsumer({journal:createOutreachConsumptionJournal({directory,protection}),channel:f.channel,isCurrent:f.current});
      expect(await create().consume(f.expected,f.grant,new AbortController().signal)).toMatchObject({reason:'EXECUTION_UNKNOWN'});
      expect(await create().consume({...f.expected,sessionId:'new-session'},f.grant,new AbortController().signal)).toMatchObject({reason:'ALREADY_CONSUMED'});
      expect(f.channel.execute).toHaveBeenCalledTimes(1);
    } finally {await rm(directory,{recursive:true,force:true});}
  });
  it('persists consumption before exactly one action and never reports server acceptance',async()=>{
    const f=fixture();
    f.channel.execute.mockImplementationOnce(async()=>{
      expect(f.journal.consume).toHaveBeenCalledTimes(1);
      expect(await f.journal.consumed()).toBe(true);
      return {status:'SENT',confirmed:true,proof:{kind:'ACCEPTED',externalId:'synthetic-receipt',sha256:'c'.repeat(64),observedAt:new Date().toISOString()}};
    });
    const result=await f.controller.consume(f.expected,f.grant,new AbortController().signal);
    expect(result).toMatchObject({state:'RESULT_READY',requestId:f.expected.requestId,serverAccepted:false,outcome:{status:'SENT'}});
    expect(await f.controller.consume(f.expected,f.grant,new AbortController().signal)).toMatchObject({state:'UNKNOWN',reason:'ALREADY_CONSUMED'});
    expect(f.channel.execute).toHaveBeenCalledTimes(1);
  });
  it('two simultaneous grants cannot both call the driver',async()=>{
    const f=fixture();await Promise.all([1,2].map(()=>f.controller.consume(f.expected,f.grant,new AbortController().signal)));
    expect(f.channel.execute).toHaveBeenCalledTimes(1);
  });
  it('rejects receipt IDs that the signed RESULT API cannot accept',async()=>{
    const f=fixture();
    f.channel.execute.mockResolvedValueOnce({status:'SENT',confirmed:true,proof:{kind:'ACCEPTED',externalId:'平台回执1',sha256:'c'.repeat(64),observedAt:new Date().toISOString()}});
    expect(await f.controller.consume(f.expected,f.grant,new AbortController().signal)).toMatchObject({state:'UNKNOWN',reason:'RESULT_INVALID'});
  });
  it.each(['permission','expired','context','scope','target','url'] as const)('rejects changed %s before action',async kind=>{
    const f=fixture();
    if(kind==='permission')f.grant.dispatchAllowed=false;
    if(kind==='expired')f.advance(30_000);
    if(kind==='context')f.grant.context.draft.content='changed';
    if(kind==='scope')f.expected.tenantId=randomUUID();
    if(kind==='target')f.grant.context.target.authorPublicId='someone-else';
    if(kind==='url')f.grant.context.source.url='http://127.0.0.1/private';
    expect(await f.controller.consume(f.expected,f.grant,new AbortController().signal)).toMatchObject({state:'UNKNOWN'});
    expect(f.channel.execute).not.toHaveBeenCalled();expect(f.journal.consume).not.toHaveBeenCalled();
  });
  it('refuses an account change during the local channel check',async()=>{
    const f=fixture();f.channel.check.mockResolvedValueOnce({...f.observation(),accountPublicId:'other-account'});
    expect(await f.controller.consume(f.expected,f.grant,new AbortController().signal)).toMatchObject({state:'UNKNOWN',reason:'CHANNEL_UNVERIFIED'});
    expect(f.journal.consume).not.toHaveBeenCalled();expect(f.channel.execute).not.toHaveBeenCalled();
  });
  it.each(['session','cancel','deadline'] as const)('does not act if %s changes while storage is syncing',async kind=>{
    const f=fixture(),abort=new AbortController();
    f.journal.consume.mockImplementationOnce(async()=>{if(kind==='session')f.current.mockReturnValue(false);if(kind==='cancel')abort.abort();if(kind==='deadline')f.advance(30_000);return {created:true};});
    expect(await f.controller.consume(f.expected,f.grant,abort.signal)).toMatchObject({state:'UNKNOWN'});
    expect(f.channel.execute).not.toHaveBeenCalled();
  });
  it('storage failure and thrown driver errors never become confirmed non-delivery',async()=>{
    const f=fixture();f.journal.consume.mockRejectedValueOnce(new Error('/private/secret-file'));
    expect(await f.controller.consume(f.expected,f.grant,new AbortController().signal)).toMatchObject({state:'UNKNOWN',reason:'CONSUMPTION_UNAVAILABLE'});
    expect(f.channel.execute).not.toHaveBeenCalled();
    f.channel.execute.mockRejectedValueOnce(new Error('private browser error'));
    const result=await f.controller.consume(f.expected,f.grant,new AbortController().signal);
    expect(result).toMatchObject({state:'UNKNOWN',reason:'EXECUTION_UNKNOWN'});expect(JSON.stringify(result)).not.toContain('private');
  });
});
