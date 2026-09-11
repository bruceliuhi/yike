import {expect,it,vi} from 'vitest';
import {createServiceClient} from '../../src/main/serviceClient';
import {service} from '../../src/renderer/services/client';
import {briefBusinessDay} from '../../src/renderer/domain/opportunityBrief';
import {explicitInstant} from '../../src/renderer/domain/opportunityLibrary';
it.skipIf(!process.env.YIKE_BRIEF_LIVE_BASE)('reads verified contact then reflects actual planned followup and correction',async()=>{
 const base=process.env.YIKE_BRIEF_LIVE_BASE!,token=process.env.YIKE_BRIEF_LIVE_TOKEN!,opp=process.env.YIKE_BRIEF_LIVE_OPPORTUNITY!;
 expect(new URL(base).hostname).toBe('127.0.0.1');
 expect(Object.keys(process.env).filter(k=>/DATABASE|^POSTGRES_/i.test(k))).toEqual([]);
 let cookie='';let basisTimes:string[]=[];
 const client=createServiceClient({baseUrl:base,clearSession:async()=>{cookie='';},fetch:async(url,options)=>{
  expect(new URL(url).origin).toBe(base);const headers=new Headers(options.headers);if(cookie)headers.set('Cookie',cookie);
  const response=await fetch(url,{...options,headers});
  if(new URL(url).pathname==='/api/ui/opportunity-brief/query'&&response.ok){
   const payload=await response.clone().json();
   basisTimes=(Object.values(payload.groups) as {items:{basis:{verifiedAt:string}}[]}[]).flatMap(group=>group.items.map(item=>item.basis.verifiedAt));
  }
  const session=response.headers.getSetCookie().find(v=>v.startsWith('pilot_session='));if(session)cookie=session.split(';',1)[0];return response;
 }});
 vi.stubGlobal('window',{yikeDesktop:{requestApi:client.request}});
 try{
  const user=await service.loginToken(token),row=await service.opportunity(opp),profiles=await service.profiles();
  const profile=profiles.find(p=>p.id===row.profileVersionId)!;expect(profile).toBeDefined();
  const input={contractVersion:1 as const,requestId:crypto.randomUUID(),userId:user.userId!,accountScopeId:user.accountScope!.id,scopeVersion:1,profileId:profile.id,profileVersion:profile.version,businessDate:briefBusinessDay(Date.now(),'Asia/Shanghai'),timezone:'Asia/Shanghai'};
  const query=async()=>{
   basisTimes=[];
   try{return await service.opportunityBrief!.query({...input,requestId:crypto.randomUUID()});}
   finally{for(const value of basisTimes)expect(explicitInstant(value),`basis instant: ${value}`).toBe(true);}
  };
  const first=await query();expect(first.coverage).toBe('PARTIAL');
  expect(first.groups.contact.items.map(i=>i.opportunityId)).toContain(opp);
  expect(first.groups.contact.items.find(i=>i.opportunityId===opp)?.basis.kind).toBe('REVIEWED_DEMAND');
  expect(first.uncheckedScope.length).toBeGreaterThan(0);expect(first.groups.changes.total).toBe(0);
  const binding={opportunityId:opp,profileVersionId:profile.id,action:'create' as const,targetId:'',targetRevision:0,requestId:crypto.randomUUID()};
  const values={status:'REPLIED' as const,note:'synthetic interested reply',occurredAt:new Date(Date.now()-60000).toISOString(),nextStep:'约需求沟通',nextFollowupAt:new Date(Date.now()-1000).toISOString(),ownerId:user.userId!};
  const saved=await service.followup!.mutate({binding,values});
  const planned=await query();expect(planned.groups.contact.items.map(i=>i.opportunityId)).not.toContain(opp);
  expect(planned.groups.followup.items.find(i=>i.opportunityId===opp)?.basis).toMatchObject({recordId:saved.record!.id,kind:'MANUAL_FOLLOWUP'});
  await service.followup!.mutate({binding:{...binding,action:'correct',targetId:saved.record!.id,targetRevision:saved.record!.revision,requestId:crypto.randomUUID()},values:{...values,nextFollowupAt:null},reason:'清空计划'});
  expect((await query()).groups.followup.items.map(i=>i.opportunityId)).not.toContain(opp);
  await service.logout();await expect(query()).rejects.toThrow();
 }finally{vi.unstubAllGlobals();}
},20_000);
