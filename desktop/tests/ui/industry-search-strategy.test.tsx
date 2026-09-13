// @vitest-environment jsdom
import {afterEach,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {suggestionReceiptSchema,type SuggestionRequest} from '../../src/shared/searchSuggestions';
import {SearchSuggestionPanel} from '../../src/renderer/pages/tasks/SearchSuggestionPanel';
import {saveSearchSuggestion} from '../../src/renderer/pages/tasks/searchSuggestionStorage';
const uuid='11111111-1111-4111-8111-111111111111';
const scope={userId:'strategy-test',accountScopeId:'space',accountScopeVersion:1};
const request:SuggestionRequest={request_id:uuid,draft_id:uuid,profile_version_id:uuid,draft_revision:1,
  disclosure:{accepted:true,profile_sha256:'a'.repeat(64),model_provider:'controlled',model_name:'configured',policy_version:'profile-description-v1'}};
const strategy={version:'industry-search-strategy-v1',buyerRole:'制造企业',salesMotion:null,
  sourceTypes:['SOCIAL_POST','COMMENT'],intentSignals:['寻找设备改造供应商'],counterSignals:['设备厂商广告'],basis:['为制造企业提供产线改造']};
const receipt={request_id:uuid,draft_id:uuid,profile_version_id:uuid,draft_revision:1,profile_sha256:'a'.repeat(64),
  model_provider:'controlled',model_name:'configured',disclosure_policy_version:'profile-description-v1',rule_version:'search-suggestion-v1',
  profile_current:true,state:'SUCCEEDED',result:{keywords:['产线改造供应商'],exclusions:[],rationale:'围绕改造需求寻找表达',evidence:['产线改造'],unknowns:['销售方式未说明'],strategy},
  usage:null,error_code:null,created_at:'2026-09-11T00:00:00Z',updated_at:'2026-09-11T00:00:01Z'};
afterEach(()=>{cleanup();localStorage.clear();});
it('validates bounded strategy receipts without accepting execution permissions or breaking legacy results',()=>{
  expect(suggestionReceiptSchema.safeParse(receipt).success).toBe(true);
  for(const invalid of [{...strategy,autoSend:true},{...strategy,version:'other'},
      {...strategy,sourceTypes:['COMMENT','COMMENT']},{...strategy,intentSignals:['bad\0text']}])
    expect(suggestionReceiptSchema.safeParse({...receipt,result:{...receipt.result,strategy:invalid}}).success).toBe(false);
  const {strategy:omitted,...legacy}=receipt.result;
  expect(suggestionReceiptSchema.parse({...receipt,result:legacy}).result).not.toHaveProperty('strategy');
});
it('keeps proposed filters collapsed without publishing generated explanations or executing them',async()=>{
  saveSearchSuggestion({schemaVersion:1,scope,request,receipt:null});
  const service={preview:vi.fn(),submit:vi.fn(),getReceipt:vi.fn().mockResolvedValue(receipt)};
  const onApply=vi.fn(()=>true);
  render(<SearchSuggestionPanel service={service} scope={scope} draftId={uuid} draftRevision={1}
    profileVersionId={uuid} profileConfirmed hasTerms={false} onApply={onApply}/>);
  await screen.findByText('策略建议，尚未执行');
  expect(screen.getByText('制造企业')).toBeTruthy();
  expect(screen.getByText('画像未说明')).toBeTruthy();
  expect(screen.getByText('需求主帖')).toBeTruthy();expect(screen.getByText('讨论评论')).toBeTruthy();
  expect(screen.getByText('寻找设备改造供应商')).toBeTruthy();expect(screen.getByText('设备厂商广告')).toBeTruthy();
  expect(screen.queryByText('为制造企业提供产线改造')).toBeNull();
  expect(screen.queryByText(/策略版本：industry-search-strategy-v1/)).toBeNull();
  expect(screen.getByText('更多筛选条件').closest('details')!.open).toBe(false);
  expect(onApply).not.toHaveBeenCalled();expect(service.submit).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button',{name:'合并新增建议'}));
  await waitFor(()=>expect(onApply).toHaveBeenCalledWith(receipt,'append'));
  expect(service.submit).not.toHaveBeenCalled();
});
