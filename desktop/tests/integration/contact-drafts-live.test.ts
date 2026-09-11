import {expect,it,vi} from 'vitest';
import {createServiceClient} from '../../src/main/serviceClient';
import {service} from '../../src/renderer/services/client';
import {draftSnapshot,snapshotDigest,type DraftSaveInput} from '../../src/renderer/domain/shortCoach';

const prefix='YIKE_DRAFT_LIVE_';
it.skipIf(!process.env[`${prefix}BASE`])('persists and restores manual drafts over actual authenticated HTTP',async()=>{
 const base=process.env[`${prefix}BASE`]!,token=process.env[`${prefix}TOKEN`]!,opp=process.env[`${prefix}OPPORTUNITY`]!;
 expect(new URL(base).hostname).toBe('127.0.0.1');
 expect(Object.keys(process.env).filter(key=>/DATABASE|^POSTGRES_/i.test(key))).toEqual([]);
 let cookie='',drop=false;
 const calls:string[]=[];
 const client=createServiceClient({baseUrl:base,clearSession:async()=>{cookie='';},fetch:async(url,options)=>{
  const path=new URL(url).pathname;expect(new URL(url).origin).toBe(base);
  const headers=new Headers(options.headers);if(cookie)headers.set('Cookie',cookie);
  const response=await fetch(url,{...options,headers});
  const session=response.headers.getSetCookie().find(value=>value.startsWith('pilot_session='));
  if(session)cookie=session.split(';',1)[0];
  calls.push(path);expect(response.headers.get('cache-control')).toBe('no-store');
  if(drop&&path==='/api/ui/contact-drafts'){drop=false;await response.text();throw new Error('synthetic lost save response');}
  return response;
 }});
 vi.stubGlobal('window',{yikeDesktop:{requestApi:client.request}});
 try{
  const session=await service.loginToken(token),row=await service.opportunity(opp);
  expect(row.sourceEvidenceVersion).toBeTruthy();
  const api=service.contactDrafts!;expect(api).toBeDefined();
  expect(await api.latest!(opp,'dm')).toBeNull();
  const snapshot=draftSnapshot(row,{opportunityId:opp,channel:'dm',content:'您好，采购输送设备的需求还在推进吗？',
   savedContent:row.dm,version:2,accountId:'synthetic-account',recipient:'synthetic-buyer'},session.accountScope);
  const first:DraftSaveInput={snapshot,previousRequestId:null,binding:{opportunityId:opp,channel:'dm',requestId:crypto.randomUUID(),contentHash:await snapshotDigest(snapshot)}};
  const saved=await api.save(first).catch(error=>{throw new Error(`First save failed: ${error.code ?? error.name}`);});
  expect(saved.status).toBe('SUCCEEDED');expect(await api.latest!(opp,'dm')).toEqual(saved);
  expect(await api.latest!(opp,'comment')).toBeNull();
  const nextSnapshot={...saved.snapshot!,draft:{...saved.snapshot!.draft,content:'设备清单可以先发我看看吗？',version:3}};
  const second:DraftSaveInput={snapshot:nextSnapshot,previousRequestId:first.binding.requestId,
   binding:{...first.binding,requestId:crypto.randomUUID(),contentHash:await snapshotDigest(nextSnapshot)}};
  drop=true;await expect(api.save(second)).rejects.toThrow();
  const recovered=await api.operation(second.binding);
  expect(recovered.snapshot?.draft.content).toBe(nextSnapshot.draft.content);
  expect(await api.latest!(opp,'dm')).toEqual(recovered);
  expect(await api.operation(first.binding)).toEqual(saved);
  const staleSnapshot={...nextSnapshot,draft:{...nextSnapshot.draft,content:'旧窗口文字',version:4}};
  await expect(api.save({...second,snapshot:staleSnapshot,binding:{...second.binding,requestId:crypto.randomUUID(),contentHash:await snapshotDigest(staleSnapshot)}})).rejects.toThrow();
  expect(await api.latest!(opp,'dm')).toEqual(recovered);
  expect(calls.every(path=>path==='/api/ui/session'||path.startsWith('/api/ui/contact-drafts')||path.startsWith(`/api/ui/opportunities/${opp}`))).toBe(true);
  await service.logout();await service.loginToken(process.env[`${prefix}OTHER_TOKEN`]!);
  expect(await api.latest!(opp,'dm')).toBeNull();
  await expect(api.operation(second.binding)).rejects.toThrow();
  await service.logout();await expect(api.latest!(opp,'dm')).rejects.toThrow();
 }finally{vi.unstubAllGlobals();}
},20_000);
