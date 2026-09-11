import {configuredService} from './serviceClient';

export function clientServiceConfiguration({packaged,bundled,env}:{
  packaged:boolean;bundled:string|null;env:NodeJS.ProcessEnv;
}):string|null {
  if(packaged)return configuredService(bundled??undefined,{packaged:true,allowLoopbackHttp:false});
  return configuredService(env.YIKE_SERVICE_URL,{packaged:false,allowLoopbackHttp:env.YIKE_ALLOW_LOOPBACK_HTTP==='1'});
}
