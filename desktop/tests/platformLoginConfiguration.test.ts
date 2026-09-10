import {expect,it} from 'vitest';
import path from 'node:path';
import {platformLoginConfiguration} from '../src/main/platformLoginConfiguration';
const env={YIKE_SOURCE_HOST_PYTHON:path.resolve('python.exe'),YIKE_SOURCE_PROJECT_ROOT:path.resolve('project'),YIKE_SOURCE_RUNTIME_PATH:path.resolve('runtime')};
const input={env,packaged:false,platform:'win32',userData:path.resolve('data')};
it('only accepts explicit main-owned absolute development paths on Windows',()=>{
 expect(platformLoginConfiguration(input)).toEqual({pythonExecutable:env.YIKE_SOURCE_HOST_PYTHON,projectRoot:env.YIKE_SOURCE_PROJECT_ROOT,runtimePath:env.YIKE_SOURCE_RUNTIME_PATH,
  profileRoot:path.join(input.userData,'platform-profiles'),outputRoot:path.join(input.userData,'platform-login-output')});
 for(const change of [{packaged:true},{platform:'darwin'},{env:{}},{env:{...env,YIKE_SOURCE_HOST_PYTHON:'python.exe'}},{env:{...env,YIKE_SOURCE_PROJECT_ROOT:'relative'}},{env:{...env,YIKE_SOURCE_RUNTIME_PATH:'\\\\server\\share'}}])expect(platformLoginConfiguration({...input,...change})).toBeNull();
});
