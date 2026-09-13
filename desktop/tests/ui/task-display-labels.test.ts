import {expect,it} from 'vitest';
import {taskAccountLabel, scheduleRegionLabel} from '../../src/renderer/pages/tasks/taskDisplayLabels';
it('keeps account numbering consistent with all same-platform connections',()=>{
 const first={platform:'xhs',accountId:'internal-1',status:'UNAVAILABLE',capabilities:[]} as const;
 const second={...first,accountId:'internal-2',status:'CONNECTED'} as const;
 expect(taskAccountLabel(second as any,[first,second] as any)).toBe('小红书账号2');
 expect(taskAccountLabel({...second,accountName:'小王'} as any,[])).toBe('小王');
});
it('keeps regional schedule meaning without exposing IANA codes',()=>{
 expect(scheduleRegionLabel('Asia/Shanghai')).toBe('北京时间');
 expect(scheduleRegionLabel('America/New_York')).toBe('纽约时间');
 expect(scheduleRegionLabel('Europe/Berlin')).not.toMatch(/Europe\//);
});
