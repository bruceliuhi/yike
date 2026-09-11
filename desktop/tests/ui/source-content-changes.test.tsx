// @vitest-environment jsdom
import {cleanup,render,screen,within} from '@testing-library/react';
import {afterEach,expect,it,vi} from 'vitest';
import type {AppContextValue} from '../../src/renderer/app/context';
import {parseResearchTimeline} from '../../src/renderer/domain/opportunityResearch';
import {createOpportunityResearchService} from '../../src/renderer/services/opportunityResearch';
import {EvidenceTimeline} from '../../src/renderer/pages/opportunities/EvidenceTimeline';
import {binding,researchRow,timeline as legacy} from './r4-opportunity-research-fixtures';
let context:AppContextValue;
vi.mock('../../src/renderer/app/context',()=>({useApp:()=>context}));
afterEach(()=>{cleanup();vi.restoreAllMocks();});
const at=(minutes:number)=>new Date(Date.now()-minutes*60000).toISOString();
function snapshot(){
 const generatedAt=at(0),t1=at(8),t2=at(6),t3=at(4);
 const versions=[{...legacy.versions[0],id:'v2',ordinal:1,previousVersionId:null,content:'需要一期知识库开发',observedAt:t1,access:'UNKNOWN' as const},
  {...legacy.versions[1],id:'v3',ordinal:2,previousVersionId:'v2',content:'增加客服系统对接',observedAt:t2,access:'UNKNOWN' as const}];
 const observations=[{id:'o1',versionId:'v2',observedAt:t1,receivedAt:t1},{id:'o2',versionId:'v3',observedAt:t2,receivedAt:t2},
  {id:'o3',versionId:'v2',observedAt:t3,receivedAt:t3}];
 const quote=(versionId:string)=>({sourceUrl:binding.sourceUrl,evidenceVersion:versionId,quote:versions.find(v=>v.id===versionId)!.content,field:'source.body' as const});
 const changes=observations.slice(1).map((o,i)=>({id:'change-'+i,kind:'CONTENT' as const,label:'观察到正文不同',
  from:quote(observations[i].versionId),to:quote(o.versionId),occurredAt:null,detectedAt:o.receivedAt,
  fromObservationId:observations[i].id,toObservationId:o.id}));
 return {schemaVersion:2 as const,binding,snapshotId:'snapshot-2',generatedAt,expiresAt:new Date(Date.now()+60000).toISOString(),
  anchorObservationId:'o1',versions,observations,changes,contacts:[],gaps:[] as string[]};
}
it('accepts anchored A to B to A without inventing a third content version and keeps V1 strict',()=>{
 const raw=snapshot();const parsed=parseResearchTimeline(raw,binding);
 expect(parsed.versions).toHaveLength(2);expect(parsed.changes).toHaveLength(2);
 const legacyRaw={...structuredClone(legacy),generatedAt:at(0),expiresAt:new Date(Date.now()+60000).toISOString()};
 expect(parseResearchTimeline(legacyRaw,binding).schemaVersion).toBe(1);
 expect(()=>parseResearchTimeline({...legacyRaw,binding:{...binding,evidenceVersion:'v1'}},{...binding,evidenceVersion:'v1'})).toThrow();
});
it('rejects wrong anchor, source, observation direction, timestamps, missing changes and forged quotes',()=>{
 const mutations=[
  (v:ReturnType<typeof snapshot>)=>{v.anchorObservationId='o2';},
  (v:ReturnType<typeof snapshot>)=>{v.versions[1].sourceUrl='https://example.test/another';},
  (v:ReturnType<typeof snapshot>)=>{v.changes[1].fromObservationId='o3';},
  (v:ReturnType<typeof snapshot>)=>{v.changes[0].detectedAt=at(20);},
  (v:ReturnType<typeof snapshot>)=>{v.observations[2].receivedAt=new Date(Date.now()+600000).toISOString();},
  (v:ReturnType<typeof snapshot>)=>{v.changes.pop();},
  (v:ReturnType<typeof snapshot>)=>{v.changes[0].to.quote='伪造采购承诺';},
 ];
 for(const change of mutations){const raw=snapshot();change(raw);expect(()=>parseResearchTimeline(raw,binding)).toThrow();}
});
it('keeps equal-time conflicting observations unresolved and does not order them into a change',()=>{
 const raw=snapshot();raw.observations[1].observedAt=raw.observations[0].observedAt;
 raw.observations[1].receivedAt=raw.observations[0].receivedAt;raw.changes=[];raw.gaps=['同刻正文不一致，待核验'];
 expect(parseResearchTimeline(raw,binding).changes).toEqual([]);
 raw.changes=snapshot().changes;
 expect(()=>parseResearchTimeline(raw,binding)).toThrow();
});
it('consumes the actual fixed-route service response without changing the frozen opportunity evidence',async()=>{
 const raw=snapshot(),transport=vi.fn(async()=>raw);
 const api=createOpportunityResearchService(transport,async()=>({authenticated:true,userId:binding.userId,accountScope:binding.accountScope}));
 expect((await api.timeline(binding)).changes[1].to.evidenceVersion).toBe(binding.evidenceVersion);
 expect(transport.mock.calls[0]).toEqual(['research.timeline','/opportunity-research/timeline','POST',{binding},undefined]);
});
it('shows inclusion anchor, repeated original version and separate observation/receipt/edit time',async()=>{
 const raw=snapshot();context={session:{authenticated:true,userId:binding.userId,accountScope:binding.accountScope},
  service:{opportunityResearch:{timeline:vi.fn(async()=>raw)}}} as unknown as AppContextValue;
 render(<EvidenceTimeline opportunity={researchRow}/>);
 await screen.findByText('纳入商机时的依据');
 const events=screen.getByRole('list',{name:'原文观察记录'});
 expect(within(events).getAllByRole('listitem')).toHaveLength(3);
 expect(within(events).getAllByText('原文版本 v1')).toHaveLength(2);
 expect(screen.getAllByText(/实际编辑时间未知/)).toHaveLength(2);
 expect(screen.getAllByText(/系统收到证据/).length).toBeGreaterThan(1);
});
