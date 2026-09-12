// @vitest-environment jsdom
import {webcrypto} from 'node:crypto';
import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import {nativeResearchStartCommand} from '../src/renderer/domain/nativeResearch';
import {newTaskDraft,type PlatformConnection,type Session,type TaskDraft} from '../src/renderer/domain/models';
import {defaultResearchSettings,usageQuoteRequest,type UsageQuote} from '../src/renderer/domain/researchUsage';
import {configurationHash,hashText} from '../src/renderer/domain/taskOperations';
import {strategyPrepareRequest} from '../src/renderer/domain/researchStrategies';
import type {StrategyReceipt} from '../src/shared/researchStrategies';
import type {PublicSourceId} from '../src/shared/publicSources';

const id=(n:number)=>`10000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
async function fixture(source?:PublicSourceId){
  const draft:TaskDraft={...newTaskDraft(),id:id(1),profileId:id(2),name:'合成公开研究',platforms:['web'],accounts:{},mode:'once',
    terms:[{id:id(3),value:'采购',origin:'manual',edited:false}],executionLimits:{max_records:10,max_runtime_seconds:60},
    research:{...defaultResearchSettings(),maxSoubei:20,limits:{sources:2,minutes:3,modelCalls:4}},...(source?{publicSource:source}:{})};
  const strategyRequest=strategyPrepareRequest(draft,id(4),{max_records:10,max_runtime_seconds:60});const prepared:StrategyReceipt={schema_version:'strategy-confirmation-v1',request_id:id(4),operation:'PREPARE',
    strategy_version_id:id(5),draft_id:draft.id,draft_revision:draft.revision,profile_version_id:draft.profileId,profile_sha256:'a'.repeat(64),configuration_sha256:'b'.repeat(64),
    state:'DRAFT',recorded_at:'2026-09-11T00:00:00Z',snapshot:{strategy_version_id:id(5),profile_version_id:draft.profileId,configuration:strategyRequest.configuration,
      platforms:strategyRequest.platforms,max_records:10,max_runtime_seconds:60}};
  const session:Session={authenticated:true,userId:'test-user',accountScope:{id:'test-space',version:1}};
  const binding={strategyVersionId:id(5),profileVersionId:id(2),configurationSha256:'b'.repeat(64)};
  const hash=await hashText(JSON.stringify([await configurationHash(draft),draft.executionLimits,binding]));
  const input=usageQuoteRequest(draft,session,hash,binding);const quote:UsageQuote={...input,requestId:id(6),quoteId:id(7),ruleVersion:'test-rule-v1',
    ruleSha256:'c'.repeat(64),authorizationToken:'abc.def',estimatedSoubei:5,generatedAt:new Date(Date.now()-1000).toISOString(),
    expiresAt:new Date(Date.now()+60_000).toISOString(),basis:'TEST only'};
  const connections:PlatformConnection[]=[{platform:'web',status:'CONNECTED',capabilities:['search'],publicBinding:{sourceId:'v2ex-latest-v1',deviceId:id(8)}}];
  return {draft,prepared,session,quote,connections};
}
beforeEach(()=>vi.stubGlobal('crypto',webcrypto));afterEach(()=>vi.unstubAllGlobals());
describe('native research command binding',()=>{
  it.each(['v2ex-qna-v1','v2ex-outsourcing-authors-v1'] as const)('preserves selected %s and requires that public binding',async(source)=>{
    const f=await fixture(source);
    await expect(nativeResearchStartCommand(f.draft,f.prepared,f.connections,f.session,f.quote,id(9))).rejects.toThrow();
    f.connections[0].publicBinding!.sourceIds=['v2ex-latest-v1',source];
    const command=await nativeResearchStartCommand(f.draft,f.prepared,f.connections,f.session,f.quote,id(9));
    expect(command.configurationSha256).toBe(f.prepared.configuration_sha256);
    expect(f.prepared.snapshot.configuration.publicSource).toBe(source);
    await expect(nativeResearchStartCommand({...f.draft,publicSource:'v2ex-latest-v1'},f.prepared,f.connections,f.session,f.quote,id(9))).rejects.toThrow();
  });
  it('binds the actual configuration hash, fresh quote, rule digest and exact limits',async()=>{const f=await fixture();
    const command=await nativeResearchStartCommand(f.draft,f.prepared,f.connections,f.session,f.quote,id(9));
    expect(command).toMatchObject({action:'RESEARCH_START',requestId:id(9),profileVersionId:id(2),strategyVersionId:id(5),configurationSha256:'b'.repeat(64),
      authorizationToken:'abc.def',reservation:{quote_id:id(7),rule_version:'test-rule-v1',rule_sha256:'c'.repeat(64),estimated_soubei:5,max_soubei:20,
        limits:{sources:2,minutes:3,modelCalls:4}}});
  });
  it('rejects expired, changed-hash, and changed strategy quotes',async()=>{const f=await fixture();
    await expect(nativeResearchStartCommand(f.draft,f.prepared,f.connections,f.session,{...f.quote,expiresAt:new Date(Date.now()-1).toISOString()},id(9))).rejects.toThrow();
    await expect(nativeResearchStartCommand({...f.draft,name:'changed'},f.prepared,f.connections,f.session,f.quote,id(9))).rejects.toThrow();
    await expect(nativeResearchStartCommand(f.draft,f.prepared,f.connections,f.session,{...f.quote,strategyBinding:{...f.quote.strategyBinding!,strategyVersionId:id(10)}},id(9))).rejects.toThrow();
  });
  it('rejects multi-platform, monitor, missing source and oversized execution boundaries',async()=>{const f=await fixture();
    for(const draft of [{...f.draft,platforms:['web','bilibili']},{...f.draft,mode:'monitor'},{...f.draft,executionLimits:{max_records:101,max_runtime_seconds:60}}] as TaskDraft[])
      await expect(nativeResearchStartCommand(draft,f.prepared,f.connections,f.session,f.quote,id(9))).rejects.toThrow(/V2EX/);
    await expect(nativeResearchStartCommand(f.draft,f.prepared,[],f.session,f.quote,id(9))).rejects.toThrow(/V2EX/);
  });
});
