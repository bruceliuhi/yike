/** Actual authenticated local HTTP handler + restricted PG output; synthetic sources/model. */
import {readFileSync} from 'node:fs';
import {expect,it} from 'vitest';
import {researchRuntimeCapabilitySchema,researchRuntimeStatusSchema,researchAllowsSource} from '../src/shared/researchRuntime';
import {createResearchRuntimeService} from '../src/renderer/services/researchRuntime';
import {createServiceClient} from '../src/main/serviceClient';
import {ServiceError} from '../src/renderer/services/contracts';

const artifact=process.env.YIKE_TARGETED_RESEARCH_HTTP_ARTIFACT;
it.skipIf(!artifact)('replays the actual baseline capability rejection as one read-only fallback',async()=>{
  const records=JSON.parse(readFileSync(artifact!,'utf8')),paths:string[]=[];
  expect(records.legacyNegotiated.baseline).toBe('8da6d87496481958ada3558efffae0f27b776677');
  const main=createServiceClient({baseUrl:'https://synthetic.example',clearSession:async()=>{},fetch:async(url,options)=>{
    expect(options.method).toBe('GET');expect(options.body).toBeUndefined();paths.push(url);
    const reply=url.endsWith('?source_catalog_version=1')?records.legacyNegotiated:
      {status:200,body:records['v2ex-qna-v1'].legacyCapability};
    return new Response(JSON.stringify(reply.body),{status:reply.status,headers:{'Content-Type':'application/json'}});
  }});
  const renderer=createResearchRuntimeService(async(operation,_path,_method,payload)=>{
    const result=await main.request({operation,payload});
    if(!result.ok)throw new ServiceError(result.error,'failure',result.status);
    return result.data;
  });
  const capability=await renderer.capability();
  expect(capability.contractVersion).toBe(1);
  expect(researchAllowsSource(capability,'v2ex-qna-v1')).toBe(false);
  expect(paths).toEqual(['https://synthetic.example/api/ui/research-execution/capability?source_catalog_version=1',
    'https://synthetic.example/api/ui/research-execution/capability']);
});
it.skipIf(!artifact)('desktop consumes actual node research DTOs through the formal service and fixed IPC route',async()=>{
  const records=JSON.parse(readFileSync(artifact!,'utf8'));
  for(const source of ['v2ex-qna-v1','v2ex-outsourcing-authors-v1']){
    const entry=records[source],capability=researchRuntimeCapabilitySchema.parse(entry.capability);
    expect(researchAllowsSource(capability,source)).toBe(true);
    const seen:string[]=[];
    const responses=[entry.capability,entry.queued,entry.afterSource,entry.completed];
    // Only the network is substituted: consume output produced by the real Python handler/DB.
    const main=createServiceClient({baseUrl:'https://synthetic.example',clearSession:async()=>{},fetch:async(url,options)=>{
      expect(options.redirect).toBe('manual');seen.push(url);
      return new Response(JSON.stringify(responses.shift()),{headers:{'Content-Type':'application/json'}});
    }});
    const renderer=createResearchRuntimeService(async(operation,_path,_method,payload)=>{
      const result=await main.request({operation,payload});
      if(!result.ok)throw new ServiceError(result.error,'failed',result.status);
      return result.data;
    });
    expect(await renderer.capability()).toEqual(capability);
    const queued=await renderer.status(entry.queued.taskId);
    expect(queued.phase).toBe('QUEUED');
    const sourced=await renderer.advance(queued.taskId,queued.runId);
    expect(sourced.acceptedOriginals).toBe(1);
    const completed=await renderer.advance(queued.taskId,queued.runId);
    expect(completed).toEqual(researchRuntimeStatusSchema.parse(entry.completed));
    expect(completed.phase).toBe('COMPLETED');expect(completed.analyzedOriginals).toBe(1);
    expect(completed.usage.sourceReads.succeeded).toBe(1);
    expect(completed.usage.modelCalls.succeeded).toBe(1);
    expect(completed.sourceScope).toBe(source==='v2ex-qna-v1'?'V2EX_QNA_INDEX':'V2EX_OUTSOURCING_INDEX');
    expect(seen).toEqual([
      'https://synthetic.example/api/ui/research-execution/capability?source_catalog_version=1',
      `https://synthetic.example/api/ui/research-execution/tasks/${queued.taskId}`,
      `https://synthetic.example/api/ui/research-execution/tasks/${queued.taskId}/advance`,
      `https://synthetic.example/api/ui/research-execution/tasks/${queued.taskId}/advance`,
    ]);
  }
});
