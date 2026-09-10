import {expect,it} from 'vitest';
import {portableBuildInput} from '../build/portableBuild';
import {mkdtempSync,writeFileSync,rmSync} from 'node:fs';
import path from 'node:path';
import {tmpdir} from 'node:os';
import {createHash} from 'node:crypto';
it('never requires a Windows payload for other platform builds',()=>{expect(portableBuildInput({},'darwin')).toBeNull();});
it('rejects missing or unbound Windows payloads',()=>{
  expect(()=>portableBuildInput({},'win32')).toThrow('PORTABLE_BUILD_INPUT_INVALID');
  expect(()=>portableBuildInput({YIKE_PORTABLE_BUNDLE_PATH:'C:\\payload'},'win32')).toThrow('PORTABLE_BUILD_INPUT_INVALID');
});
it('binds the exact clean manifest and resource name into a Windows build',()=>{
  const root=mkdtempSync(path.join(tmpdir(),'yike-portable-'));
  try {
    const raw=JSON.stringify({schema_version:'YIKE_WINDOWS_PORTABLE_BUNDLE_V1',source:{project_dirty:false}});
    writeFileSync(path.join(root,'bundle-manifest.json'),raw);
    const sha256=createHash('sha256').update(raw).digest('hex');
    expect(portableBuildInput({YIKE_PORTABLE_BUNDLE_PATH:root,YIKE_PORTABLE_BUNDLE_SHA256:sha256},'win32')).toEqual({source:root,pin:{sha256,resourceName:path.basename(root)}});
  }finally{rmSync(root,{recursive:true,force:true});}
});
