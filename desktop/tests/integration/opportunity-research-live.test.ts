import {expect,it,vi} from 'vitest';
import {createServiceClient} from '../../src/main/serviceClient';
import {service} from '../../src/renderer/services/client';
import {researchBinding} from '../../src/renderer/domain/opportunityResearch';

const prefix='YIKE_RESEARCH_LIVE_';
it.skipIf(!process.env[`${prefix}BASE`])('reads real research evidence and similar preview through the desktop HTTP boundary',async()=>{
 const base=process.env[`${prefix}BASE`]!,token=process.env[`${prefix}TOKEN`]!,user=process.env[`${prefix}USER`]!,id=process.env[`${prefix}OPPORTUNITY`]!;
 expect(new URL(base).hostname).toBe('127.0.0.1');expect(token&&user&&id).toBeTruthy();
 expect(Object.keys(process.env).filter(key=>/DATABASE|^POSTGRES_/i.test(key))).toEqual([]);
 let cookie='';const calls:{path:string;method:string}[]=[];
 const client=createServiceClient({baseUrl:base,clearSession:async()=>{cookie='';},fetch:async(url,options)=>{
  expect(new URL(url).origin).toBe(base);
  const headers=new Headers(options.headers);if(cookie)headers.set('Cookie',cookie);
  const response=await fetch(url,{...options,headers});
  const session=response.headers.getSetCookie().find(value=>value.startsWith('pilot_session='));
  if(session)cookie=session.split(';',1)[0];
  calls.push({path:new URL(url).pathname,method:options.method!});
  expect(response.headers.get('cache-control')).toBe('no-store');return response;
 }});
 vi.stubGlobal('window',{yikeDesktop:{requestApi:client.request}});
 try{
  expect((await service.loginToken(token)).userId).toBe(user);
  const session=await service.session(),api=service.opportunityResearch!;
  const rows=await api.list(),row=rows.records.find(item=>item.opportunity.id===id)!;
  expect(row).toBeDefined();expect(row.classification.review.status).toBe('RECOGNIZED');
  const binding=researchBinding(row.opportunity,user,session.accountScope)!;expect(binding).not.toBeNull();
  const timeline=await api.timeline(binding);
  expect(timeline.versions.at(-1)?.id).toBe(binding.evidenceVersion);
  expect(timeline.versions.at(-1)?.content).toBe(row.opportunity.excerpt);
  const requestId=crypto.randomUUID(),first=await api.similar(binding,requestId),again=await api.similar(binding,requestId);
  expect(first.eligible).toBe(true);expect(first.usage.status).toBe('UNKNOWN');
  expect(first.recognition?.reviewer).toBe(row.classification.review.reviewer);
  expect(first.recognition?.reviewedAt).toBe(row.classification.review.reviewedAt);
  expect(first.keywords.length).toBeGreaterThan(0);
  expect(again.suggestionId).toBe(first.suggestionId);expect(again.keywords).toEqual(first.keywords);
  const cross=await client.request({operation:'research.timeline',payload:{binding:{...binding,userId:'another-user'}}});
  expect(cross.ok).toBe(false);
  expect(calls.every(call=>['/api/ui/session','/api/ui/opportunity-research','/api/ui/opportunity-research/timeline','/api/ui/opportunity-research/similar'].includes(call.path))).toBe(true);
  await service.logout();await expect(api.list()).rejects.toThrow();
 }finally{vi.unstubAllGlobals();}
},20_000);
