import path from 'node:path';
import type {PlatformLoginDriverOptions} from './platformLoginDriver';
/** Temporary developer wiring only. Customer packages require a separately verified bootstrap bundle. */
export function platformLoginConfiguration({env,packaged,platform,userData}:{env:NodeJS.ProcessEnv;packaged:boolean;platform:string;userData:string}):PlatformLoginDriverOptions|null {
  if(packaged || platform!=='win32')return null;
  const values=[env.YIKE_SOURCE_HOST_PYTHON,env.YIKE_SOURCE_PROJECT_ROOT,env.YIKE_SOURCE_RUNTIME_PATH,userData];
  // Accept native absolute paths as well as Windows absolute paths when this
  // Windows-only developer configuration is exercised from another host.
  if(values.some(v=>typeof v!=='string' || (!path.isAbsolute(v) && !path.win32.isAbsolute(v)) || /^\\\\/.test(v) || /[\p{C}]/u.test(v)))return null;
  return {pythonExecutable:values[0]!,projectRoot:values[1]!,runtimePath:values[2]!,
    profileRoot:path.join(userData,'platform-profiles'),outputRoot:path.join(userData,'platform-login-output')};
}
