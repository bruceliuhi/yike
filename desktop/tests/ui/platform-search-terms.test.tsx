// @vitest-environment jsdom
import {afterEach,expect,it} from 'vitest';
import {cleanup} from '@testing-library/react';
import {newTaskDraft,type TaskDraft} from '../../src/renderer/domain/models';
import {makeTerm,taskErrors,taskFingerprint,applySuggestion} from '../../src/renderer/domain/task';
import {taskDraftSchema} from '../../src/renderer/app/taskDraft';
import {strategyPrepareRequest} from '../../src/renderer/domain/researchStrategies';
import {prepareStrategySchema,strategyConfigurationSchema} from '../../src/shared/researchStrategies';
import {templateFromDraft,draftFromTemplate} from '../../src/renderer/pages/tasks/localTemplates';

const id='11111111-1111-4111-8111-111111111111';
const limits={max_records:20,max_runtime_seconds:600};
function draft():TaskDraft {
  return {...newTaskDraft(),id,profileId:id,name:'平台查询',platforms:['xhs','bilibili'],
    terms:[makeTerm('展台搭建')],platformTerms:{xhs:[makeTerm('找搭建团队')],bilibili:[makeTerm('展台设计报价')]}} as TaskDraft;
}
afterEach(cleanup);

it('preserves independent platform terms when saving and adopting a new template draft',()=>{
  const initial=draft(),restored=draftFromTemplate(templateFromDraft(initial,'分平台词测试'));
  expect(restored.platformTerms).toEqual(initial.platformTerms);
  expect(restored.id).not.toBe(initial.id);
});

it('persists platform edits and binds exact distinct queries without rewriting old configuration',()=>{
  const value=draft();
  expect(taskDraftSchema.parse(JSON.parse(JSON.stringify(value)))).toHaveProperty('platformTerms',value.platformTerms);
  const request=strategyPrepareRequest(value,id,limits);
  expect(request.configuration).toHaveProperty('platformQueries',{version:'platform-queries-v1',items:[
    {platform:'XIAOHONGSHU',keywords:['找搭建团队']},{platform:'BILIBILI',keywords:['展台设计报价']}]});
  const legacy={...value};delete legacy.platformTerms;
  expect(strategyPrepareRequest(legacy,id,limits).configuration).not.toHaveProperty('platformQueries');
  expect(taskFingerprint(legacy)).not.toBe(taskFingerprint(value));
  const changed={...value,platformTerms:{...value.platformTerms,xhs:[makeTerm('有没有搭建公司')]}};
  expect(taskFingerprint(changed)).not.toBe(taskFingerprint(value));
  expect(applySuggestion(value,{profileId:id,requestId:id,keywords:['品牌展厅'],exclusions:[]},'replace_unedited').platformTerms)
    .toEqual(value.platformTerms);
});

it('rejects invalid platform scope, conflicting terms, and research or links modes',()=>{
  const value=draft(),request=strategyPrepareRequest(value,id,limits);
  for(const patch of [{platforms:['xhs']},{exclusions:[makeTerm('报价')]},{source:'links',links:'https://www.example.com/'},
    {research:{version:'research-settings-v1'}},{platformTerms:{xhs:[]}},{platformTerms:{web:[makeTerm('采购')]}}]) {
    const invalid={...value,...patch} as TaskDraft;
    expect(taskErrors(invalid)).toHaveProperty('platformTerms');
    expect(()=>strategyPrepareRequest(invalid,id,limits)).toThrow();
  }
  for(const items of [[{platform:'XIAOHONGSHU',keywords:[' 采购']}],[{platform:'XIAOHONGSHU',keywords:['甲,乙']}],
    [{platform:'XIAOHONGSHU',keywords:['同词','同词']}],[{platform:'PUBLIC_WEB',keywords:['采购']}],[],
    [{platform:'XIAOHONGSHU',keywords:['采购']},{platform:'XIAOHONGSHU',keywords:['定制']}]] )
    expect(strategyConfigurationSchema.safeParse({...request.configuration,platformQueries:{version:'platform-queries-v1',items}}).success).toBe(false);
  expect(strategyConfigurationSchema.safeParse({...request.configuration,platformQueries:null}).success).toBe(false);
  expect(prepareStrategySchema.safeParse({...request,platforms:['XIAOHONGSHU']}).success).toBe(false);
});
