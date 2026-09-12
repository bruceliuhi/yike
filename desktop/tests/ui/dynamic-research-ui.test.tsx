// @vitest-environment jsdom
import {afterEach,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {ResearchProgress} from '../../src/renderer/pages/tasks/ResearchProgress';
import {PublicSourceSelector} from '../../src/renderer/pages/tasks/PublicSourceSelector';
import {ResearchSettingsPanel} from '../../src/renderer/pages/tasks/ResearchSettings';
import {newTaskDraft} from '../../src/renderer/domain/models';
import {defaultResearchSettings} from '../../src/renderer/domain/researchUsage';
import {dynamicCapability,dynamicStatus} from '../fixtures/dynamicResearch';
import type {AppContextValue} from '../../src/renderer/app/context';
let context:AppContextValue;
vi.mock('../../src/renderer/app/context',()=>({useApp:()=>context}));
afterEach(cleanup);
it('shows author time window and shared source allowance before confirmation',()=>{
  const onChange=vi.fn(),value={...defaultResearchSettings(),dynamicScope:{version:1 as const,maxAgeDays:60,timezone:'Asia/Shanghai'}};
  render(<ResearchSettingsPanel value={value} onChange={onChange} quote={null} busy={false} error="" onEstimate={vi.fn()} onCancel={vi.fn()}/>);
  fireEvent.change(screen.getByRole('spinbutton',{name:'需求时间窗口（天）'}),{target:{value:'30'}});
  expect(onChange).toHaveBeenCalledWith({...value,dynamicScope:{...value.dynamicScope,maxAgeDays:30}});
  expect(screen.getByText(/搜索和读取共用来源上限/)).toBeTruthy();
  expect(screen.getByText(/最多20次模型调用/)).toBeTruthy();
});
it('offers dynamic server research without a fabricated local source binding',()=>{
  const onChange=vi.fn();
  render(<PublicSourceSelector draft={{...newTaskDraft(),platforms:['web'],research:defaultResearchSettings()}}
    connections={[]} researchCapability={dynamicCapability} onChange={onChange}/>);
  fireEvent.change(screen.getByRole('combobox',{name:'公开来源板块'}),{target:{value:'public-web-agent-v1'}});
  expect(onChange).toHaveBeenCalledWith('public-web-agent-v1');
});
it('starts once and polls existing background work; leaving stops observation, not the server',async()=>{
  const queued=dynamicStatus(),running={...queued,phase:'RUNNING',canAdvance:false,newActionsBlocked:true};
  const status=vi.fn().mockResolvedValue(running).mockResolvedValueOnce(queued).mockResolvedValueOnce(queued);
  const advance=vi.fn().mockResolvedValue(running);
  context={service:{researchRuntime:{status,advance}},session:{authenticated:true,userId:'test-user'},navigate:vi.fn()} as unknown as AppContextValue;
  const view=render(<ResearchProgress taskId={queued.taskId} runId={queued.runId} taskStatus="PENDING"/>);
  await screen.findByRole('button',{name:'开始研究'});
  fireEvent.click(screen.getByRole('button',{name:'开始研究'}));
  await screen.findByText(/离开页面不会停止服务端研究/);
  await waitFor(()=>expect(status.mock.calls.length).toBeGreaterThanOrEqual(3),{timeout:4000});
  expect(advance).toHaveBeenCalledTimes(1);
  expect(screen.queryByText(/暂未取得新进度/)).toBeNull();
  expect(screen.getByText(/搜索完成：0/)).toBeTruthy();
  expect(screen.queryByRole('button',{name:'停止本页推进'})).toBeNull();
  view.unmount();expect(advance).toHaveBeenCalledTimes(1);
});
