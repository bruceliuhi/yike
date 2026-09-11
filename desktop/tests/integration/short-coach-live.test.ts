import {expect,it,vi} from 'vitest';
import {createServiceClient} from '../../src/main/serviceClient';
import {service} from '../../src/renderer/services/client';
import {makeCoachInput} from '../../src/renderer/domain/shortCoach';

it.skipIf(!process.env.YIKE_COACH_LIVE_BASE)('confirms exact ordinary client input over real HTTP and replays once',async()=>{
 const base=process.env.YIKE_COACH_LIVE_BASE!,token=process.env.YIKE_COACH_LIVE_TOKEN!,opp=process.env.YIKE_COACH_LIVE_OPPORTUNITY!;
 expect(new URL(base).hostname).toBe('127.0.0.1');
 expect(Object.keys(process.env).filter(key=>/DATABASE|^POSTGRES_/i.test(key))).toEqual([]);
 let cookie='';const paths:string[]=[];
 const client=createServiceClient({baseUrl:base,clearSession:async()=>{cookie='';},fetch:async(url,options)=>{
  expect(new URL(url).origin).toBe(base);paths.push(new URL(url).pathname);
  const headers=new Headers(options.headers);if(cookie)headers.set('Cookie',cookie);
  const response=await fetch(url,{...options,headers});
  if(!response.ok){const body=await response.clone().json().catch(()=>null);const code=body?.detail?.code??body?.code;
   console.info('COACH_HTTP_FAILURE',response.status,typeof code==='string'&&/^[a-z_]+$/i.test(code)?code:'unclassified');}
  const session=response.headers.getSetCookie().find(v=>v.startsWith('pilot_session='));if(session)cookie=session.split(';',1)[0];
  expect(response.headers.get('cache-control')).toBe('no-store');return response;
 }});
 vi.stubGlobal('window',{yikeDesktop:{requestApi:client.request}});
 try{
  const session=await service.loginToken(token),row=await service.opportunity(opp),api=service.shortCoach!;
  const input=await makeCoachInput(row,{opportunityId:opp,channel:'dm',content:'现在还在找团队吗？',
   savedContent:'',version:2,accountId:'local-only',recipient:'local-only'},'requirement',crypto.randomUUID(),session.accountScope!);
  const preview=await api.preview!(input);expect(preview.modelProvider).toBe('synthetic');
  expect(paths).not.toContain('/api/ui/short-coach/generate');
  const accepted={...input,disclosure:{...preview,accepted:true as const}};
  const result=await api.generate(accepted);
  expect(result.content).toBe('您好，项目需求还在推进吗？');
  expect(await api.generate(accepted)).toEqual(result);
  expect(result.quotes[0].text).toBe(input.sourceText.slice(result.quotes[0].start,result.quotes[0].end));
  await service.logout();await expect(api.preview!(input)).rejects.toThrow();
 }finally{vi.unstubAllGlobals();}
},20_000);
