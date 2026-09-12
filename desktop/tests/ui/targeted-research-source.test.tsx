// @vitest-environment jsdom
import {cleanup,fireEvent,render,screen} from '@testing-library/react';
import {afterEach,expect,it,vi} from 'vitest';
import {PublicSourceSelector} from '../../src/renderer/pages/tasks/PublicSourceSelector';
import {newTaskDraft,type PlatformConnection} from '../../src/renderer/domain/models';
import {defaultResearchSettings} from '../../src/renderer/domain/researchUsage';

const catalog={contractVersion:2,sourceScope:'V2EX_SELECTED_INDEX',sourceLabel:'V2EX定向板块 · 单源索引研究',
  sourceIds:['v2ex-latest-v1','v2ex-qna-v1','v2ex-outsourcing-authors-v1'],maxFreshEffectsPerAdvance:1,settlementState:'PENDING'};
const connections:PlatformConnection[]=[{platform:'web',status:'CONNECTED',capabilities:['search'],
  publicBinding:{sourceId:'v2ex-latest-v1',sourceIds:['v2ex-latest-v1','v2ex-qna-v1','v2ex-outsourcing-authors-v1'],deviceId:'10000000-0000-4000-8000-000000000001'}}];
const draft=()=>({...newTaskDraft(),publicSource:'v2ex-qna-v1' as const,research:defaultResearchSettings()});
afterEach(cleanup);
it('offers only jointly supported research sources and explicitly describes unread context',()=>{
  const onChange=vi.fn();
  render(<PublicSourceSelector draft={draft()} connections={connections} onChange={onChange} researchCapability={catalog}/>);
  const select=screen.getByLabelText('公开来源板块') as HTMLSelectElement;
  expect(select.disabled).toBe(false);
  expect(select.value).toBe('v2ex-qna-v1');
  expect(screen.getAllByText(/单源索引研究（未读评论）/).length).toBeGreaterThan(0);
  fireEvent.change(select,{target:{value:'v2ex-outsourcing-authors-v1'}});
  expect(onChange).toHaveBeenCalledWith('v2ex-outsourcing-authors-v1');
});
it('preserves unavailable node selection on an old server, without silently switching',()=>{
  const onChange=vi.fn();
  const legacy={contractVersion:1,sourceScope:'V2EX_LATEST_INDEX',sourceLabel:'V2EX最新主题 · 公开单源研究',maxFreshEffectsPerAdvance:1,settlementState:'PENDING'};
  render(<PublicSourceSelector draft={draft()} connections={connections} onChange={onChange} researchCapability={legacy}/>);
  const select=screen.getByLabelText('公开来源板块') as HTMLSelectElement;
  expect(select.value).toBe('v2ex-qna-v1');
  expect([...select.options].find(option=>option.value==='v2ex-qna-v1')?.disabled).toBe(true);
  expect([...select.options].some(option=>option.value==='v2ex-outsourcing-authors-v1')).toBe(false);
  expect(onChange).not.toHaveBeenCalled();
});
it('does not offer a research source when execution binding omits it',()=>{
  render(<PublicSourceSelector draft={draft()} connections={[{...connections[0],publicBinding:{...connections[0].publicBinding!,sourceIds:['v2ex-latest-v1']}}]} onChange={vi.fn()} researchCapability={catalog}/>);
  const select=screen.getByLabelText('公开来源板块') as HTMLSelectElement;
  expect([...select.options].find(option=>option.value==='v2ex-qna-v1')?.disabled).toBe(true);
});
