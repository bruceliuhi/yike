// @vitest-environment jsdom
import {webcrypto} from 'node:crypto';
import {useState} from 'react';
import {cleanup,fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import type {AppContextValue} from '../../src/renderer/app/context';
import type {ContactDraft} from '../../src/renderer/domain/models';
import {makeCoachInput,readCoachSuggestion,type CoachInput} from '../../src/renderer/domain/shortCoach';
import {coachInputHash,coachInputSchema} from '../../src/shared/shortCoach';
import {createShortCoachService} from '../../src/renderer/services/shortCoachClient';
import {ShortCoachPanel} from '../../src/renderer/pages/outreach/ShortCoachPanel';
import {ContactEditor} from '../../src/renderer/pages/outreach/ContactEditor';
import {clearLocalDrafts} from '../../src/renderer/app/hooks';
import {parseRoute} from '../../src/renderer/domain/routes';
import {PUBLIC_SAMPLE} from '../../src/renderer/pages/Opportunities';
let context:AppContextValue;
vi.mock('../../src/renderer/app/context',()=>({useApp:()=>context}));
const uuid=(n:number)=>`00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
const ref={sourceProfileVersionId:uuid(5),materialId:'m1',materialVersion:3,extractionId:'e1',quote:'支持私有部署和权限管理'};
const row={...PUBLIC_SAMPLE,id:uuid(1),sample:false,profileStatus:'CONFIRMED',sourceStatus:'OPEN',
 profileVersionId:uuid(2),sourceEvidenceVersion:uuid(3),sourceObservedAt:'2026-09-11T00:00:00Z',excerpt:'想找做企业知识库的团队。'};
const scope={id:uuid(4),version:1};
const draft:ContactDraft={opportunityId:row.id,channel:'dm',version:2,content:`我们${ref.quote}，资料多吗？`,savedContent:'',recipient:'',accountId:'',materialReferences:[ref]};
const preview=async(v:CoachInput)=>({inputHash:await coachInputHash(v),modelProvider:'configured',modelName:'model',policyVersion:'short-coach-material-draft-v1' as const});
function result(v:CoachInput){return {suggestionId:uuid(8),binding:v.binding,content:'支持私有部署，你们资料多吗？',question:'你们资料多吗？',
 materialReferences:[{...ref,quote:'支持私有部署'}],context:{summary:'依据公开原文与选定资料',quoteIds:['q']},
 quotes:[{id:'q',text:v.sourceText,start:0,end:v.sourceText.length,sourceUrl:v.binding.sourceUrl,sourceEvidenceVersion:v.binding.sourceEvidenceVersion}],
 checks:[],createdAt:new Date().toISOString(),expiresAt:new Date(Date.now()+60000).toISOString()};}
const input=()=>makeCoachInput(row,draft,'requirement',uuid(7),scope);
beforeEach(()=>{vi.stubGlobal('crypto',webcrypto);localStorage.clear();sessionStorage.clear();clearLocalDrafts();context={session:{authenticated:true,userId:uuid(9),accountScope:scope},
 service:{shortCoach:{preview:vi.fn(preview),generate:vi.fn(async(v)=>result(v))},opportunity:vi.fn(async()=>row)},
 } as unknown as AppContextValue;});
afterEach(()=>{cleanup();vi.restoreAllMocks();});

it('carries canonical references, binds consent hash and rejects invalid output provenance',async()=>{
 const v=await input();expect(v.materialReferences).toEqual([ref]);
 const legacy={...v};delete legacy.materialReferences;
 expect(await coachInputHash(v)).not.toBe(await coachInputHash(legacy));
 expect(await coachInputHash({...legacy,materialReferences:[]})).not.toBe(await coachInputHash(legacy));
 const reversed={quote:ref.quote,extractionId:ref.extractionId,materialVersion:ref.materialVersion,materialId:ref.materialId,sourceProfileVersionId:ref.sourceProfileVersionId};
 expect(await coachInputHash({...v,materialReferences:[reversed]})).toBe(await coachInputHash(v));
 expect(coachInputSchema.safeParse({...v,materialReferences:null}).success).toBe(false);
 expect(coachInputSchema.safeParse({...v,materialReferences:[{...ref,quote:'正文未选用'}]}).success).toBe(false);
 expect(readCoachSuggestion(result(v),v).materialReferences?.[0].quote).toBe('支持私有部署');
 for(const refs of [undefined,[],[{...ref,materialVersion:4,quote:'支持私有部署'}],[{...ref,quote:'凭空承诺'}]]){
  expect(()=>readCoachSuggestion({...result(v),materialReferences:refs},v)).toThrow();
 }
 expect(()=>readCoachSuggestion(result(v),legacy)).toThrow();
});
it('enforces material policy in the actual service before model dispatch',async()=>{
 const v=await input(),p=await preview(v),transport=vi.fn(async()=>p);
 const api=createShortCoachService(transport,async()=>context.session);
 expect(await api.preview!(v)).toEqual(p);
 transport.mockResolvedValue({...p,policyVersion:'short-coach-public-draft-v1'} as never);
 await expect(api.preview!(v)).rejects.toThrow();
 transport.mockClear();
 await expect(api.generate({...v,disclosure:{...p,policyVersion:'short-coach-public-draft-v1',accepted:true}})).rejects.toThrow();
 expect(transport).not.toHaveBeenCalled();
});
function Harness(){const [current,setCurrent]=useState(draft);return <>
 <output data-testid="draft">{JSON.stringify(current)}</output>
 <button onClick={()=>setCurrent(v=>({...v,materialReferences:[{...ref,materialVersion:4}]}))}>改变资料绑定</button>
 <button onClick={()=>setCurrent(v=>({...v,content:'人工改写',version:v.version+1}))}>人工编辑</button>
 <ShortCoachPanel row={row} draft={current} purpose="requirement" onApply={(content,materialReferences)=>setCurrent(v=>({...v,content,materialReferences,version:v.version+1}))}/>
 </>;}
async function openPreview(){render(<Harness/>);fireEvent.click(screen.getByRole('button',{name:'生成短句建议'}));return screen.findByRole('dialog',{name:'确认模型生成'});}
async function ready(){const dialog=await openPreview();fireEvent.click(within(dialog).getByRole('button',{name:'确认并生成'}));return screen.findByRole('dialog',{name:'短句建议与当前草稿'});}
it('discloses selected excerpts, requalifies and adopts shortened reference with content',async()=>{
 const dialog=await openPreview();expect(within(dialog).getByText(ref.quote)).toBeTruthy();
 expect(context.service.shortCoach!.generate).not.toHaveBeenCalled();
 fireEvent.click(within(dialog).getByRole('button',{name:'确认并生成'}));
 const compare=await screen.findByRole('dialog',{name:'短句建议与当前草稿'});
 expect(within(compare).getByText('支持私有部署')).toBeTruthy();
 fireEvent.click(within(compare).getByRole('button',{name:'核对并替换当前草稿'}));
 await waitFor(()=>expect(JSON.parse(screen.getByTestId('draft').textContent!).materialReferences).toEqual([{...ref,quote:'支持私有部署'}]));
 expect(context.service.shortCoach!.preview).toHaveBeenCalledTimes(2);
 expect(context.service.shortCoach!.generate).toHaveBeenCalledOnce();
});
it('requires renewed disclosure when material binding changes without content/version change',async()=>{
 const dialog=await openPreview();fireEvent.click(screen.getByRole('button',{name:'改变资料绑定'}));
 fireEvent.click(within(dialog).getByRole('button',{name:'确认并生成'}));
 await screen.findByText(/草稿已变化，请重新预览/);
 expect(context.service.shortCoach!.generate).not.toHaveBeenCalled();
});
it('preserves draft when material requalification fails and when user edits during qualification',async()=>{
 let dialog=await ready();vi.mocked(context.service.shortCoach!.preview!).mockRejectedValueOnce(new Error('资料已撤销'));
 fireEvent.click(within(dialog).getByRole('button',{name:'核对并替换当前草稿'}));
 await screen.findByText('资料已撤销');expect(JSON.parse(screen.getByTestId('draft').textContent!).content).toBe(draft.content);
 let resolve!:(v:Awaited<ReturnType<typeof preview>>)=>void;
 vi.mocked(context.service.shortCoach!.preview!).mockImplementationOnce(()=>new Promise(done=>{resolve=done;}));
 fireEvent.click(within(dialog).getByRole('button',{name:'核对并替换当前草稿'}));
 await waitFor(()=>expect(resolve).toBeTypeOf('function'));
 fireEvent.click(screen.getByRole('button',{name:'人工编辑'}));
 resolve(await preview(vi.mocked(context.service.shortCoach!.preview!).mock.calls[0][0]));
 await screen.findByText(/核对期间你又修改了草稿/);
 expect(JSON.parse(screen.getByTestId('draft').textContent!).content).toBe('人工改写');
});
it('saves the actually used shortened quote through the ordinary contact editor',async()=>{
 const source={id:ref.materialId,profileVersionId:row.profileVersionId,version:ref.materialVersion,name:'产品资料',text:ref.quote,
  purpose:'产品介绍',visibility:'external',status:'READY',updatedAt:'2026-09-11T00:00:00Z',
  extraction:{id:ref.extractionId,materialVersion:ref.materialVersion,fields:{service:ref.quote},evidence:[{field:'service',quote:ref.quote}]}};
 context.service.connections=vi.fn(async()=>[]);
 context.service.materials={list:vi.fn(async()=>[source])} as never;
 context.service.contactDrafts={latest:vi.fn(async()=>null),operation:vi.fn(),save:vi.fn(async(v)=>({binding:v.binding,status:'SUCCEEDED' as const,confirmed:true,
  snapshot:{...v.snapshot,draft:{...v.snapshot.draft,savedContent:v.snapshot.draft.content}}}))};
 context.service.shortCoach!.generate=vi.fn(async v=>({...result(v),materialReferences:[{...v.materialReferences![0],quote:'支持私有部署'}]}));
 context.notify=vi.fn();
 context.route=parseRoute('#/outreach?opportunity='+row.id);
 render(<ContactEditor row={row} renderConfirmation={()=>null}/>);
 fireEvent.click(await screen.findByRole('button',{name:'带入资料片段'}));
 fireEvent.click(screen.getByRole('button',{name:'生成短句建议'}));
 let dialog=await screen.findByRole('dialog',{name:'确认模型生成'});
 fireEvent.click(within(dialog).getByRole('button',{name:'确认并生成'}));
 dialog=await screen.findByRole('dialog',{name:'短句建议与当前草稿'});
 fireEvent.click(within(dialog).getByRole('button',{name:'核对并替换当前草稿'}));
 await waitFor(()=>expect(screen.queryByRole('dialog',{name:'短句建议与当前草稿'})).toBeNull());
 fireEvent.click(screen.getByRole('button',{name:'保存草稿'}));
 await waitFor(()=>expect(context.service.contactDrafts!.save).toHaveBeenCalledOnce());
 const saved=vi.mocked(context.service.contactDrafts!.save).mock.calls[0][0].snapshot.draft;
 expect(saved.content).toBe('支持私有部署，你们资料多吗？');
 expect(saved.materialReferences).toEqual([{...ref,sourceProfileVersionId:row.profileVersionId,quote:'支持私有部署'}]);
});
