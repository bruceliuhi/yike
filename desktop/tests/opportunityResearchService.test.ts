import {describe,it,expect,vi} from 'vitest';
import {createOpportunityResearchService} from '../src/renderer/services/opportunityResearch';
import {validatedOperation} from '../src/main/servicePolicy';
import {collection,binding,timeline,similar as exampleSimilar} from './ui/r4-opportunity-research-fixtures';
import {parseResearchCollection,parseResearchTimeline,researchBinding} from '../src/renderer/domain/opportunityResearch';

const session=()=>Promise.resolve({authenticated:true,userId:binding.userId,accountScope:binding.accountScope});
const similar={...exampleSimilar,requestId:'00000000-0000-4000-8000-000000000001'};
describe('connected opportunity research reads',()=>{
 it('reads a collection bound to independently authenticated session scope',async()=>{
  const transport=vi.fn().mockResolvedValue(collection), service=createOpportunityResearchService(transport,session);
  expect(await service.list()).toEqual(collection);
  expect(transport).toHaveBeenCalledWith('research.list','/opportunity-research','GET',undefined,undefined);
  transport.mockResolvedValue({...collection,accountScope:{...collection.accountScope,id:'other'}});
  await expect(service.list()).rejects.toThrow();
 });
 it('does not discover session identity from a collection response',async()=>{
  const transport=vi.fn().mockResolvedValue(collection);
  await expect(createOpportunityResearchService(transport,async()=>({authenticated:false})).list()).rejects.toThrow();
  expect(transport).not.toHaveBeenCalled();
 });
 it('uses fixed read-only preview routes and validates original binding',async()=>{
  const transport=vi.fn().mockResolvedValueOnce(timeline).mockResolvedValueOnce(similar);
  const service=createOpportunityResearchService(transport,session);
  expect(await service.timeline(binding)).toEqual(timeline);
  expect(await service.similar(binding,similar.requestId)).toEqual(similar);
  expect(transport.mock.calls.map(call=>call.slice(0,4))).toEqual([
   ['research.timeline','/opportunity-research/timeline','POST',{binding}],
   ['research.similar','/opportunity-research/similar','POST',{binding,requestId:similar.requestId}],
  ]);
  transport.mockResolvedValue({...similar,requestId:'another-request'});
  await expect(service.similar(binding,similar.requestId)).rejects.toThrow();
 });
 it('keeps errors as errors and refuses abort before and after read',async()=>{
  const transport=vi.fn().mockRejectedValue(new Error('offline')),service=createOpportunityResearchService(transport,session);
  await expect(service.list()).rejects.toThrow('offline');
  const abort=new AbortController();abort.abort();transport.mockClear();
  await expect(service.timeline(binding,abort.signal)).rejects.toThrow();
  expect(transport).not.toHaveBeenCalled();
  const late=new AbortController();transport.mockImplementation(async()=>{late.abort();return timeline;});
  await expect(service.timeline(binding,late.signal)).rejects.toThrow();
 });
 it('allows only bounded bindings and no caller-selected route or tenant',()=>{
  expect(validatedOperation({operation:'research.list'})).toEqual({path:'/api/ui/opportunity-research',method:'GET',logout:false});
  const route=validatedOperation({operation:'research.timeline',payload:{binding}})!;
  expect(route).toMatchObject({path:'/api/ui/opportunity-research/timeline',method:'POST',logout:false});
  expect(JSON.parse(route.body!)).toEqual({binding});
  expect(validatedOperation({operation:'research.similar',payload:{binding,requestId:similar.requestId}})).toMatchObject({path:'/api/ui/opportunity-research/similar',method:'POST'});
  for(const payload of [{binding,tenant_id:'other'},{binding:{...binding,userId:''}},{binding:{...binding,sourceUrl:'file:///etc/passwd'}},{binding,requestId:'x'.repeat(513)}]){
   expect(validatedOperation({operation:'research.similar',payload})).toBeNull();
  }
 });
 it('keeps legacy rows without invented evidence versions and forbids research binding',()=>{
  const row=structuredClone(collection.records[0]);delete row.opportunity.sourceEvidenceVersion;
  row.classification={...row.classification,category:'UNASSESSED',evidence:[],review:{status:'NEEDS_EVIDENCE',reviewer:'',reviewedAt:null}};
  const result=parseResearchCollection({...collection,records:[row]},binding.userId,Date.now(),binding.accountScope);
  expect(result.records).toHaveLength(1);
  expect(researchBinding(result.records[0].opportunity,binding.userId,binding.accountScope)).toBeNull();
  row.classification.category='OPPORTUNITY';
  expect(()=>parseResearchCollection({...collection,records:[row]},binding.userId,Date.now(),binding.accountScope)).toThrow();
 });
 it('does not collapse distinct comments sharing a post URL',()=>{
  const other=structuredClone(collection.records[0]);other.opportunity.id='other-comment';other.opportunity.sourceEvidenceVersion='other-version';
  other.classification.evidence=other.classification.evidence.map(q=>({...q,evidenceVersion:'other-version'}));
  expect(parseResearchCollection({...collection,records:[collection.records[0],other]},binding.userId,Date.now(),binding.accountScope).records).toHaveLength(2);
 });
 it('preserves timeline source whitespace and decomposed characters',()=>{
  const raw=structuredClone(timeline);
  raw.versions[0].content=` \n${raw.versions[0].content} e\u0301😀\t `;
  expect(parseResearchTimeline(raw,binding).versions[0].content).toBe(raw.versions[0].content);
 });
});
