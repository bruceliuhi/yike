import {configuredService} from '../src/main/serviceClient';

/** Public service origin only. Never embed runtime credentials in the client. */
export function releaseServiceBuildInput(env:NodeJS.ProcessEnv,required:boolean):string|null {
  const input=env.YIKE_RELEASE_SERVICE_URL;
  if(!input){
    if(required)throw new Error('RELEASE_SERVICE_URL_REQUIRED');
    return null;
  }
  const origin=configuredService(input,{packaged:true,allowLoopbackHttp:false});
  if(origin===null)throw new Error('RELEASE_SERVICE_URL_INVALID');
  return origin;
}
