import {webcrypto} from 'node:crypto';
import {it,expect,vi,beforeEach} from 'vitest';
import {createShortCoachService} from '../src/renderer/services/shortCoachClient';
import {coachInputHash} from '../src/shared/shortCoach';
import {textDigest,type CoachInput} from '../src/renderer/domain/shortCoach';
import {validatedOperation} from '../src/main/servicePolicy';

beforeEach(()=>vi.stubGlobal('crypto',webcrypto));
const uuid=(n:number)=>`00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
const scope={id:uuid(1),version:1},session=async()=>({authenticated:true,userId:uuid(2),accountScope:scope});
async function input():Promise<CoachInput>{return {binding:{accountScope:scope,requestId:uuid(3),opportunityId:uuid(4),
 profileVersionId:uuid(5),sourceEvidenceVersion:uuid(6),sourceUrl:'https://example.com/post',sourceObservedAt:'2026-09-11T00:00:00Z',
 channel:'dm',draftVersion:2,draftHash:await textDigest('现在还在找团队吗？'),purpose:'requirement'},
 content:'现在还在找团队吗？',sourceText:'需要😀知识库项目开发'};}
const candidate=(v:CoachInput)=>({suggestionId:uuid(7),binding:v.binding,content:'看到你在找知识库开发，现在还在选团队吗？',
 question:'现在还在选团队吗？',context:{summary:'需要知识库开发',quoteIds:['q1']},
 quotes:[{id:'q1',text:v.sourceText,start:0,end:v.sourceText.length,sourceUrl:v.binding.sourceUrl,sourceEvidenceVersion:v.binding.sourceEvidenceVersion}],
 checks:[{kind:'PROMISE',status:'NEEDS_REVIEW',message:'能力仍需核实',quoteIds:[]}],
 createdAt:new Date().toISOString(),expiresAt:new Date(Date.now()+60000).toISOString()});
it('previews exact input without generating and forwards accepted disclosure on fixed routes',async()=>{
 const v=await input(),preview={inputHash:await coachInputHash(v),modelProvider:'configured-provider',modelName:'configured-model',policyVersion:'short-coach-public-draft-v1' as const};
 const transport=vi.fn().mockResolvedValue(preview),api=createShortCoachService(transport,session);
 expect(await api.preview!(v)).toEqual(preview);expect(transport).toHaveBeenCalledTimes(1);
 expect(transport.mock.calls[0][0]).toBe('shortCoach.preview');
 const result=candidate(v);transport.mockResolvedValue(result);
 const accepted={...v,disclosure:{...preview,accepted:true as const}};
 expect(await api.generate(accepted)).toEqual(result);
 expect(transport.mock.calls[1][0]).toBe('shortCoach.generate');
 expect(validatedOperation({operation:'shortCoach.preview',payload:v})?.path).toBe('/api/ui/short-coach/preview');
 expect(validatedOperation({operation:'shortCoach.generate',payload:accepted})?.path).toBe('/api/ui/short-coach/generate');
 expect(validatedOperation({operation:'shortCoach.generate',payload:v})).toBeNull();
 expect(validatedOperation({operation:'shortCoach.preview',payload:{...v,baseUrl:'https://evil.test'}})).toBeNull();
});
it('does not dispatch unconfirmed, changed-body or mismatched preview requests',async()=>{
 const v=await input(),transport=vi.fn(),api=createShortCoachService(transport,session);
 await expect(api.generate(v)).rejects.toThrow();
 await expect(api.preview!({...v,content:'changed'})).rejects.toThrow();
 expect(transport).not.toHaveBeenCalled();
 transport.mockResolvedValue({inputHash:'a'.repeat(64),modelProvider:'configured',modelName:'model',policyVersion:'short-coach-public-draft-v1'});
 await expect(api.preview!(v)).rejects.toThrow();
});
it('rejects wrong source quotes, changed sessions and late cancellation',async()=>{
 const v=await input(),preview={inputHash:await coachInputHash(v),modelProvider:'configured',modelName:'model',policyVersion:'short-coach-public-draft-v1' as const};
 const transport=vi.fn().mockResolvedValue({...candidate(v),quotes:[{...candidate(v).quotes[0],end:4}]}),api=createShortCoachService(transport,session);
 await expect(api.generate({...v,disclosure:{accepted:true,...preview}})).rejects.toThrow();
 let current=await session();transport.mockImplementation(async()=>{current={...current,userId:uuid(9)};return preview;});
 await expect(createShortCoachService(transport,async()=>current).preview!(v)).rejects.toThrow();
 const abort=new AbortController();abort.abort();transport.mockClear();
 await expect(api.preview!(v,abort.signal)).rejects.toThrow();expect(transport).not.toHaveBeenCalled();
});
