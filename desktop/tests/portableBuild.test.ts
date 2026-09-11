import {expect,it} from 'vitest';
import {portableBuildInput} from '../build/portableBuild';
import {mkdtempSync,writeFileSync,rmSync,mkdirSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import path from 'node:path';
import {tmpdir} from 'node:os';
import {createHash} from 'node:crypto';
it('never requires a Windows payload for other platform builds',()=>{expect(portableBuildInput({},'darwin')).toBeNull();});
it('rejects missing or unbound Windows payloads',()=>{
  expect(()=>portableBuildInput({},'win32')).toThrow('PORTABLE_BUILD_INPUT_INVALID');
  expect(()=>portableBuildInput({YIKE_PORTABLE_BUNDLE_PATH:'C:\\payload'},'win32')).toThrow('PORTABLE_BUILD_INPUT_INVALID');
});
function fixture(run:(f:{root:string;repo:string;commit:string;input:(sha?:string)=>NodeJS.ProcessEnv;git:(...args:string[])=>string})=>void){
  const root=mkdtempSync(path.join(tmpdir(),'yike-portable-'));
  try {
    const repo=path.join(root,'project');mkdirSync(repo);
    const git=(...args:string[])=>execFileSync('git',['-C',repo,...args],{encoding:'utf8',stdio:['ignore','pipe','pipe']}).trim();
    git('init');writeFileSync(path.join(repo,'source.txt'),'source');git('add','source.txt');
    git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','-c','commit.gpgsign=false','commit','-m','synthetic');
    const commit=git('rev-parse','HEAD');
    const input=(sha:string|undefined=commit)=>{
      const raw=JSON.stringify({schema_version:'YIKE_WINDOWS_PORTABLE_BUNDLE_V1',source:{project_dirty:false,project_commit:sha}});
      writeFileSync(path.join(root,'bundle-manifest.json'),raw);
      return {YIKE_PORTABLE_BUNDLE_PATH:root,YIKE_PORTABLE_BUNDLE_SHA256:createHash('sha256').update(raw).digest('hex')};
    };
    run({root,repo,commit,input,git});
  }finally{rmSync(root,{recursive:true,force:true});}
}
it('binds only the exact clean payload and Electron source commit',()=>fixture(({root,repo,input})=>{
  const env=input();
  expect(portableBuildInput(env,'win32',repo)).toEqual({source:root,pin:{sha256:env.YIKE_PORTABLE_BUNDLE_SHA256,resourceName:path.basename(root)}});
}));
it.each(['0'.repeat(40),'','not-a-commit'])('rejects an unbound payload commit %s',sha=>fixture(({repo,input})=>{
  expect(()=>portableBuildInput(input(sha),'win32',repo)).toThrow('PORTABLE_BUILD_INPUT_INVALID');
}));
it.each(['source.txt','untracked.txt'])('rejects dirty Electron source %s',name=>fixture(({repo,input})=>{
  const env=input();writeFileSync(path.join(repo,name),'local changes');
  expect(()=>portableBuildInput(env,'win32',repo)).toThrow('PORTABLE_BUILD_INPUT_INVALID');
}));
it('rejects a missing source checkout even with an otherwise pinned manifest',()=>fixture(({root,input})=>{
  expect(()=>portableBuildInput(input(),'win32',path.join(root,'missing'))).toThrow('PORTABLE_BUILD_INPUT_INVALID');
}));
