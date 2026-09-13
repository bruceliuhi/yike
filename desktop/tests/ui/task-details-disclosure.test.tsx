// @vitest-environment jsdom
import {cleanup,render,screen} from '@testing-library/react';
import {afterEach,it,expect,vi} from 'vitest';
import {DesktopExecutionRequests} from '../../src/renderer/pages/tasks/DesktopExecutionRequests';
import {TaskConfirmationSummary} from '../../src/renderer/pages/tasks/TaskConfirmationSummary';
import {newTaskDraft} from '../../src/renderer/domain/models';
import {defaultResearchSettings} from '../../src/renderer/domain/researchUsage';
afterEach(cleanup);
it('describes confirmed limits in plain language without resource-internals teaching',()=>{
 const draft={...newTaskDraft(),research:{...defaultResearchSettings(),maxSoubei:30},
  executionLimits:{max_records:17,max_runtime_seconds:75}};
 render(<TaskConfirmationSummary draft={draft} usage={{estimatedSoubei:20,ruleVersion:'technical-rule-v1'} as any}
  connections={[]} deviceReady disabled={false} onEdit={vi.fn()}/>);
 expect(screen.queryByText('执行保护上限')).toBeNull();
 expect(screen.queryByText('停止条件')).toBeNull();
 expect(screen.queryByText(/模型调用达到任一上限|独立于搜贝/)).toBeNull();
 expect(screen.getByText('本次处理范围')).toBeTruthy();
 expect(screen.getByText('17 条记录 / 75 秒').closest('details')).toBeNull();
 expect(screen.getByText('达到本次上限即暂停，不会自动追加用量。').closest('details')).toBeNull();
 expect(screen.getByText('30 搜贝')).toBeTruthy();
 expect(screen.getByText('20 搜贝')).toBeTruthy();
});
it('requires returning to configure an unset range without presenting defaults as accepted',()=>{
 render(<TaskConfirmationSummary draft={newTaskDraft()} connections={[]} deviceReady disabled={false} onEdit={vi.fn()}/>);
 expect(screen.getByText('尚未设置，请返回配置设置后再启动。').closest('details')).toBeNull();
 expect(screen.queryByText(/建议100条|900秒/)).toBeNull();
 expect(screen.getByRole('button',{name:'修改配置'})).toBeTruthy();
});
it('collapses raw execution request identity without hiding UNKNOWN recovery',()=>{
 const execution={identity:{},loaded:true,busy:false,error:'',entries:[{requestId:'technical-request',operation:'START',state:'UNKNOWN'}],refresh:vi.fn()};
 render(<DesktopExecutionRequests execution={execution as any} canRetryStart={false} validateStart={vi.fn()}/>);
 const identity=screen.getByText('technical-request');
 expect(identity.closest('details')).not.toBeNull();
 expect(identity.closest('details')!.open).toBe(false);
 expect(screen.getByText(/原请求待核对/).closest('details')).toBeNull();
 expect(screen.getByRole('button',{name:'查询原执行请求'})).toBeTruthy();
});
it('keeps confirmation budgets in view and places billing rule versions in details',()=>{
 const draft={...newTaskDraft(),research:defaultResearchSettings()};
 render(<TaskConfirmationSummary draft={draft} usage={{estimatedSoubei:20,ruleVersion:'technical-rule-v1'} as any}
  connections={[]} deviceReady disabled={false} onEdit={vi.fn()}/>);
 const rule=screen.getByText(/technical-rule-v1/);
 expect(rule.closest('details')).not.toBeNull();
 expect(rule.closest('details')!.open).toBe(false);
 expect(screen.getByText('20 搜贝').closest('details')).toBeNull();
 expect(screen.getByText('搜贝上限').closest('details')).toBeNull();
 expect(screen.getByRole('button',{name:'修改配置'})).toBeTruthy();
});
