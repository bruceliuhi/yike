import { describe, expect, it, vi } from 'vitest';
import { validatedOperation } from '../src/main/servicePolicy';
import { createSearchSuggestionsService } from '../src/renderer/services/searchSuggestions';
import { suggestionRequestSchema, type SuggestionRequest } from '../src/shared/searchSuggestions';

const id = '11111111-1111-4111-8111-111111111111';
const profile = '22222222-2222-4222-8222-222222222222';
const request: SuggestionRequest = {
  request_id:id, draft_id:'33333333-3333-4333-8333-333333333333', profile_version_id:profile, draft_revision:4,
  disclosure:{accepted:true,profile_sha256:'a'.repeat(64),model_provider:'openai-compatible',model_name:'synthetic-v1',policy_version:'profile-description-v1'},
};
const preview = {profile_version_id:profile,profile_sha256:'a'.repeat(64),description:'制造企业自动化',
  model_provider:'openai-compatible',model_name:'synthetic-v1',disclosure_policy_version:'profile-description-v1'};
function receipt() { return {request_id:id,draft_id:request.draft_id,draft_revision:4,profile_version_id:profile,
  profile_sha256:'a'.repeat(64),model_provider:'openai-compatible',model_name:'synthetic-v1',
  disclosure_policy_version:'profile-description-v1',rule_version:'search-suggestion-v1',profile_current:true,
  state:'SUCCEEDED',result:{keywords:['工厂自动化'],exclusions:['招聘'],rationale:'寻找项目需求',evidence:['制造企业'],unknowns:['预算待确认']},
  usage:null,error_code:null,created_at:'2026-09-11T00:00:00+00:00',updated_at:'2026-09-11T00:00:01+00:00'}; }

describe('governed suggestion transport',()=>{
  it('only uses fixed preview, submit and original receipt paths',async()=>{
    const transport=vi.fn().mockResolvedValueOnce(preview).mockResolvedValueOnce(receipt()).mockResolvedValueOnce(receipt());
    const service=createSearchSuggestionsService(transport);
    await service.preview(profile); await service.submit(request); await service.getReceipt(request);
    expect(transport.mock.calls.map(call=>[call[0],call[1],call[2]])).toEqual([
      ['suggestions.preview',`/search-suggestions/preview?profileVersionId=${profile}`,'GET'],
      ['suggestions.submit','/search-suggestions','POST'],
      ['suggestions.receipt',`/search-suggestions/${id}`,'GET'],
    ]);
    const operation=validatedOperation({operation:'suggestions.submit',payload:request});
    expect(operation?.path).toBe('/api/ui/search-suggestions');
    expect(JSON.parse(operation!.body!)).toEqual(request);
    expect(validatedOperation({operation:'suggestions.preview',payload:{profile_version_id:profile}})?.path)
      .toBe(`/api/ui/search-suggestions/preview?profileVersionId=${profile}`);
    expect(validatedOperation({operation:'suggestions.receipt',payload:{request_id:id}})?.method).toBe('GET');
  });
  it.each(['request_id','draft_id','profile_version_id','draft_revision','profile_sha256','model_name','model_provider','disclosure_policy_version'])(
    'rejects mismatched %s',async(field)=>{
      const wrong={...receipt(),[field]:field==='draft_revision'?5:field==='profile_sha256'?'b'.repeat(64):field.endsWith('_id')?'44444444-4444-4444-8444-444444444444':'different'};
      await expect(createSearchSuggestionsService(vi.fn().mockResolvedValue(wrong)).getReceipt(request)).rejects.toThrow();
    });
  it('keeps a past profile receipt readable but explicitly not current',async()=>{
    const result=await createSearchSuggestionsService(vi.fn().mockResolvedValue({...receipt(),profile_current:false})).getReceipt(request);
    expect(result.profile_current).toBe(false);
  });
  it('accepts only a bound non-admission fact, without model result or usage',async()=>{
    const denied={...receipt(),state:'NOT_SUBMITTED',profile_current:false,result:null,usage:null,error_code:'suggestion_quota_exceeded'};
    const service=createSearchSuggestionsService(vi.fn().mockResolvedValue(denied));
    expect((await service.getReceipt(request)).state).toBe('NOT_SUBMITTED');
    for(const invalid of [{...denied,request_id:request.draft_id},{...denied,result:receipt().result},
      {...denied,profile_current:true},{...denied,error_code:'suggestion_result_unknown'},
      {...denied,state:'FAILED'}])
      await expect(createSearchSuggestionsService(vi.fn().mockResolvedValue(invalid)).getReceipt(request)).rejects.toThrow();
  });
  it('forwards read cancellation and does not dispatch an already cancelled submit',async()=>{
    const transport=vi.fn().mockResolvedValue(receipt()); const service=createSearchSuggestionsService(transport);
    const abort=new AbortController();
    await service.getReceipt(request,abort.signal);
    expect(transport.mock.calls[0][4]).toBe(abort.signal);
    abort.abort();
    await expect(service.submit(request,abort.signal)).rejects.toThrow();
    expect(transport).toHaveBeenCalledTimes(1);
  });
  it('rejects wrong preview profile and impossible success state',async()=>{
    await expect(createSearchSuggestionsService(vi.fn().mockResolvedValue({...preview,profile_version_id:id})).preview(profile)).rejects.toThrow();
    await expect(createSearchSuggestionsService(vi.fn().mockResolvedValue({...receipt(),result:null})).submit(request)).rejects.toThrow();
    await expect(createSearchSuggestionsService(vi.fn().mockResolvedValue({...receipt(),state:'UNKNOWN'})).getReceipt(request)).rejects.toThrow();
  });
  it('denies missing consent, caller-supplied targets, noncanonical IDs and extra fields before dispatch',async()=>{
    const transport=vi.fn(); const service=createSearchSuggestionsService(transport);
    for(const input of [{...request,disclosure:{...request.disclosure,accepted:false}}, {...request,tenant_id:'other'},
      {...request,request_id:id.toUpperCase().replace('1111','AAAA')}, {...request,disclosure:{...request.disclosure,url:'https://arbitrary.example'}}]){
      expect(suggestionRequestSchema.safeParse(input).success).toBe(false);
      expect(validatedOperation({operation:'suggestions.submit',payload:input})).toBeNull();
      await expect(service.submit(input as SuggestionRequest)).rejects.toThrow();
    }
    expect(transport).not.toHaveBeenCalled();
  });
});
