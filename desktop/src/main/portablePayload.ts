import path from 'node:path';
import {lstat,open,readdir} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {z} from 'zod';

const hash=z.string().regex(/^[a-f0-9]{64}$/);
const manifestSchema=z.object({schema_version:z.literal('YIKE_WINDOWS_PORTABLE_BUNDLE_V1'),
  source:z.object({project_dirty:z.literal(false)}),
  entries:z.object({host_python:z.literal('host/python.exe'),project_root:z.literal('project'),
    runtime_root:z.literal('runtime'),runtime_python:z.literal('runtime/.venv/Scripts/python.exe')}).strict(),
  probes:z.object({host:z.object({status:z.literal('PASSED')}),runtime_cli:z.object({status:z.literal('PASSED')}),chromium:z.object({status:z.literal('PASSED')})}),
  files:z.array(z.object({path:z.string(),size:z.number().int().min(0).max(512*1024*1024),sha256:hash}).strict()).min(1).max(50000)});
const required=['host/python.exe','runtime/.venv/Scripts/python.exe','project/app/windows_portable_install.py',
  'project/app/windows_platform_outreach.py','project/app/platform_outreach_worker.py',
  'project/app/platform_outreach_runtime.py','project/app/xhs_comment_channel.py'];
function fail():never {throw new Error('PORTABLE_PAYLOAD_INVALID');}
function relative(value:string){
  if(!value || value==='bundle-manifest.json' || value.split('/').some(part=>!part||part==='.'||part==='..'||
    /[\p{C}<>:"\\|?*]/u.test(part)||/[ .]$/.test(part)||/^(con|prn|aux|nul|com[1-9]|lpt[1-9])(\.|$)/i.test(part)))fail();
  return value;
}
async function regular(file:string){const s=await lstat(file);if(!s.isFile()||s.isSymbolicLink()||s.nlink!==1)fail();return s;}
async function bytes(file:string,limit:number){
  const before=await regular(file);if(before.size>limit)fail();
  const handle=await open(file,'r');
  try {const stat=await handle.stat();if(stat.ino!==before.ino||stat.dev!==before.dev||stat.size!==before.size||stat.nlink!==1)fail();
    const data=Buffer.alloc(stat.size);let at=0;
    while(at<data.length){const r=await handle.read(data,at,data.length-at,at);if(!r.bytesRead)fail();at+=r.bytesRead;}
    const tail=await handle.read(Buffer.alloc(1),0,1,at);if(tail.bytesRead)fail();return data;
  }finally{await handle.close();}
}
/** Integrity boundary before any bundled executable. Never executes, downloads or repairs. */
export async function verifyPortablePayload(root:string,pin:string,signal?:AbortSignal):Promise<void>{
  const guard=()=>{if(signal?.aborted)fail();};
  try {
    guard();hash.parse(pin);if(!path.isAbsolute(root))fail();
    for(let p=root;;p=path.dirname(p)){const s=await lstat(p);if(!s.isDirectory()||s.isSymbolicLink())fail();if(path.dirname(p)===p)break;}
    const raw=await bytes(path.join(root,'bundle-manifest.json'),16*1024*1024);
    if(createHash('sha256').update(raw).digest('hex')!==pin)fail();
    const manifest=manifestSchema.parse(JSON.parse(raw.toString('utf8'))),files=new Map(manifest.files.map(f=>[relative(f.path),f]));
    if(files.size!==manifest.files.length||new Set([...files.keys()].map(k=>k.toLowerCase())).size!==files.size||
      required.some(name=>!files.has(name))||manifest.files.reduce((n,f)=>n+f.size,0)>4*1024**3)fail();
    const seen=new Set<string>();let directories=0;
    async function visit(dir:string,prefix=''){
      guard();if(++directories>50000)fail();
      for(const entry of await readdir(dir,{withFileTypes:true})){
        guard();const name=prefix+entry.name,file=path.join(dir,entry.name),stat=await lstat(file);
        if(stat.isSymbolicLink())fail();
        if(stat.isDirectory()){relative(name);await visit(file,name+'/');continue;}
        if(name==='bundle-manifest.json'){await regular(file);continue;}
        const expected=files.get(name);if(!expected||!stat.isFile()||stat.nlink!==1||stat.size!==expected.size)fail();
        const handle=await open(file,'r');
        try {const start=await handle.stat();if(start.ino!==stat.ino||start.dev!==stat.dev||start.nlink!==1)fail();
          const digest=createHash('sha256'),buffer=Buffer.alloc(1024*1024);let size=0;
          while(true){guard();const result=await handle.read(buffer,0,buffer.length,null);if(!result.bytesRead)break;
            size+=result.bytesRead;if(size>expected.size)fail();digest.update(buffer.subarray(0,result.bytesRead));}
          if(size!==expected.size||digest.digest('hex')!==expected.sha256)fail();
        }finally{await handle.close();}
        seen.add(name);
      }
    }
    await visit(root);guard();if(seen.size!==files.size)fail();
  }catch{fail();}
}
