import {createCipheriv,createDecipheriv,createHash,generateKeyPairSync,randomBytes} from 'node:crypto';
import {describe,expect,it,vi} from 'vitest';
import {createExecutionSession} from '../src/main/executionSession';
import {createExecutionJournal} from '../src/main/executionJournal';
import {createExecutionController} from '../src/main/executionController';
import {executionOperationSchema} from '../src/shared/executionOperation';
import {researchReservationBindingSchema} from '../src/shared/researchExecution';
import {mkdtemp,readFile,readdir,rm} from 'node:fs/promises';
import os from 'node:os';import path from 'node:path';

const id=(n:number)=>`10000000-0000-4000-8000-${String(n).padStart(12,'0')}`; const origin='https://test.example';
function canonical(v:any):string{return Array.isArray(v)?'['+v.map(canonical).join(',')+']':v&&typeof v==='object'?'{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+canonical(v[k])).join(',')+'}':JSON.stringify(v);}
function fixture(){
  const request=executionOperationSchema.parse({schema_version:'execution-runtime-v1',operation:'START',request_id:id(1),device_id:id(2),credential_version:1,
    profile_version_id:id(3),strategy_version_id:id(4),configuration_sha256:'a'.repeat(64),targets:[{platform:'PUBLIC_WEB',access_mode:'PUBLIC_ANONYMOUS',connection_id:null}]});
  const reservation=researchReservationBindingSchema.parse({quote_id:id(5),strategy_version_id:id(4),profile_version_id:id(3),configuration_sha256:'a'.repeat(64),
    rule_version:'test-v1',rule_sha256:'b'.repeat(64),estimated_soubei:1,max_soubei:2,limits:{sources:1,minutes:1,modelCalls:1}});
  const receipt={schema_version:'research-execution-v1',execution:{schema_version:'execution-runtime-v1',request_id:id(1),operation:'START',task_id:id(6),run_id:id(7),status:'PENDING',stop_confirmed:false,
    platform_runs:[{platform_run_id:id(8),platform:'PUBLIC_WEB',status:'PENDING'}]},reservation:{...reservation,reservation_id:id(9),status:'RESERVED'}};
  let record:any=null; const events:string[]=[]; const pair=generateKeyPairSync('ed25519');
  const key={scope:{serviceOrigin:origin,userId:'user',deviceId:id(2)},privateKey:pair.privateKey.export({format:'pem',type:'pkcs8'}).toString(),publicKey:pair.publicKey.export({format:'jwk'}).x!};
  const journal:any={persist:vi.fn(),read:vi.fn(),list:vi.fn(),persistResearch:vi.fn(async(_s:any,r:any)=>{events.push('persistResearch');const created=!record;record??=structuredClone(r);return {record:structuredClone(record),created};}),
    readResearch:vi.fn(async()=>{events.push('readResearch');return structuredClone(record)}),listResearch:vi.fn(async()=>record?[structuredClone(record)]:[])};
  const transport={requestExecution:vi.fn(async(input:any):Promise<any>=>{events.push(input.operation);if(input.operation==='execution.prepare'){const r=input.payload.request;return {ok:true,status:200,data:{request_id:r.request_id,device_id:r.device_id,credential_version:r.credential_version,request_sha256:createHash('sha256').update(canonical(r)).digest('hex'),signing_payload:canonical({protocol:'yike-execution-operation-v1',tenant_id:'tenant',user_id:'user',session_digest:'a'.repeat(64),operation:r})}};} return {ok:true,status:200,data:receipt};})};
  const session={userId:'user',sessionId:id(10),isCurrent:()=>true}; const client=createExecutionSession({serviceOrigin:origin,journal,vault:{read:async()=>key},transport});
  return {request,reservation,receipt,record:()=>record,events,transport,session,client};
}
describe('native durable research protocol',()=>{
  it('persists exact nonsecret original before prepare/sign/research POST',async()=>{const f=fixture();expect(await f.client.submitResearch(f.session,f.request,f.reservation,'abc.def')).toEqual({state:'RESEARCH_RECORDED',receipt:f.receipt});
    expect(f.events).toEqual(['persistResearch','execution.prepare','researchExecution.start']); expect(JSON.stringify(f.record())).not.toContain('abc.def');
    expect(f.transport.requestExecution.mock.calls[1][0].payload.authorization_token).toBe('abc.def');});
  it('existing submit and restart recovery only read receipt and never resubmit or need token',async()=>{const f=fixture();await f.client.submitResearch(f.session,f.request,f.reservation,'abc.def');f.events.length=0;
    expect(await f.client.submitResearch(f.session,f.request,f.reservation,'other.token')).toMatchObject({state:'RESEARCH_RECORDED'});expect(f.events).toEqual(['persistResearch','researchExecution.receipt']);f.events.length=0;
    expect(await f.client.recoverResearch(f.session,id(1))).toMatchObject({state:'RESEARCH_RECORDED'});expect(f.events).toEqual(['readResearch','researchExecution.receipt']);});
  it('404 stays UNKNOWN and list returns nonsecret exact originals',async()=>{const f=fixture();await f.client.submitResearch(f.session,f.request,f.reservation,'abc.def');f.transport.requestExecution.mockResolvedValueOnce({ok:false,status:404,error:'request_not_found'});f.events.length=0;
    expect(await f.client.recoverResearch(f.session,id(1))).toEqual({state:'UNKNOWN',requestId:id(1)});expect(f.events).toEqual(['readResearch']);
    expect(f.transport.requestExecution.mock.calls.at(-1)?.[0]).toEqual({operation:'researchExecution.receipt',payload:{request_id:id(1)}});
    expect(await f.client.listResearch(f.session)).toEqual({state:'RESEARCH_LIST',requests:[f.record()]});});
  it('writes a versioned encrypted research record that reconstructs without a token',async()=>{const root=await mkdtemp(path.join(os.tmpdir(),'yike-research-journal-'));const secret=randomBytes(32);
    const protection={isEncryptionAvailable:()=>true,encryptString:(plain:string)=>{const iv=randomBytes(12),cipher=createCipheriv('aes-256-gcm',secret,iv);return Buffer.concat([iv,cipher.update(plain),cipher.final(),cipher.getAuthTag()]);},
      decryptString:(bytes:Buffer)=>{const cipher=createDecipheriv('aes-256-gcm',secret,bytes.subarray(0,12));cipher.setAuthTag(bytes.subarray(-16));return Buffer.concat([cipher.update(bytes.subarray(12,-16)),cipher.final()]).toString();}};
    try{const directory=path.join(root,'journal'),journal=createExecutionJournal({directory,protection});const f=fixture();const record={record_version:2 as const,record_type:'RESEARCH_START' as const,request:f.request,reservation:f.reservation};
      await expect(journal.persistResearch!({serviceOrigin:origin,userId:'user'},record)).resolves.toMatchObject({created:true});const file=path.join(directory,(await readdir(directory))[0]);
      expect((await readFile(file)).includes(Buffer.from('abc.def'))).toBe(false);expect(JSON.parse(protection.decryptString(await readFile(file)))).toEqual({version:2,scope:{serviceOrigin:origin,userId:'user'},record});
      await expect(createExecutionJournal({directory,protection}).readResearch!({serviceOrigin:origin,userId:'user'},id(1))).resolves.toEqual(record);
    }finally{await rm(root,{recursive:true,force:true});}});
  it('main constructs device identity and keeps renderer identity out of native research START',async()=>{const f=fixture();let submitted:any;
    const controller=createExecutionController({identity:{getStatus:()=>({state:'READY',deviceId:id(2),credentialVersion:1}),withAuthenticatedSession:async action=>({ok:true as const,value:await action(f.session)})},
      execution:{submit:async()=>({state:'UNKNOWN',requestId:id(1)}),recover:async()=>({state:'UNKNOWN',requestId:id(1)}),list:async()=>({state:'LIST',requests:[]}),
        submitResearch:async(_s,request,binding,token)=>{submitted={request,binding,token};return {state:'UNKNOWN',requestId:id(1)};}}});
    expect(await controller.execute({action:'RESEARCH_START',requestId:id(1),profileVersionId:id(3),strategyVersionId:id(4),configurationSha256:'a'.repeat(64),targets:f.request.targets!,
      reservation:f.reservation,authorizationToken:'abc.def',humanConfirmed:true})).toEqual({state:'UNKNOWN',requestId:id(1)});
    expect(submitted.request).toEqual(f.request);expect(submitted).not.toHaveProperty('userId');});
});
