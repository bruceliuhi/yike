/** Real authenticated local handler/PG output; source/model I/O is synthetic, not platform proof. */
import {readFileSync} from 'node:fs';
import {expect,it} from 'vitest';
import {createResearchRuntimeService} from '../src/renderer/services/researchRuntime';
import {createServiceClient} from '../src/main/serviceClient';
import {ServiceError} from '../src/renderer/services/contracts';
import {researchRuntimeStatusSchema,researchAllowsSelection} from '../src/shared/researchRuntime';

const artifact=process.env.YIKE_SOURCE_PLAN_HTTP_ARTIFACT;
it.skipIf(!artifact)('consumes actual multi-source handler receipts using formal IPC, transport and renderer schemas',async()=>{
  const record=JSON.parse(readFileSync(artifact!,'utf8'));
  expect(record.evidenceKind).toBe('local_authenticated_http_restricted_postgresql_synthetic_source_and_model');
  const replies=[record.capability,record.queued,record.afterFirstSource,record.afterAllSources,record.completed];
  const paths:string[]=[];
  const main=createServiceClient({baseUrl:'https://synthetic.example',clearSession:async()=>{},fetch:async(url,options)=>{
    expect(options.redirect).toBe('manual');paths.push(url);
    return new Response(JSON.stringify(replies.shift()),{headers:{'Content-Type':'application/json'}});
  }});
  const renderer=createResearchRuntimeService(async(operation,_path,_method,payload)=>{
    const result=await main.request({operation,payload});
    if(!result.ok)throw new ServiceError(result.error,'failed',result.status);
    return result.data;
  });
  const capability=await renderer.capability();
  expect(researchAllowsSelection(capability,'v2ex-latest-v1',{version:1,sources:['v2ex-latest-v1','v2ex-qna-v1']})).toBe(true);
  const queued=await renderer.status(record.queued.taskId);
  const first=await renderer.advance(queued.taskId,queued.runId);
  expect(first.acceptedOriginals).toBeNull();expect(first.canAdvance).toBe(true);
  expect(first.sourceProgress?.map(source=>source.phase)).toEqual(['SUCCEEDED','NOT_STARTED']);
  const sourced=await renderer.advance(queued.taskId,queued.runId);
  expect(sourced.acceptedOriginals).toBe(3);expect(sourced.analyzedOriginals).toBe(0);
  // Backend artifact executed the model sequence; now refresh its stored completion.
  const completed=await renderer.status(queued.taskId);
  expect(completed).toEqual(researchRuntimeStatusSchema.parse(record.completed));
  expect(completed.phase).toBe('COMPLETED');expect(completed.analyzedOriginals).toBe(3);
  expect(completed.sourceProgress?.map(source=>source.recordLimit)).toEqual([2,1]);
  expect(paths).toEqual(['https://synthetic.example/api/ui/research-execution/capability?source_plan_version=1',
    `https://synthetic.example/api/ui/research-execution/tasks/${queued.taskId}`,
    `https://synthetic.example/api/ui/research-execution/tasks/${queued.taskId}/advance`,
    `https://synthetic.example/api/ui/research-execution/tasks/${queued.taskId}/advance`,
    `https://synthetic.example/api/ui/research-execution/tasks/${queued.taskId}`]);
});
