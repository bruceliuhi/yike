import {expect,it} from 'vitest';
import {validatedExecutionOperation} from '../src/main/executionServicePolicy';
it('exposes only a fixed private read-only foreground support lookup',()=>{
 expect(validatedExecutionOperation({operation:'execution.support'})).toEqual({path:'/api/ui/execution-support',method:'GET',logout:false});
 expect(validatedExecutionOperation({operation:'execution.support',payload:{mode:'all'}})).toBeNull();
});
