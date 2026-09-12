import {expect,it} from 'vitest';
import {createCipheriv,createDecipheriv,createPrivateKey,createPublicKey,randomBytes} from 'node:crypto';
import {mkdtemp,readFile,readdir,rm} from 'node:fs/promises';
import os from 'node:os';import path from 'node:path';
import {createServiceClient} from '../../src/main/serviceClient';
import {createDeviceIdentityController} from '../../src/main/deviceIdentityController';
import {createExecutionJournal} from '../../src/main/executionJournal';
import {createExecutionSession} from '../../src/main/executionSession';
import {createExecutionController} from '../../src/main/executionController';
import {executionOperationSchema} from '../../src/shared/executionOperation';
import {researchRuntimeCapabilitySchema,researchRuntimeStatusSchema} from '../../src/shared/researchRuntime';
import {taskFeedDetailSchema} from '../../src/shared/taskFeed';
import {desktopExecutionCommandSchema} from '../../src/shared/desktopExecution';
import type {ApiResult} from '../../src/shared/contracts';

const names=['BASE','USER','TOKEN','SEED','START','QUOTE','BINDING'] as const;
it.skipIf(!names.some(name=>process.env[`YIKE_RESEARCH_LIVE_${name}`]))('runs one signed native research task across HTTP and restricted PostgreSQL',async()=>{
  const env=Object.fromEntries(names.map(name=>[name,process.env[`YIKE_RESEARCH_LIVE_${name}`]]));
  expect(Object.values(env).every(Boolean)).toBe(true);expect(Object.keys(process.env).filter(name=>/DATABASE|^POSTGRES_/i.test(name))).toEqual([]);
  const base=env.BASE!,start=executionOperationSchema.parse(JSON.parse(env.START!));expect(new URL(base).hostname).toBe('127.0.0.1');
  const privateKey=createPrivateKey({format:'der',type:'pkcs8',key:Buffer.concat([Buffer.from('302e020100300506032b657004220420','hex'),Buffer.from(env.SEED!,'hex')])});
  const key={scope:{serviceOrigin:base,userId:env.USER!,deviceId:start.device_id},privateKey:privateKey.export({format:'pem',type:'pkcs8'}).toString(),publicKey:createPublicKey(privateKey).export({format:'jwk'}).x!};
  const directory=await mkdtemp(path.join(os.tmpdir(),'yike-research-live-')),protectionKey=randomBytes(32);
  const protection={isEncryptionAvailable:()=>true,encryptString(value:string){const iv=randomBytes(12),cipher=createCipheriv('aes-256-gcm',protectionKey,iv);return Buffer.concat([iv,cipher.update(value),cipher.final(),cipher.getAuthTag()]);},
    decryptString(bytes:Buffer){const cipher=createDecipheriv('aes-256-gcm',protectionKey,bytes.subarray(0,12));cipher.setAuthTag(bytes.subarray(-16));return Buffer.concat([cipher.update(bytes.subarray(12,-16)),cipher.final()]).toString();}};
  let cookie='',startPosts=0;const client=createServiceClient({baseUrl:base,clearSession:async()=>{cookie='';},fetch:async(url,init)=>{const headers=new Headers(init.headers);if(cookie)headers.set('Cookie',cookie);
    const response=await fetch(url,{...init,headers});const session=response.headers.getSetCookie().find(value=>value.startsWith('pilot_session='));if(session)cookie=session.split(';',1)[0];
    if(init.method==='POST'&&url.endsWith('/research-execution/start'))startPosts++;return response;}});
  const identity=createDeviceIdentityController({service:client,identityFactory:()=>({prepare:async()=>({state:'READY' as const,deviceId:start.device_id,credentialVersion:1})})});
  const coordinator=()=>createExecutionSession({serviceOrigin:base,transport:identity,journal:createExecutionJournal({directory,protection}),vault:{read:async()=>key}});
  const data=(result:ApiResult):any=>{expect(result.ok).toBe(true);if(!result.ok)throw new Error(result.error);return result.data;};
  try{
    data(await identity.requestApi({operation:'session.login',payload:{token:env.TOKEN}}));expect(await identity.prepare()).toMatchObject({state:'READY'});
    const dynamic=process.env.YIKE_RESEARCH_LIVE_TEST_MODE==='dynamic';
    if(dynamic){
      const capability=researchRuntimeCapabilitySchema.parse(data(await identity.requestApi({operation:'researchRuntime.capability',payload:{dynamicResearchVersion:1}})));
      expect(capability.contractVersion).toBe(4);
    }
    const quote=data(await identity.requestApi({operation:'researchUsage.quote',payload:JSON.parse(env.QUOTE!)}));
    const reservation={quote_id:quote.quoteId,strategy_version_id:start.strategy_version_id,profile_version_id:start.profile_version_id,configuration_sha256:start.configuration_sha256,
      rule_version:quote.ruleVersion,rule_sha256:quote.ruleSha256,estimated_soubei:quote.estimatedSoubei,max_soubei:quote.maxSoubei,limits:JSON.parse(env.BINDING!).limits};
    let execution=coordinator(),controller=createExecutionController({identity,execution});
    const command=desktopExecutionCommandSchema.parse({action:'RESEARCH_START',requestId:start.request_id,profileVersionId:start.profile_version_id,strategyVersionId:start.strategy_version_id,
      configurationSha256:start.configuration_sha256,targets:start.targets,reservation,authorizationToken:quote.authorizationToken,humanConfirmed:true});
    const begun=await controller.execute(command);
    expect(begun.state).toBe('RESEARCH_RECORDED');if(begun.state!=='RESEARCH_RECORDED')throw new Error('research start failed');expect(startPosts).toBe(1);
    const taskId=begun.receipt.execution.task_id,runId=begun.receipt.execution.run_id;
    const files=await readdir(directory);expect(files.length).toBe(1);expect((await readFile(path.join(directory,files[0]))).includes(Buffer.from(quote.authorizationToken))).toBe(false);
    execution=coordinator();controller=createExecutionController({identity,execution});expect((await controller.execute({action:'RESEARCH_RECOVER',requestId:start.request_id})).state).toBe('RESEARCH_RECORDED');expect(startPosts).toBe(1);
    let status=researchRuntimeStatusSchema.parse(data(await identity.requestApi({operation:'researchRuntime.advance',payload:{taskId,runId}})));
    if(dynamic){
      for(let poll=0;status.phase==='RUNNING'&&poll<100;poll++){
        await new Promise(resolve=>setTimeout(resolve,50));
        status=researchRuntimeStatusSchema.parse(data(await identity.requestApi({operation:'researchRuntime.status',payload:{taskId}})));
      }
      expect(status).toMatchObject({contractVersion:4,phase:'COMPLETED',acceptedOriginals:1,analyzedOriginals:1,
        discovery:{searches:{succeeded:1},reads:{succeeded:1},unpublishedOriginals:0}});
      expect(status.candidateIds).toHaveLength(1);
      expect(researchRuntimeStatusSchema.parse(data(await identity.requestApi({operation:'researchRuntime.advance',payload:{taskId,runId}})))).toMatchObject({phase:'COMPLETED',candidateIds:status.candidateIds});
    }else{
      expect(status.acceptedOriginals).toBe(1);
      status=researchRuntimeStatusSchema.parse(data(await identity.requestApi({operation:'researchRuntime.advance',payload:{taskId,runId}})));expect(status.phase).toBe('COMPLETED');
      expect(researchRuntimeStatusSchema.parse(data(await identity.requestApi({operation:'researchRuntime.status',payload:{taskId}})))).toEqual(status);
    }
    const feed=taskFeedDetailSchema.parse(data(await identity.requestApi({operation:'taskFeed.get',payload:{taskId}})));expect(feed.item).toMatchObject({research:true,status:'SUCCEEDED'});
  }finally{if(path.dirname(directory)!==path.resolve(os.tmpdir())||!path.basename(directory).startsWith('yike-research-live-'))throw new Error('invalid cleanup');await rm(directory,{recursive:true,force:true});}
},30_000);
