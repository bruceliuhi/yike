import {expect,it,vi} from 'vitest';
import {createPrivateKey,createPublicKey,createCipheriv,createDecipheriv,randomBytes,randomUUID} from 'node:crypto';
import {mkdtemp,rm} from 'node:fs/promises';
import {channel} from 'node:diagnostics_channel';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {isDeepStrictEqual} from 'node:util';
import {createServiceClient} from '../../src/main/serviceClient';
import {createDeviceIdentityController} from '../../src/main/deviceIdentityController';
import {createForegroundCollectionController} from '../../src/main/foregroundCollectionController';
import {createPublicCommunityDriver} from '../../src/main/publicCommunityDriver';
import {createExecutionJournal} from '../../src/main/executionJournal';
import {createExecutionSession} from '../../src/main/executionSession';
import {createCandidateJournal} from '../../src/main/candidateJournal';
import {createCandidateSession} from '../../src/main/candidateSession';
import {prepareStrategySchema,strategyReceiptSchema,strategyViewSchema} from '../../src/shared/researchStrategies';
import {candidateSubmissionSchema,type CandidateSubmission} from '../../src/shared/candidateSubmission';
import type {CandidateReceipt} from '../../src/shared/candidateReceipt';
import {publicSourceIdSchema,PUBLIC_SOURCES} from '../../src/shared/publicSources';
import {parseRawCandidateEvidence} from '../../src/shared/rawCandidateEvidence';
import {createCandidateReviewService} from '../../src/renderer/services/candidateReview';
import {ServiceError} from '../../src/renderer/services/contracts';

