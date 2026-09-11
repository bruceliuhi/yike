// @vitest-environment jsdom
import {afterEach,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen} from '@testing-library/react';
import {newTaskDraft,type PlatformConnection} from '../../src/renderer/domain/models';
import {TaskConfirmationSummary} from '../../src/renderer/pages/tasks/TaskConfirmationSummary';
const module=await import('../../src/renderer/pages/tasks/PublicSourceSelector').catch(()=>null);
const id='11111111-1111-4111-8111-111111111111';
const row:PlatformConnection={platform:'web',status:'CONNECTED',capabilities:['search'],
 publicBinding:{sourceId:'v2ex-latest-v1',deviceId:id,sourceIds:['v2ex-latest-v1','v2ex-qna-v1']}};
afterEach(cleanup);
it('offers only service-authorized sources and preserves an unavailable saved selection',()=>{
 expect(module?.PublicSourceSelector).toBeTypeOf('function');
 const Component=module!.PublicSourceSelector,onChange=vi.fn();
 const draft={...newTaskDraft(),platforms:['web' as const]};
 const view=render(<Component draft={draft} connections={[row]} onChange={onChange}/>);
 fireEvent.change(screen.getByRole('combobox',{name:'公开来源板块'}),{target:{value:'v2ex-qna-v1'}});
 expect(onChange).toHaveBeenCalledWith('v2ex-qna-v1');
 view.rerender(<Component draft={{...draft,publicSource:'v2ex-qna-v1'}} connections={[{...row,publicBinding:{sourceId:'v2ex-latest-v1',deviceId:id}}]} onChange={onChange}/>);
 expect(screen.getByRole('combobox')).toHaveProperty('value','v2ex-qna-v1');
 expect(screen.getByRole('option',{name:'V2EX问与答（当前不可用）'})).toHaveProperty('disabled',true);
 expect(onChange).toHaveBeenCalledTimes(1);
 view.rerender(<Component draft={draft} connections={[{...row,publicBinding:{sourceId:'v2ex-latest-v1',deviceId:id}}]} onChange={onChange}/>);
 expect(screen.queryByRole('option',{name:'V2EX问与答'})).toBeNull();
});
it('shows the chosen source and its actual capability in the final summary',()=>{
 const draft={...newTaskDraft(),platforms:['web' as const],publicSource:'v2ex-qna-v1' as const};
 const view=render(<TaskConfirmationSummary draft={draft} connections={[row]} deviceReady disabled={false} onEdit={()=>{}}/>);
 expect(screen.getByText('公开读取可用')).toBeTruthy();
 expect(screen.getByText(/V2EX问与答/)).toBeTruthy();
 view.rerender(<TaskConfirmationSummary draft={draft} connections={[{...row,publicBinding:{sourceId:'v2ex-latest-v1',deviceId:id}}]} deviceReady disabled={false} onEdit={()=>{}}/>);
 expect(screen.getByText('范围待确认')).toBeTruthy();
});
