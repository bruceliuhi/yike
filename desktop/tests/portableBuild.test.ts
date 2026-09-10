import {expect,it} from 'vitest';
import {portableBuildInput} from '../build/portableBuild';
it('never requires a Windows payload for other platform builds',()=>{expect(portableBuildInput({},'darwin')).toBeNull();});
it('rejects missing or unbound Windows payloads',()=>{
  expect(()=>portableBuildInput({},'win32')).toThrow('PORTABLE_BUILD_INPUT_INVALID');
  expect(()=>portableBuildInput({YIKE_PORTABLE_BUNDLE_PATH:'C:\\payload'},'win32')).toThrow('PORTABLE_BUILD_INPUT_INVALID');
});
