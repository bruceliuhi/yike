import {spawn,type ChildProcessWithoutNullStreams} from 'node:child_process';
const READY='{"schema_version":"windows-source-probe-v1","state":"READY"}\n';
/** Read-only installed-byte/ACL probe, not platform authorization or a login check. */
export function probeCollectionRuntime(options:{pythonExecutable:string;projectRoot:string;runtimePath:string;spawn?:typeof spawn}):Promise<boolean> {
  return new Promise(resolve=>{
    if([options.pythonExecutable,options.projectRoot,options.runtimePath].some(p=>typeof p!=='string'||!/^[A-Za-z]:[\\/]/.test(p)||/\p{C}/u.test(p))){resolve(false);return;}
    let child:ChildProcessWithoutNullStreams;
    const env:NodeJS.ProcessEnv={PYTHONUTF8:'1',PYTHONIOENCODING:'utf-8'};
    for(const key of ['SystemRoot','WINDIR','USERNAME'])if(process.env[key])env[key]=process.env[key];
    try {child=(options.spawn??spawn)(options.pythonExecutable,['-X','utf8','-m','app.windows_source_probe'],{cwd:options.projectRoot,shell:false,windowsHide:true,stdio:['pipe','pipe','pipe'],env});}
    catch {resolve(false);return;}
    let settled=false,invalid=false,bytes=0;const chunks:Buffer[]=[];
    const finish=(ok:boolean)=>{if(settled)return;settled=true;clearTimeout(timer);resolve(ok);};
    const abort=()=>{invalid=true;try{child.kill();}catch{}finish(false);};
    const timer=setTimeout(abort,30000);
    child.stderr.resume();
    child.on('error',abort);child.stdin.on('error',abort);child.stdout.on('error',abort);child.stderr.on('error',abort);
    child.stdout.on('data',(chunk:Buffer)=>{bytes+=chunk.length;if(bytes>16384){abort();return;}chunks.push(chunk);});
    child.on('close',(code,signal)=>finish(!invalid&&code===0&&!signal&&Buffer.concat(chunks).equals(Buffer.from(READY))));
    try{child.stdin.write(JSON.stringify({schema_version:'windows-source-probe-v1',runtime_path:options.runtimePath})+'\n');}catch{abort();}
  });
}
