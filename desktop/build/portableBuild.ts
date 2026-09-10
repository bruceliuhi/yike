import path from 'node:path';
import {readFileSync,lstatSync} from 'node:fs';
import {createHash} from 'node:crypto';
/** Build-only explicit input; these environment names are never read by packaged main. */
export function portableBuildInput(env:NodeJS.ProcessEnv,platform:string){
  if(platform!=='win32')return null;
  try {
    const root=env.YIKE_PORTABLE_BUNDLE_PATH,pin=env.YIKE_PORTABLE_BUNDLE_SHA256;
    if(!root||!path.isAbsolute(root)||!pin||!/^[a-f0-9]{64}$/.test(pin))throw Error();
    const name=path.basename(root);if(!/^[A-Za-z0-9_-]{1,100}$/.test(name))throw Error();
    const s=lstatSync(root);if(!s.isDirectory()||s.isSymbolicLink())throw Error();
    const file=path.join(root,'bundle-manifest.json'),stat=lstatSync(file);
    if(!stat.isFile()||stat.isSymbolicLink()||stat.nlink!==1||stat.size>16*1024*1024)throw Error();
    const bytes=readFileSync(file);
    if(createHash('sha256').update(bytes).digest('hex')!==pin)throw Error();
    const manifest=JSON.parse(bytes.toString('utf8'));
    if(manifest.schema_version!=='YIKE_WINDOWS_PORTABLE_BUNDLE_V1'||manifest.source?.project_dirty!==false)throw Error();
    return {source:root,pin:{sha256:pin,resourceName:name}};
  }catch{throw new Error('PORTABLE_BUILD_INPUT_INVALID');}
}