const names=['BASE','USER','TOKEN','SEED','DEVICE','PROFILE','PREPARE','NETWORK'] as const;
it.skipIf(!names.some(name=>process.env[`YIKE_PUBLIC_LIVE_${name}`]))('real HTTP public collection signs, uploads and finishes without recollection',async()=>{
 const env=Object.fromEntries(names.map(name=>[name,process.env[`YIKE_PUBLIC_LIVE_${name}`]]));
 expect(Object.values(env).every(Boolean)).toBe(true);
 expect(Object.keys(process.env).some(name=>/DATABASE|^POSTGRES_/i.test(name))).toBe(false);
 expect(process.versions.node.split('.')[0]).toBe('24');
 const base=env.BASE!,network=env.NETWORK==='1';expect(new URL(base).hostname==='127.0.0.1').toBe(true);
 const prepare=prepareStrategySchema.parse(JSON.parse(env.PREPARE!));
 const sourceId=publicSourceIdSchema.parse(process.env.YIKE_PUBLIC_LIVE_SOURCE??'v2ex-latest-v1');
 const project=sourceId==='v2ex-outsourcing-authors-v1';
 const assessSourceId=process.env.YIKE_PUBLIC_LIVE_ASSESS_SOURCE_ID??'';
 expect(prepare.profile_version_id===env.PROFILE&&prepare.configuration.publicSource===sourceId).toBe(true);
 const privateKey=createPrivateKey({format:'der',type:'pkcs8',key:Buffer.concat([Buffer.from('302e020100300506032b657004220420','hex'),Buffer.from(env.SEED!,'hex')])});
 const key={scope:{serviceOrigin:base,userId:env.USER!,deviceId:env.DEVICE!},privateKey:privateKey.export({format:'pem',type:'pkcs8'}).toString(),publicKey:createPublicKey(privateKey).export({format:'jwk'}).x!};
 const secret=randomBytes(32),protection={isEncryptionAvailable:()=>true,
  encryptString(value:string){const nonce=randomBytes(12),cipher=createCipheriv('aes-256-gcm',secret,nonce);const body=Buffer.concat([cipher.update(value,'utf8'),cipher.final()]);return Buffer.concat([nonce,cipher.getAuthTag(),body]);},
  decryptString(value:Buffer){const cipher=createDecipheriv('aes-256-gcm',secret,value.subarray(0,12));cipher.setAuthTag(value.subarray(12,28));return Buffer.concat([cipher.update(value.subarray(28)),cipher.final()]).toString('utf8');}};
 const directory=await mkdtemp(path.join(tmpdir(),'yike-public-live-'));
 const executionJournal=()=>createExecutionJournal({directory:path.join(directory,'execution'),protection});
 const candidateJournal=()=>createCandidateJournal({directory:path.join(directory,'candidate'),protection});
 let cookie='',sourceReads=0,replyReads=0,driverStarts=0,driverStops=0,candidateWrites=0,assessRequests=0;
 let assessmentSummary:Record<string,unknown>|undefined;
 let records:CandidateSubmission['records']=[],accepted:CandidateReceipt|undefined;
 const operations:string[]=[],controllers:ReturnType<typeof createForegroundCollectionController>[]=[];
 const diagnostics=channel('undici:request:create');
 const observe=(message:unknown)=>{const request=(message as {request?:{origin?:string;path?:string}}).request;
  const endpoint=new URL(PUBLIC_SOURCES[sourceId].endpoint);
  if(String(request?.origin)===endpoint.origin&&request?.path===endpoint.pathname+endpoint.search)sourceReads++;
  if(String(request?.origin)===endpoint.origin&&request?.path?.startsWith('/api/replies/show.json?topic_id='))replyReads++;};
 if(network)diagnostics.subscribe(observe);
 const client=createServiceClient({baseUrl:base,clearSession:async()=>{cookie='';},fetch:async(url,init)=>{
  expect(new URL(url).origin===base).toBe(true);
  const headers=new Headers(init.headers);if(cookie)headers.set('Cookie',cookie);
  const response=await fetch(url,{...init,headers});
  const session=response.headers.getSetCookie().find(value=>value.startsWith('pilot_session='));if(session)cookie=session.split(';',1)[0];
  if(init.method==='POST'&&url.endsWith('/execution-operations'))operations.push(JSON.parse(String(init.body)).request.operation);
  if(init.method==='POST'&&url.endsWith('/candidate-reviews')){expect(JSON.parse(String(init.body)).action).toBe('ASSESS');assessRequests++;expect(assessRequests).toBe(1);}
  if(init.method==='POST'&&url.endsWith('/candidate-batches')){candidateWrites++;expect(driverStops===candidateWrites).toBe(true);
   if(response.ok)accepted=await response.clone().json() as CandidateReceipt;}
  return response;
 }});
 const identity=createDeviceIdentityController({service:client,identityFactory:()=>({prepare:async()=>({state:'READY' as const,deviceId:env.DEVICE!,credentialVersion:1})})});
 const forbidden=()=>{throw new Error('native runtime must not run');};
 const fixtureCreated=Math.floor(Date.now()/1000)-60;
 const makeDriver=()=>createPublicCommunityDriver(network?{}:{fetch:async(url)=>{
  if(String(url).includes('/api/replies/show.json?')){replyReads++;return new Response(JSON.stringify([
   {id:101,topic_id:987654321,member:{id:123},created:fixtureCreated+1,content:'合成作者更新：项目已结束'},
   {id:102,topic_id:987654321,member:{id:456},created:fixtureCreated+2,content:'合成第三方回复，不应保存'},
  ]),{headers:{'content-type':'application/json'}});}
  sourceReads++;return new Response(JSON.stringify([{id:987654321,title:'AI 合成采样',content:'需要 AI 的企业服务，仅为合成验证。',created:fixtureCreated,url:'https://www.v2ex.com/t/987654321',member:{id:123},replies:2,node:{name:project?'outsourcing':'qna'}}]),{headers:{'content-type':'application/json'}});}});
 function controller(){const value=createForegroundCollectionController({serviceOrigin:base,identity,configuration:null,
  store:{read:async()=>null},executionJournal:executionJournal(),candidateJournal:candidateJournal(),probe:forbidden,resolveAccount:forbidden,driverFactory:forbidden,
  sessions:scope=>({execution:createExecutionSession({serviceOrigin:base,transport:scope.transport,journal:executionJournal(),vault:{read:async()=>key}}),
   candidates:createCandidateSession({serviceOrigin:base,transport:scope.transport,journal:candidateJournal(),vault:{read:async()=>key}})}),
  publicDriverFactory:()=>{const reader=makeDriver();return {start(input){driverStarts++;const handle=reader.start(input);return {completed:handle.completed.then(value=>{records=candidateSubmissionSchema.shape.records.parse(value);return value;}),async stop(){driverStops++;await handle.stop();}};}};}});
  controllers.push(value);return value;}
 try{
  expect((await identity.requestApi({operation:'session.login',payload:{token:env.TOKEN}})).ok).toBe(true);
  expect((await identity.prepare()).state).toBe('READY');
  const preparedResponse=await identity.requestApi({operation:'strategies.prepare',payload:prepare});expect(preparedResponse.ok).toBe(true);
  if(!preparedResponse.ok)throw new Error('strategy preparation failed');
  const prepared=strategyReceiptSchema.parse(preparedResponse.data);
  const confirmed=await identity.requestApi({operation:'strategies.confirm',payload:{schema_version:'strategy-confirmation-v1',request_id:randomUUID(),strategy_version_id:prepared.strategy_version_id,configuration_sha256:prepared.configuration_sha256,human_confirmed:true}});
  expect(confirmed.ok).toBe(true);
  const currentResponse=await identity.requestApi({operation:'strategies.get',payload:{strategy_version_id:prepared.strategy_version_id}});expect(currentResponse.ok).toBe(true);
  if(!currentResponse.ok)throw new Error('strategy read failed');
  const current=strategyViewSchema.parse(currentResponse.data);expect(current.state==='CONFIRMED'&&current.is_current&&current.profile_current).toBe(true);
  const first=controller();const capability=await first.execute({action:'CAPABILITIES'});
  expect(capability).toMatchObject({state:'AVAILABLE',bindings:[],publicBinding:{sourceId:'v2ex-latest-v1',deviceId:env.DEVICE}});
  if(sourceId==='v2ex-qna-v1')expect(capability).toMatchObject({publicBinding:{sourceIds:['v2ex-latest-v1','v2ex-qna-v1'],monitorSupported:true}});
  if(project)expect(capability).toMatchObject({publicBinding:{sourceIds:['v2ex-latest-v1','v2ex-qna-v1',sourceId],monitorSupported:true}});
  const command={action:'START',humanConfirmed:true,requestId:randomUUID(),profileVersionId:env.PROFILE!,strategyVersionId:prepared.strategy_version_id,configurationSha256:prepared.configuration_sha256,
   targets:[{platform:'PUBLIC_WEB',access_mode:'PUBLIC_ANONYMOUS',connection_id:null,connection_version:null}]} as const;
  const begun=await first.start(command);expect(begun.state).toBe('RECORDED');
  if(begun.state!=='RECORDED'||begun.receipt.operation!=='START')throw new Error('START not recorded');
  const taskId=begun.receipt.task_id;
  await vi.waitFor(async()=>{expect(await first.execute({action:'STATUS',taskId})).toMatchObject({localState:'COMPLETED',serverStatus:'SUCCEEDED',stopConfirmed:true,recordsUsed:records.length});},{timeout:30000,interval:100});
  expect(records.length>0).toBe(true);if(!network)expect(records.length).toBe(1);
  expect([sourceReads,driverStarts,driverStops,candidateWrites]).toEqual([1,1,1,1]);expect(operations).toEqual(['START','CLAIM','FINISH']);
  expect(replyReads).toBe(project?records.length:0);
  if(project)expect(records.length).toBeLessThanOrEqual(3);
  expect(accepted?.items.length===records.length).toBe(true);
  const listing=await identity.requestApi({operation:'candidates.list',payload:{taskId,page:1,pageSize:100}});expect(listing.ok).toBe(true);
  if(!listing.ok)throw new Error('candidate list failed');
  const items=(listing.data as {items:{id:string}[]}).items;
  expect(items.length===records.length).toBe(true);
  for(const item of accepted!.items){
   expect(items.some(row=>row.id===item.candidate_id)).toBe(true);
   const response=await identity.requestApi({operation:'candidates.rawEvidence',payload:{candidateId:item.candidate_id}});expect(response.ok).toBe(true);
   if(!response.ok)throw new Error('candidate evidence read failed');
   const raw=response.data as {candidate:{revision:number}};
   const data=parseRawCandidateEvidence(response.data,{candidateId:item.candidate_id,
    candidateRevision:raw.candidate.revision,sourceVersionId:item.version_id,profileId:env.PROFILE!,
    strategyVersionId:prepared.strategy_version_id,platform:'PUBLIC_WEB'});
   const record=records[item.index],content=data.candidate.current_version;
   expect(data.candidate.profile_version_id===env.PROFILE&&data.candidate.strategy_version_id===prepared.strategy_version_id).toBe(true);
   expect((['body','title','public_url','author_public_id'] as const).every(field=>content[field]===record[field])).toBe(true);
   expect(isDeepStrictEqual(content.source_context,record.source_context)).toBe(true);
   if(sourceId==='v2ex-outsourcing-authors-v1')expect(content.source_context).toBeDefined();
   if(project&&!network)expect(content.source_context).toMatchObject({replies_read:2,replies_complete:true,author_replies:[{id:'101',body:'合成作者更新：项目已结束'}]});
   expect(Date.parse(String(content.published_at))===Date.parse(record.published_at!)).toBe(true);
   expect(data.observations.items.some(o=>o.version_id===item.version_id&&o.task_id===taskId&&o.collector_version===record.collector_version&&o.normalizer_version===record.normalizer_version&&o.query===record.query)).toBe(true);
  }
  if(assessSourceId){
   const index=records.findIndex(record=>record.external_source_id===assessSourceId);
   expect(index>=0,'explicit assessment source must be present; do not substitute another topic').toBe(true);
   const selected=accepted!.items.find(item=>item.index===index)!;
   const api=createCandidateReviewService(async(operation,_path,_method,payload)=>{
    const response=await identity.requestApi({operation,payload});
    if(!response.ok)throw new ServiceError(response.error,'ordinary candidate API failed',response.status);
    return response.data;
   });
   const candidate=(await api.list({ids:[selected.candidate_id],page:1,pageSize:1})).items[0];
   const assessmentRequest={candidateId:candidate.id,candidateRevision:candidate.revision,
    sourceVersionId:candidate.sourceVersionId,profileId:candidate.profileId,profileVersion:candidate.profileVersion,
    requestId:randomUUID(),action:'ASSESS' as const};
   const result=await api.review(assessmentRequest);
   expect(result.kind).toBe('assessment');
   if(result.kind!=='assessment')throw new Error('assessment receipt required');
   expect(result.assessment.sendingAuthorized).toBe(false);
   expect(result.assessment.strategyVersionId).toBe(prepared.strategy_version_id);
   const recovered=await api.getRequest(assessmentRequest.requestId,{request:assessmentRequest});
   expect(isDeepStrictEqual(result,recovered)).toBe(true);
   const reopened=(await api.list({ids:[candidate.id],page:1,pageSize:1})).items[0];
   expect(reopened.assessment?.id).toBe(result.assessment.id);
   expect(reopened.assessmentStale).toBe(false);
   expect(reopened.status).toBe('PENDING_REVIEW');expect(reopened.sourceStatus).toBe('UNVERIFIED');
   expect(reopened.opportunityId).toBeUndefined();expect(assessRequests).toBe(1);
   assessmentSummary={sourceId:assessSourceId,id:result.assessment.id,decision:result.assessment.effectiveDecision,
    grade:result.assessment.grade,assessRequests,persisted:true};
  }
  await first.shutdown();const restored=controller();await restored.start(command);
  expect([sourceReads,driverStarts,candidateWrites]).toEqual([1,1,1]);
  expect(replyReads).toBe(project?records.length:0);
  let tasks=1;
  if(!network){
   // New ordinary task after a simulated process restart; synthetic I/O only.
   // Same-process cross-source cooldown is covered by publicCommunityDriver.test.
   const originalItems=accepted!.items;await restored.shutdown();const next=controller();
   const repeated=await next.start({...command,requestId:randomUUID()});
   if(repeated.state!=='RECORDED'||repeated.receipt.operation!=='START')throw new Error('second START not recorded');
   const repeatId=repeated.receipt.task_id;expect(repeatId).not.toBe(taskId);
   await vi.waitFor(async()=>{expect(await next.execute({action:'STATUS',taskId:repeatId})).toMatchObject({localState:'COMPLETED',serverStatus:'SUCCEEDED',recordsUsed:records.length});},{timeout:10000,interval:100});
   expect(accepted!.items.map(x=>[x.candidate_id,x.version_id])).toEqual(originalItems.map(x=>[x.candidate_id,x.version_id]));
   expect([sourceReads,driverStarts,driverStops,candidateWrites]).toEqual([2,2,2,2]);tasks=2;
  }
  expect(replyReads).toBe(project?records.length*tasks:0);
  console.log('PUBLIC_COMMUNITY_RESULT '+JSON.stringify({mode:network?'network':'fixture',records:records.length,taskId,sourceReads,replyReads,tasks,sourceId,collectorVersion:records[0].collector_version,
   ...(assessmentSummary?{assessment:assessmentSummary}:{}),
   ...(project?{authorContext:records.map(r=>({id:r.external_source_id,read:r.source_context!.replies_read,expected:r.source_context!.replies_expected,authorReplies:r.source_context!.author_replies.length,matched:r.source_context!.replies_complete}))}:{})}));
 }finally{
  if(network)diagnostics.unsubscribe(observe);
  for(const controller of controllers)await controller.shutdown();
  const cleanup=path.resolve(directory);if(path.dirname(cleanup)!==path.resolve(tmpdir())||!path.basename(cleanup).startsWith('yike-public-live-'))throw new Error('unsafe fixture cleanup');
  await rm(cleanup,{recursive:true,force:true});
 }
},45000);
