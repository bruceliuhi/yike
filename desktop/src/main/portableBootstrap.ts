import path from 'node:path';
import {mkdir} from 'node:fs/promises';
import {spawn as nodeSpawn,type ChildProcess} from 'node:child_process';
import {verifyPortablePayload} from './portablePayload';
import type {PlatformLoginDriverOptions} from './platformLoginDriver';
import type {PortableRuntimeStatus} from '../shared/portableRuntime';
type Options={resourcesPath:string;userData:string;pin:{sha256:string;resourceName:string};
  verify?:typeof verifyPortablePayload;spawn?:typeof nodeSpawn;prepareParent?:(path:string)=>Promise<unknown>};
export function createPortableBootstrap(options:Options){
  let status:PortableRuntimeStatus={state:'PREPARING'},run:Promise<PlatformLoginDriverOptions|null>|null=null;
  const abort=new AbortController();let child:ChildProcess|null=null,closed=true,stopped=false;
  let closePromise:Promise<void>=Promise.resolve(),resolveClose:()=>void=()=>{};
  const stopChild=()=>{if(child&&!closed)child.kill();};
  return {
    status:():PortableRuntimeStatus=>({...status}),
    start():Promise<PlatformLoginDriverOptions|null>{
      if(run)return run;
      run=(async()=>{
        try {
          if(abort.signal.aborted||!/^[a-f0-9]{64}$/.test(options.pin.sha256)||!/^[A-Za-z0-9_-]{1,100}$/.test(options.pin.resourceName))throw Error();
          const source=path.join(options.resourcesPath,options.pin.resourceName),parent=path.join(options.userData,'portable-runtimes');
          const destination=path.join(parent,options.pin.sha256);
          await (options.verify??verifyPortablePayload)(source,options.pin.sha256,abort.signal);
          if(abort.signal.aborted)throw Error();
          await (options.prepareParent??(p=>mkdir(p,{recursive:true})))(parent);
          if(abort.signal.aborted)throw Error();
          const env:NodeJS.ProcessEnv={};
          for(const key of ['SystemRoot','WINDIR','USERNAME','TEMP','TMP'])if(process.env[key])env[key]=process.env[key];
          const ok=await new Promise<boolean>((resolve)=>{
            let output='',bad=false,finished=false;let grace:ReturnType<typeof setTimeout>|undefined;
            const finish=(value:boolean)=>{if(finished)return;finished=true;clearTimeout(timeout);if(grace)clearTimeout(grace);abort.signal.removeEventListener('abort',kill);resolve(value);};
            const kill=()=>{bad=true;stopChild();if(!grace)grace=setTimeout(()=>finish(false),5000);};
            const timeout=setTimeout(kill,15*60*1000);
            try {
              child=(options.spawn??nodeSpawn)(path.join(source,'host','python.exe'),['-B','-X','utf8','-m','app.windows_portable_install',
                '--source',source,'--destination',destination,'--manifest-sha256',options.pin.sha256],
                {cwd:path.join(source,'project'),env,stdio:['ignore','pipe','pipe'],windowsHide:true,shell:false});
              closed=false;closePromise=new Promise<void>(r=>{resolveClose=r;});
              child.stdout?.on('data',(value:Buffer)=>{if(Buffer.byteLength(output)+value.length>4096){kill();return;}output+=value.toString('utf8');});
              child.stderr?.on('data',()=>{bad=true;});
              child.once('error',()=>{bad=true;if(!child?.pid){closed=true;resolveClose();finish(false);}else kill();});
              child.once('close',(code)=>{
                closed=true;resolveClose();let receipt:unknown;
                try{receipt=JSON.parse(output);}catch{bad=true;}
                const exact=receipt!==null&&typeof receipt==='object'&&Object.keys(receipt).sort().join(',')==='manifestSha256,state'&&
                  (receipt as {state?:unknown}).state==='READY'&&(receipt as {manifestSha256?:unknown}).manifestSha256===options.pin.sha256;
                finish(!bad&&!abort.signal.aborted&&code===0&&exact);
              });
              abort.signal.addEventListener('abort',kill,{once:true});
              if(abort.signal.aborted)kill();
            }catch{finish(false);}
          });
          if(!ok||abort.signal.aborted||stopped)throw Error();
          // Verify copied bytes independently before any platform controller consumes them.
          await (options.verify??verifyPortablePayload)(destination,options.pin.sha256,abort.signal);
          if(abort.signal.aborted)throw Error();status={state:'READY'};
          return {pythonExecutable:path.join(destination,'host','python.exe'),projectRoot:path.join(destination,'project'),
            runtimePath:path.join(destination,'runtime'),profileRoot:path.join(options.userData,'platform-profiles'),
            outputRoot:path.join(options.userData,'platform-login-output')};
        }catch{status={state:'FAILED'};return null;}
      })();return run;
    },
    async stop(){stopped=true;abort.abort();stopChild();let timer:ReturnType<typeof setTimeout>|undefined;
      try {await Promise.race([closePromise,new Promise<never>((_,reject)=>{timer=setTimeout(()=>reject(Error('PORTABLE_STOP_UNCONFIRMED')),5500);})]);
        if(run)await run;if(!closed)throw Error('PORTABLE_STOP_UNCONFIRMED');
      }finally{if(timer)clearTimeout(timer);}
    },
  };
}
