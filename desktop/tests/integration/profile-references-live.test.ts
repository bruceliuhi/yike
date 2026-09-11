import {expect,it,vi} from 'vitest';
import {createServiceClient} from '../../src/main/serviceClient';
import {service} from '../../src/renderer/services/client';
it.skipIf(!process.env.YIKE_PROFILE_REF_BASE)('persists provenance, invalidates stale impact, and preserves manual/history after revoke',async()=>{
 const base=process.env.YIKE_PROFILE_REF_BASE!,source=process.env.YIKE_PROFILE_REF_SOURCE!,materialId=process.env.YIKE_PROFILE_REF_MATERIAL!;
 expect(new URL(base).hostname).toBe('127.0.0.1');expect(Object.keys(process.env).filter(k=>/DATABASE|^POSTGRES_/i.test(k))).toEqual([]);
 let cookie='';
 const client=createServiceClient({baseUrl:base,clearSession:async()=>{cookie='';},fetch:async(url,options)=>{
  const headers=new Headers(options.headers);if(cookie)headers.set('Cookie',cookie);
  const response=await fetch(url,{...options,headers});
  const session=response.headers.getSetCookie().find(v=>v.startsWith('pilot_session='));if(session)cookie=session.split(';',1)[0];return response;
 }});
 vi.stubGlobal('window',{yikeDesktop:{requestApi:client.request}});
 try{
  await service.loginToken(process.env.YIKE_PROFILE_REF_TOKEN!);
  const fields={service:'知识库实施',customer:'制造企业',regions:'上海',preference:'明确预算',exclusions:'招聘'};
  const materialVersion=Number(process.env.YIKE_PROFILE_REF_VERSION!);
  const first=await service.saveProfile(fields,{materialReferences:[{field:'service',sourceProfileVersionId:source,materialId,materialVersion,extractionId:process.env.YIKE_PROFILE_REF_EXTRACTION!}]});
  expect(first.materialReferences).toHaveLength(1);expect(first.materialReferences![0].valid).toBe(true);
  expect((await service.confirmProfile(first.id)).status).toBe('CONFIRMED');
  await service.searchSuggestions!.preview(first.id);
  const oldImpact=await service.materials!.impact(source,materialId,materialVersion,'revoke');
  expect(oldImpact.references.length).toBeGreaterThan(0);
  const second=await service.saveProfile({...fields,regions:'北京'},{baseProfileVersionId:first.id,materialReferences:[{field:'service',referenceId:first.materialReferences![0].referenceId}]});
  expect(second.id).not.toBe(first.id);
  const revoke=(token:string)=>service.materials!.mutate({requestId:crypto.randomUUID(),profileVersionId:source,change:{kind:'revoke',materialId,expectedVersion:materialVersion,impactToken:token}},{signal:new AbortController().signal,onUploadProgress:()=>{}});
  expect(await revoke(oldImpact.token)).toMatchObject({status:'FAILED',confirmedNoChange:true});
  const impact=await service.materials!.impact(source,materialId,materialVersion,'revoke');
  expect(impact.references.length).toBeGreaterThan(oldImpact.references.length);
  expect(await revoke(impact.token)).toMatchObject({status:'SUCCEEDED',record:{status:'REVOKED'}});
  await expect(service.searchSuggestions!.preview(first.id)).rejects.toThrow();
  const history=(await service.profiles()).find(p=>p.id===first.id)!;
  expect(history.fields).toEqual(fields);expect(history.status).toBe('CONFIRMED');expect(history.materialReferences![0].valid).toBe(false);
  const manual=await service.saveProfile(fields,{baseProfileVersionId:first.id,materialReferences:[]});
  expect(manual.id).not.toBe(first.id);expect(manual.materialReferences).toEqual([]);expect(manual.status).toBe('DRAFT');
  await service.logout();await expect(service.profiles()).rejects.toThrow();
 }finally{vi.unstubAllGlobals();}
},20_000);
