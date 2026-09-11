// @vitest-environment jsdom
import {afterEach,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {newTaskDraft,type TaskDraft} from '../../src/renderer/domain/models';
import {taskErrors,taskFingerprint} from '../../src/renderer/domain/task';
import {taskDraftSchema} from '../../src/renderer/app/taskDraft';
import {strategyPrepareRequest} from '../../src/renderer/domain/researchStrategies';
import {strategyConfigurationSchema} from '../../src/shared/researchStrategies';
import {SearchSuggestionPanel} from '../../src/renderer/pages/tasks/SearchSuggestionPanel';
import {StrategySnapshotDetails} from '../../src/renderer/pages/tasks/StrategySnapshotDetails';
import {saveSearchSuggestion} from '../../src/renderer/pages/tasks/searchSuggestionStorage';
import type {SuggestionReceipt,SuggestionRequest} from '../../src/shared/searchSuggestions';
import type {StrategyReceipt} from '../../src/shared/researchStrategies';
import {useState} from 'react';
import {IndustryTaskStrategyEditor} from '../../src/renderer/pages/tasks/IndustryTaskStrategyEditor';
import {adoptIndustryTaskStrategy} from '../../src/renderer/domain/industryTaskStrategy';

const id='11111111-1111-4111-8111-111111111111';
const other='22222222-2222-4222-8222-222222222222';
const config={version:'industry-task-strategy-v1' as const,sourceTypes:['COMMENT' as const],
  intentSignals:['正在选供应商'],counterSignals:['服务商广告']};
function draft():TaskDraft {
  return {...newTaskDraft(),id,profileId:id,name:'设备项目',
    terms:[{id:'term',value:'设备改造',origin:'manual',edited:true}],platforms:['bilibili'],
    industryStrategy:{profileId:id,configuration:structuredClone(config)}} as TaskDraft;
}
const limits={max_records:10,max_runtime_seconds:600};
afterEach(()=>{cleanup();localStorage.clear();});

it('persists final rules and binds them to the confirmation digest input without changing legacy shape',()=>{
  const value=draft();
  const restored=taskDraftSchema.parse(JSON.parse(JSON.stringify(value)));
  expect(restored).toHaveProperty('industryStrategy.configuration',config);
  const request=strategyPrepareRequest(value,id,limits);
  expect(request.configuration).toHaveProperty('industryStrategy',config);
  expect(request.platforms).toEqual(['BILIBILI']);
  const legacy={...value};delete (legacy as any).industryStrategy;
  expect(strategyPrepareRequest(legacy,id,limits).configuration).not.toHaveProperty('industryStrategy');
  expect(taskFingerprint(legacy)).not.toBe(taskFingerprint(value));
  const edited=structuredClone(value);(edited as any).industryStrategy.configuration.intentSignals=['询问实施周期'];
  expect(taskFingerprint(edited)).not.toBe(taskFingerprint(value));
  for(const bad of [null,{...config,autoSend:true},{...config,intentSignals:['重复',' 重复 ']}])
    expect(strategyConfigurationSchema.safeParse({...request.configuration,industryStrategy:bad}).success).toBe(false);
});

it('blocks a previous profile strategy until it is explicitly rebound and blocks invalid edits',()=>{
  const value={...draft(),profileId:other};
  expect(taskErrors(value)).toHaveProperty('industryStrategy');
  expect(()=>strategyPrepareRequest(value,id,limits)).toThrow();
  const invalid=draft();(invalid as any).industryStrategy.configuration.intentSignals=[''];
  expect(taskDraftSchema.safeParse(invalid).success).toBe(true); // preserve unfinished local edits
  expect(taskErrors(invalid)).toHaveProperty('industryStrategy');
  expect(()=>strategyPrepareRequest(invalid,id,limits)).toThrow();
});

it('displays the final server snapshot rules without claiming automatic scoring',()=>{
  const request=strategyPrepareRequest(draft(),id,limits);
  render(<StrategySnapshotDetails receipt={{draft_id:id,draft_revision:1,profile_sha256:'a'.repeat(64),
    configuration_sha256:'b'.repeat(64),request_id:id,state:'DRAFT',recorded_at:'2026-09-11T00:00:00Z',
    snapshot:{...request,configuration:{...request.configuration,industryStrategy:config},strategy_version_id:id}} as unknown as StrategyReceipt}/>);
  expect(screen.getByText('正在选供应商')).toBeTruthy();
  expect(screen.getByText(/尚未用于自动评分或内容筛选/)).toBeTruthy();
});

it('rechecks the original receipt before separately adopting strategy and keeps keyword adoption available',async()=>{
  const scope={userId:'industry-task-test',accountScopeId:'space',accountScopeVersion:1};
  const request:SuggestionRequest={request_id:id,draft_id:id,profile_version_id:id,draft_revision:1,
    disclosure:{accepted:true,profile_sha256:'a'.repeat(64),model_provider:'controlled',model_name:'configured',policy_version:'profile-description-v1'}};
  const receipt:SuggestionReceipt={request_id:id,draft_id:id,profile_version_id:id,draft_revision:1,
    profile_sha256:'a'.repeat(64),model_provider:'controlled',model_name:'configured',disclosure_policy_version:'profile-description-v1',
    profile_current:true,rule_version:'search-suggestion-v1',state:'SUCCEEDED',result:{keywords:['设备改造'],exclusions:[],
      rationale:'研究企业采购',evidence:['设备'],unknowns:[],strategy:{...config,version:'industry-search-strategy-v1',buyerRole:null,salesMotion:null,basis:['设备']}},
    usage:null,error_code:null,created_at:'2026-09-11T00:00:00Z',updated_at:'2026-09-11T00:00:01Z'};
  saveSearchSuggestion({schemaVersion:1,scope,request,receipt:null});
  const service={preview:vi.fn(),submit:vi.fn(),getReceipt:vi.fn().mockResolvedValue(receipt)};
  const onApply=vi.fn(()=>true),onApplyStrategy=vi.fn(()=>true);
  render(<SearchSuggestionPanel {...{service,scope,draftId:id,draftRevision:1,profileVersionId:id,
    profileConfirmed:true,hasTerms:true,onApply,onApplyStrategy}}/>);
  fireEvent.click(await screen.findByRole('button',{name:'采用任务策略'}));
  await waitFor(()=>expect(onApplyStrategy).toHaveBeenCalledWith(receipt));
  expect(service.getReceipt).toHaveBeenCalledTimes(2);
  expect(onApply).not.toHaveBeenCalled();expect(service.submit).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button',{name:'合并新增建议'}));
  await waitFor(()=>expect(onApply).toHaveBeenCalledWith(receipt,'append'));
  const initial=draft();delete initial.industryStrategy;
  const adopted=adoptIndustryTaskStrategy(initial,receipt);
  expect(adopted.industryStrategy?.configuration).toEqual(config);
  expect(adopted.terms).toEqual(initial.terms);expect(adopted.platforms).toEqual(initial.platforms);
  expect(adopted.research).toEqual(initial.research);
  const edited=structuredClone(adopted);edited.industryStrategy!.configuration.intentSignals=['人工保留'];
  expect(adoptIndustryTaskStrategy(edited,receipt)).toBe(edited);
  expect(adoptIndustryTaskStrategy({...initial,profileId:other},receipt).industryStrategy).toBeUndefined();
});

it('edits and preserves unfinished local rules, explicitly rebinds profile and removes them',()=>{
  function Harness(){const [value,setValue]=useState<TaskDraft['industryStrategy']>(draft().industryStrategy);
    return <><IndustryTaskStrategyEditor value={value} profileId={other} onChange={setValue}/>
      <output data-testid="current">{JSON.stringify(value??null)}</output></>;}
  render(<Harness/>);
  fireEvent.change(screen.getByLabelText('任务购买信号'),{target:{value:'人工信号\n'}});
  expect(JSON.parse(screen.getByTestId('current').textContent!).configuration.intentSignals).toEqual(['人工信号','']);
  fireEvent.click(screen.getByRole('button',{name:'按当前画像确认'}));
  expect(JSON.parse(screen.getByTestId('current').textContent!).profileId).toBe(other);
  fireEvent.change(screen.getByLabelText('任务购买信号'),{target:{value:'人工信号'}});
  fireEvent.click(screen.getByLabelText('讨论评论'));
  expect(JSON.parse(screen.getByTestId('current').textContent!).configuration.sourceTypes).toEqual([]);
  fireEvent.click(screen.getByRole('button',{name:'移除本任务策略'}));
  expect(screen.getByTestId('current').textContent).toBe('null');
  fireEvent.click(screen.getByRole('button',{name:'手动设置行业策略'}));
  expect(JSON.parse(screen.getByTestId('current').textContent!).profileId).toBe(other);
});
