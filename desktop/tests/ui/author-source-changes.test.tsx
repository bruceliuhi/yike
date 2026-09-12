// @vitest-environment jsdom
import {cleanup,render,screen,within} from '@testing-library/react';
import {afterEach,expect,it,vi} from 'vitest';
import {parseResearchTimeline} from '../../src/renderer/domain/opportunityResearch';
import {createOpportunityResearchService} from '../../src/renderer/services/opportunityResearch';
import {ServiceError} from '../../src/renderer/services/contracts';
import {validatedOperation} from '../../src/main/servicePolicy';
import {EvidenceTimeline} from '../../src/renderer/pages/opportunities/EvidenceTimeline';
import type {AppContextValue} from '../../src/renderer/app/context';
import {binding,researchRow,timeline as legacy} from './r4-opportunity-research-fixtures';

let context:AppContextValue;
vi.mock('../../src/renderer/app/context',()=>({useApp:()=>context}));
afterEach(()=>{cleanup();vi.restoreAllMocks();});
const at=(minutes:number)=>new Date(Math.floor(Date.now()/1000)*1000-minutes*60000).toISOString();
function snapshot(){
 const times=[at(8),at(6),at(4)];
 const bodies=['',' 还在选供应商，想先看案例。 ','预算调整，先做一个部门。'];
 const sourceContext=(index:number)=>({schema_version:'v2ex-author-context-v1' as const,
  replies_expected:index?1:0,replies_read:index?1:0,replies_complete:true,supplements_read:false as const,
  author_replies:index?[{id:'10',body:bodies[index],published_at:at(7).replace('.000Z','Z')}]:[]});
 const versions=times.map((time,i)=>({...legacy.versions[0],id:'v'+(i+2),ordinal:i+1,
  previousVersionId:i?'v'+(i+1):null,content:'主帖征询企业知识库服务',publishedAt:null,observedAt:time,
  authorPublicId:'buyer-1',sourceContext:sourceContext(i)}));
 const observations=times.map((time,i)=>({id:'o'+i,versionId:versions[i].id,observedAt:time,receivedAt:time}));
 const quote=(i:number)=>({sourceUrl:binding.sourceUrl,evidenceVersion:versions[i].id,quote:bodies[i]});
 const authorChanges=[{id:'author-new',replyId:'10',kind:'OBSERVED_NEW' as const,label:'首次观察到作者回复',
  fromObservationId:'o0',toObservationId:'o1',detectedAt:times[1],occurredAt:null,from:null as ReturnType<typeof quote>|null,to:quote(1)},
 {id:'author-modified',replyId:'10',kind:'MODIFIED' as const,label:'观察到作者回复正文变化',
  fromObservationId:'o1',toObservationId:'o2',detectedAt:times[2],occurredAt:null,from:quote(1),to:quote(2)}];
 return {schemaVersion:3 as const,binding,snapshotId:'author-v3',generatedAt:at(0),expiresAt:at(-1),
  anchorObservationId:'o0',versions,observations,changes:[],authorChanges,contacts:[],gaps:[] as string[]};
}
it('accepts V3 new and modified author replies without changing old V1/V2',()=>{
 const raw=snapshot();const parsed=parseResearchTimeline(raw,binding);
 expect(parsed.schemaVersion).toBe(3);
 if(parsed.schemaVersion!==3)throw new Error('expected V3');
 expect(parsed.authorChanges[0].from).toBeNull();
 expect(parsed.authorChanges[0].to.quote).toBe(' 还在选供应商，想先看案例。 ');
 expect(parseResearchTimeline(legacy,binding).schemaVersion).toBe(1);
 const {authorChanges,...old}=raw;
 const v2={...old,schemaVersion:2,versions:old.versions.map(({authorPublicId,sourceContext,...v})=>v)};
 expect(parseResearchTimeline(v2,binding).schemaVersion).toBe(2);
 expect(()=>parseResearchTimeline({...raw,schemaVersion:2},binding)).toThrow();
});
it('rejects missing, duplicated, forged, cross-author and impossible-time author events',()=>{
 const mutations:Array<(raw:ReturnType<typeof snapshot>)=>void>=[
  v=>{v.authorChanges.pop();},v=>{v.authorChanges.push({...v.authorChanges[0],id:'duplicate'});},
  v=>{v.authorChanges[0].replyId='11';},v=>{v.authorChanges[1].to.quote='已经成交';},
  v=>{v.authorChanges[1].from!.quote='原文没有这句';},v=>{v.authorChanges[0].from=v.authorChanges[0].to;},
  v=>{v.authorChanges[1].from=null;},v=>{v.authorChanges[1].fromObservationId='o0';},
  v=>{v.authorChanges[1].detectedAt=at(9);},v=>{v.versions[1].authorPublicId='another-author';},
  v=>{v.versions[1].sourceContext.author_replies[0].published_at=at(-2).replace('.000Z','Z');},
  v=>{v.authorChanges[0].to.evidenceVersion='v4';},
 ];
 for(const mutate of mutations){const raw=snapshot();mutate(raw);expect(()=>parseResearchTimeline(raw,binding)).toThrow();}
});
it('does not infer deletion from missing replies or emit events for read-count changes',()=>{
 const raw=snapshot();raw.authorChanges=raw.authorChanges.slice(0,1);
 raw.versions[2].sourceContext={...raw.versions[0].sourceContext,replies_expected:2,replies_read:0,replies_complete:false};
 raw.gaps=['本次未读到此前回复，不代表已删除。'];
 expect(parseResearchTimeline(raw,binding).schemaVersion).toBe(3);
 const counts=snapshot();counts.authorChanges=[];
 counts.versions.forEach(v=>{v.sourceContext.author_replies=[];});
 expect(parseResearchTimeline(counts,binding).schemaVersion).toBe(3);
});
it('does not order equal-millisecond conflicting author snapshots into an event',()=>{
 const raw=snapshot();raw.observations[1].observedAt=raw.observations[0].observedAt;
 raw.versions[1].sourceContext.author_replies[0].published_at=at(9).replace('.000Z','Z');
 raw.versions[2].sourceContext.author_replies[0].published_at=at(9).replace('.000Z','Z');
 raw.authorChanges=[];raw.gaps=['同一观察时间作者内容不一致。'];
 expect(parseResearchTimeline(raw,binding).schemaVersion).toBe(3);
});
it('reorders and repeats author replies without inventing a change and preserves A to B to A',()=>{
 const same=snapshot();same.authorChanges=[];
 const replies=[{id:'10',body:'需要知识库',published_at:at(9).replace('.000Z','Z')},
  {id:'20',body:'先看方案',published_at:at(9).replace('.000Z','Z')}];
 same.versions.forEach((v,i)=>{v.sourceContext={...v.sourceContext,replies_expected:3,replies_read:2,replies_complete:false,
  author_replies:i===1?[...replies].reverse():[...replies]};});
 expect(parseResearchTimeline(same,binding).schemaVersion).toBe(3);
 const raw=snapshot();const last=raw.observations[2];
 raw.observations.push({id:'o3',versionId:'v3',observedAt:at(2),receivedAt:at(2)});
 raw.authorChanges.push({...raw.authorChanges[1],id:'reverted',fromObservationId:last.id,toObservationId:'o3',
  from:raw.authorChanges[1].to,to:raw.authorChanges[1].from!,detectedAt:at(2)});
 const parsed=parseResearchTimeline(raw,binding);expect(parsed.schemaVersion).toBe(3);
 if(parsed.schemaVersion===3)expect(parsed.authorChanges).toHaveLength(3);
});
it('negotiates V3 through the fixed IPC and downgrades only an explicit old-server rejection',async()=>{
 const transport=vi.fn().mockRejectedValueOnce(new ServiceError('invalid_request','old server',422)).mockResolvedValueOnce(legacy);
 const service=createOpportunityResearchService(transport,async()=>({authenticated:true}));
 expect((await service.timeline(binding)).schemaVersion).toBe(1);
 expect(transport.mock.calls.map(c=>c[3])).toEqual([{binding,timelineSchemaVersion:3},{binding}]);
 expect(validatedOperation({operation:'research.timeline',payload:{binding,timelineSchemaVersion:3}})).not.toBeNull();
 expect(validatedOperation({operation:'research.timeline',payload:{binding,timelineSchemaVersion:2}})).toBeNull();
 for(const error of [new ServiceError('invalid_session','login',401),new ServiceError('invalid_request','bad gateway',503),new Error('timeout')]){
  transport.mockReset().mockRejectedValue(error);await expect(service.timeline(binding)).rejects.toThrow();
  expect(transport).toHaveBeenCalledTimes(1);
 }
 transport.mockReset().mockResolvedValue({...snapshot(),authorChanges:[]});
 await expect(service.timeline(binding)).rejects.toThrow();expect(transport).toHaveBeenCalledTimes(1);
 const abort=new AbortController();transport.mockReset().mockImplementation(async()=>{
  abort.abort();throw new ServiceError('invalid_request','old server',422);
 });
 await expect(service.timeline(binding,abort.signal)).rejects.toThrow();expect(transport).toHaveBeenCalledTimes(1);
});
it('shows exact author evidence and unknown previous text separately from body changes',async()=>{
 const raw=snapshot();context={session:{authenticated:true,userId:binding.userId,accountScope:binding.accountScope},
  service:{opportunityResearch:{timeline:vi.fn(async()=>raw)}}} as unknown as AppContextValue;
 render(<EvidenceTimeline opportunity={researchRow}/>);
 await screen.findByRole('heading',{name:'作者回复变化'});
 expect(screen.getByText('此前留存范围内未读到该回复')).not.toHaveProperty('tagName','BLOCKQUOTE');
 expect(within(screen.getByRole('region',{name:'作者回复变化'})).getByText('预算调整，先做一个部门。')).toBeTruthy();
 expect(within(screen.getByRole('list',{name:'原文观察记录'})).getAllByRole('listitem')).toHaveLength(3);
 expect(screen.getByText('纳入商机时的依据')).toBeTruthy();
});
it('retains readable author evidence even when the old observation has no comparable context',async()=>{
 const raw=snapshot();raw.versions=raw.versions.slice(0,2);raw.observations=raw.observations.slice(0,2);
 Object.assign(raw.versions[0],{sourceContext:null});raw.authorChanges=[];raw.gaps=['首次取得作者上下文，不能确定变化。'];
 context={session:{authenticated:true,userId:binding.userId,accountScope:binding.accountScope},
  service:{opportunityResearch:{timeline:vi.fn(async()=>raw)}}} as unknown as AppContextValue;
 render(<EvidenceTimeline opportunity={researchRow}/>);
 await screen.findByText('该次留存的作者回复');
 expect(screen.getByText('还在选供应商，想先看案例。')).toBeTruthy();
 expect(screen.queryByRole('heading',{name:'作者回复变化'})).toBeNull();
});
