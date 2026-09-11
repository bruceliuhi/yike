import {expect,it,vi} from 'vitest';
import {createServiceClient} from '../../src/main/serviceClient';
import {service} from '../../src/renderer/services/client';
import {readFollowupWorkspace} from '../../src/renderer/domain/followup';
it.skipIf(!process.env.YIKE_FOLLOWUP_LIVE_BASE)('persists full fields, recovers original request and preserves correction history',async()=>{
 const base=process.env.YIKE_FOLLOWUP_LIVE_BASE!,token=process.env.YIKE_FOLLOWUP_LIVE_TOKEN!,opp=process.env.YIKE_FOLLOWUP_LIVE_OPPORTUNITY!;
 expect(new URL(base).hostname).toBe('127.0.0.1');
 expect(Object.keys(process.env).filter(k=>/DATABASE|^POSTGRES_/i.test(k))).toEqual([]);
 let cookie='',drop=false;
 const client=createServiceClient({baseUrl:base,clearSession:async()=>{cookie='';},fetch:async(url,options)=>{
  expect(new URL(url).origin).toBe(base);const headers=new Headers(options.headers);if(cookie)headers.set('Cookie',cookie);
  const response=await fetch(url,{...options,headers});
  const session=response.headers.getSetCookie().find(v=>v.startsWith('pilot_session='));if(session)cookie=session.split(';',1)[0];
  if(drop&&new URL(url).pathname==='/api/ui/followup-workspace/mutate'){drop=false;await response.text();throw new Error('synthetic lost response');}
  return response;
 }});
 vi.stubGlobal('window',{yikeDesktop:{requestApi:client.request}});
 const latestStatus=async()=>{const response=await client.request({operation:'opportunities.list',payload:{}});
  expect(response.ok).toBe(true);if(!response.ok)throw new Error('opportunity read failed');
  return (response.data as {items:{opportunity_id:string;latest_followup_status:string}[]}).items.find(r=>r.opportunity_id===opp)?.latest_followup_status;};
 try{
  const user=await service.loginToken(token),row=await service.opportunity(opp),api=service.followup!;
  expect(readFollowupWorkspace(await api.list()).records.some(r=>r.legacy&&r.note==='synthetic legacy history')).toBe(true);
  const binding={opportunityId:opp,profileVersionId:row.profileVersionId!,action:'create' as const,targetId:'',targetRevision:0,requestId:crypto.randomUUID()};
  const values={status:'REPLIED' as const,note:'synthetic contacted',occurredAt:new Date(Date.now()-60000).toISOString(),nextStep:'发需求清单',nextFollowupAt:new Date(Date.now()+86400000).toISOString(),ownerId:user.userId!};
  drop=true;await expect(api.mutate({binding,values})).rejects.toThrow();
  const first=await api.operation(binding);expect(first.record).toMatchObject(values);
  expect(await api.mutate({binding,values})).toEqual(first);
  expect(await latestStatus()).toBe('REPLIED');
  const correction={binding:{...binding,action:'correct' as const,targetId:first.record!.id,targetRevision:first.record!.revision,requestId:crypto.randomUUID()},values:{...values,status:'QUOTED' as const,note:'synthetic corrected'},reason:'纠正事实'};
  const corrected=await api.mutate(correction);
  const list=await api.list();expect(list.records.find(r=>r.id===first.record!.id)?.state).toBe('CORRECTED');
  expect(list.records.find(r=>r.id===corrected.record!.id)?.state).toBe('ACTIVE');
  const voided=await api.mutate({binding:{...binding,action:'void',targetId:corrected.record!.id,targetRevision:corrected.record!.revision,requestId:crypto.randomUUID()},reason:'撤销错误记录'});
  expect(voided.record?.state).toBe('VOID');expect(await api.operation(binding)).toEqual(first);
  expect(await latestStatus()).toBe('CONTACTED');
  await expect(api.mutate({...correction,binding:{...correction.binding,requestId:crypto.randomUUID()}})).rejects.toThrow();
  await service.logout();await expect(api.list()).rejects.toThrow();
 }finally{vi.unstubAllGlobals();}
},20_000);
