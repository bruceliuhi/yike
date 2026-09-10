import {afterEach,expect,it} from 'vitest';
import {mkdtemp,writeFile,mkdir,rm,link,realpath} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {verifyPortablePayload} from '../src/main/portablePayload';
const roots:string[]=[];
afterEach(async()=>{for(const root of roots.splice(0))await rm(root,{recursive:true,force:true});});
async function fixture(){
  const root=await realpath(await mkdtemp(path.join(tmpdir(),'yike-payload-test-')));roots.push(root);
  const names=['host/python.exe','runtime/.venv/Scripts/python.exe','project/app/windows_portable_install.py',
    'project/app/windows_platform_outreach.py','project/app/platform_outreach_worker.py',
    'project/app/platform_outreach_runtime.py','project/app/xhs_comment_channel.py'];
  const bytes=Buffer.from('fixture');
  for(const name of names){await mkdir(path.dirname(path.join(root,name)),{recursive:true});await writeFile(path.join(root,name),bytes);}
  const manifest={schema_version:'YIKE_WINDOWS_PORTABLE_BUNDLE_V1',source:{project_dirty:false},
    entries:{host_python:'host/python.exe',project_root:'project',runtime_root:'runtime',runtime_python:'runtime/.venv/Scripts/python.exe'},
    probes:{host:{status:'PASSED'},runtime_cli:{status:'PASSED'},chromium:{status:'PASSED'}},
    files:names.map(name=>({path:name,size:bytes.length,sha256:createHash('sha256').update(bytes).digest('hex')}))};
  async function publish(){const data=JSON.stringify(manifest);await writeFile(path.join(root,'bundle-manifest.json'),data);return createHash('sha256').update(data).digest('hex');}
  return {root,manifest,publish,sha:await publish()};
}
it('verifies the complete bound payload without executing it',async()=>{const f=await fixture();await expect(verifyPortablePayload(f.root,f.sha)).resolves.toBeUndefined();});
it.each(['tamper','extra','hardlink','wrong-pin','escape','case-collision'])('rejects %s',async kind=>{
  const f=await fixture();let pin=f.sha;
  if(kind==='tamper')await writeFile(path.join(f.root,'host/python.exe'),'changed');
  if(kind==='extra')await writeFile(path.join(f.root,'extra.py'),'extra');
  if(kind==='hardlink')await link(path.join(f.root,'host/python.exe'),path.join(f.root,'link.exe'));
  if(kind==='wrong-pin')pin='0'.repeat(64);
  if(kind==='escape'){f.manifest.files[0].path='../outside';pin=await f.publish();}
  if(kind==='case-collision'){f.manifest.files.push({...f.manifest.files[0],path:'HOST/python.exe'});pin=await f.publish();}
  await expect(verifyPortablePayload(f.root,pin)).rejects.toThrow('PORTABLE_PAYLOAD_INVALID');
});
