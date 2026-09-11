import {expect,it,vi} from 'vitest';
import {createServiceClient} from '../../src/main/serviceClient';
import {service} from '../../src/renderer/services/client';

const prefix='YIKE_COVERAGE_LIVE_';
it.skipIf(!process.env[`${prefix}BASE`])('reads persisted coverage via ordinary client and authenticated HTTP',async()=>{
 const base=process.env[`${prefix}BASE`]!,token=process.env[`${prefix}TOKEN`]!,user=process.env[`${prefix}USER`]!,task=process.env[`${prefix}TASK`]!;
 expect(new URL(base).hostname).toBe('127.0.0.1');
 expect(Object.keys(process.env).filter(key=>/DATABASE|^POSTGRES_/i.test(key))).toEqual([]);
 let cookie='';const calls:string[]=[];
 const client=createServiceClient({baseUrl:base,clearSession:async()=>{cookie='';},fetch:async(url,options)=>{
  expect(new URL(url).origin).toBe(base);
  const headers=new Headers(options.headers);if(cookie)headers.set('Cookie',cookie);
  const response=await fetch(url,{...options,headers});
  const session=response.headers.getSetCookie().find(value=>value.startsWith('pilot_session='));
  if(session)cookie=session.split(';',1)[0];
  calls.push(new URL(url).pathname);
  expect(response.headers.get('cache-control')).toBe('no-store');return response;
 }});
 vi.stubGlobal('window',{yikeDesktop:{requestApi:client.request}});
 try{
  expect((await service.loginToken(token)).userId).toBe(user);
  const session=await service.session(),item=await service.taskFeed!.get(task);
  expect(item.profile_version).toBeGreaterThan(0);
  const query={contractVersion:1 as const,requestId:crypto.randomUUID(),taskId:task,
   profileId:item.profile_version_id,profileVersion:item.profile_version!,
   expectedScope:{userId:user,accountScopeId:session.accountScope!.id,scopeVersion:session.accountScope!.version}};
  const snapshot=await service.searchCoverage!.query(query);
  expect(snapshot.runId).toBe(item.run_id);expect(snapshot.usage).toBeNull();
  expect(snapshot.coverage).not.toBe('COMPLETE');expect(snapshot.screening).toBe('UNKNOWN');
  expect(snapshot.units.reduce((n,u)=>n+(u.counts.rawContents??0),0)).toBe(Number(process.env[`${prefix}RAW`]));
  expect(snapshot.units.reduce((n,u)=>n+(u.counts.independentSources??0),0)).toBe(Number(process.env[`${prefix}SOURCES`]));
  const evidence=snapshot.units.flatMap(u=>u.evidence);
  expect(evidence.some(e=>e.excerpt===process.env[`${prefix}BODY`])).toBe(true);
  for(const unit of snapshot.units){
   expect(unit.unchecked.length).toBeGreaterThan(0);
   expect(unit.counts.requests).toBeNull();expect(unit.counts.confirmedOpportunities).toBeNull();
  }
  await expect(service.searchCoverage!.query({...query,profileVersion:item.profile_version!+1})).rejects.toThrow();
  const wrong=await client.request({operation:'coverage.query',payload:{...query,expectedScope:{...query.expectedScope,userId:'other-user'}}});
  expect(wrong.ok).toBe(false);
  expect(calls.every(path=>path==='/api/ui/session'||path==='/api/ui/search-coverage'||path===`/api/ui/execution-task-feed/${task}`)).toBe(true);
  await service.logout();await expect(service.searchCoverage!.query(query)).rejects.toThrow();
 }finally{vi.unstubAllGlobals();}
},20_000);
