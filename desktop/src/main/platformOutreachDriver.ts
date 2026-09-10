/** One CHECK/EXECUTE lifetime. Construct per dispatch with a main-resolved profile.
 * This module is private: it neither exposes IPC nor creates a sending permit. */
import {spawn,type ChildProcessWithoutNullStreams} from 'node:child_process';
import {randomUUID} from 'node:crypto';
import {lstatSync} from 'node:fs';
import {win32 as path} from 'node:path';
import type {PlatformLoginDriverOptions} from './platformLoginDriver';
import {parseNativeOutreachContext,parseNativeOutreachObservation,parseNativeOutreachOutcome,
  type NativeOutreachChannel,type NativeOutreachOutcome,type OutreachContext} from './outreachConsumer';

const SCHEMA='windows-platform-outreach-v1';
const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const failure=()=>new Error('OUTREACH_HOST_FAILED');
const unknown=():NativeOutreachOutcome=>({status:'UNKNOWN'});
type Options=PlatformLoginDriverOptions & {profileId:string;connection:Readonly<OutreachContext['connection']>};

function validatePaths(o:Options){
  if(!uuid.test(o.profileId))throw failure();
  for(const key of ['pythonExecutable','projectRoot','runtimePath','profileRoot','outputRoot'] as const){
    const value=o[key];
    if(typeof value!=='string'||!/^[A-Za-z]:[\\/]/.test(value)||!path.isAbsolute(value)||/[\p{Cc}\p{Cf}\p{Cs}]/u.test(value))throw failure();
    const info=lstatSync(value);
    if(info.isSymbolicLink()||(key==='pythonExecutable'?!info.isFile():!info.isDirectory()))throw failure();
  }
  const roots=[o.runtimePath,o.profileRoot,o.outputRoot].map(p=>path.resolve(p).toLowerCase());
  for(let i=0;i<roots.length;i++)for(let j=i+1;j<roots.length;j++)
    if(roots[i]===roots[j]||roots[i].startsWith(roots[j]+'\\')||roots[j].startsWith(roots[i]+'\\'))throw failure();
}

function decode(bytes:Buffer):Record<string,unknown>{
  const text=new TextDecoder('utf-8',{fatal:true}).decode(bytes);
  const value=JSON.parse(text);
  // Host emits compact JSON of fixed string/integer/bool fields. Round-trip
  // rejects duplicate keys and alternate ambiguous encodings at every depth.
  if(!value||Array.isArray(value)||typeof value!=='object'||JSON.stringify(value)!==text||value.schema_version!==SCHEMA)throw failure();
  return value;
}

export function createPlatformOutreachDriver(options:Options):NativeOutreachChannel & {
  stop():Promise<void>;cleanupConfirmed():boolean;
}{
  const owned={...options,connection:{...options.connection}},launch=owned.spawn??spawn;
  let child:ChildProcessWithoutNullStreams|undefined;
  let started=false,ready=false,executed=false,settled=false,stopping=false,protocolBad=false,clean=false;
  let snapshot:OutreachContext|undefined,contextWire:string|undefined;
  let observation:ReturnType<typeof parseNativeOutreachObservation>|undefined;
  let receipt:NativeOutreachOutcome|undefined,terminalClean=false,terminal=false;
  let timer:ReturnType<typeof setTimeout>|undefined,grace:ReturnType<typeof setTimeout>|undefined;
  const signals=new Set<AbortSignal>();
  let resolveCheck!:(value:unknown)=>void,rejectCheck!:(error:Error)=>void;
  let resolveResult!:(value:NativeOutreachOutcome)=>void;
  const checked=new Promise<unknown>((resolve,reject)=>{resolveCheck=resolve;rejectCheck=reject;});
  const result=new Promise<NativeOutreachOutcome>(resolve=>{resolveResult=resolve;});
  void checked.catch(()=>{});
  function finish(physicalClose=false){
    if(settled)return;settled=true;
    if(timer)clearTimeout(timer);if(grace)clearTimeout(grace);
    for(const signal of signals)signal.removeEventListener('abort',stopRequested);
    clean=physicalClose&&terminalClean&&!protocolBad;
    if(!ready)rejectCheck(failure());
    resolveResult(receipt??unknown());
  }
  function stopRequested(){
    if(settled||stopping)return;stopping=true;
    if(!child){finish();return;}
    const active=child;
    grace=setTimeout(()=>{try{active.kill();}catch{/* no cleanup claim */}finish();},30_000);
    try{active.stdin.end();}catch{/* bounded forced stop remains */}
  }
  function invalid(){protocolBad=true;stopRequested();}
  function watch(signal:AbortSignal){
    if(!signals.has(signal)){signals.add(signal);signal.addEventListener('abort',stopRequested,{once:true});}
    if(signal.aborted)stopRequested();
  }
  function write(value:unknown){
    const wire=Buffer.from(JSON.stringify(value)+'\n');
    if(!child||wire.length>131072||stopping||settled)throw failure();
    child.stdin.write(wire);
  }
  return {
    async check(context,signal){
      if(ready&&!executed&&!stopping&&!settled&&!signal.aborted&&observation){
        const age=Date.now()-Date.parse(observation.checkedAt);
        if(age>=-5000&&age<=5000&&JSON.stringify(parseNativeOutreachContext(context))===contextWire){watch(signal);return {...observation};}
      }
      if(started||stopping||settled||signal.aborted)throw failure();started=true;
      try{
        snapshot=parseNativeOutreachContext(context);contextWire=JSON.stringify(snapshot);
        if((Object.keys(snapshot.connection) as (keyof OutreachContext['connection'])[]).some(key=>snapshot!.connection[key]!==owned.connection[key])||snapshot.source.platform!=='XIAOHONGSHU'||snapshot.target.action!=='POST_COMMENT')throw failure();
        validatePaths(owned);
        const env:NodeJS.ProcessEnv={PYTHONIOENCODING:'utf-8',PYTHONUTF8:'1'};
        for(const key of ['SystemRoot','WINDIR','USERNAME'])if(process.env[key])env[key]=process.env[key];
        child=launch(owned.pythonExecutable,['-B','-X','utf8','-m','app.windows_platform_outreach'],
          {cwd:owned.projectRoot,shell:false,windowsHide:true,stdio:['pipe','pipe','pipe'],env});
        const active=child;let total=0,pending=Buffer.alloc(0);
        timer=setTimeout(stopRequested,90_000);
        active.stderr.resume();
        active.on('error',invalid);active.stdin.on('error',invalid);active.stdout.on('error',invalid);active.stderr.on('error',invalid);
        active.stdout.on('data',(chunk:Buffer)=>{
          if(settled||protocolBad)return;
          total+=chunk.length;if(total>32768){invalid();return;}
          pending=Buffer.concat([pending,chunk]);
          try{
            let end:number;
            while((end=pending.indexOf(10))>=0){
              if(terminal)throw failure();
              const frame=decode(pending.subarray(0,end));pending=pending.subarray(end+1);
              const keys=Object.keys(frame).sort().join(',');
              if(frame.state==='READY'&&keys==='observation,schema_version,state'&&!ready&&!executed&&!stopping){
                const value=parseNativeOutreachObservation(frame.observation),c=snapshot!;
                observation=value;
                const age=Date.now()-Date.parse(observation.checkedAt);
                if(observation.contextSha256!==c.contextSha256||observation.deviceId!==c.connection.deviceId||observation.connectionId!==c.connection.connectionId||observation.connectionVersion!==c.connection.connectionVersion||observation.accountPublicId!==c.connection.accountPublicId||observation.recipientId!==c.target.authorPublicId||age< -5000||age>5000)throw failure();
                ready=true;resolveCheck({...observation});
              }else if(frame.state==='RESULT'&&keys==='cleanupConfirmed,outcome,schema_version,state'&&ready&&typeof frame.cleanupConfirmed==='boolean'){
                const value=parseNativeOutreachOutcome(frame.outcome);
                if(!executed&&(!stopping||value.status!=='UNKNOWN'))throw failure();
                receipt=value;terminalClean=frame.cleanupConfirmed;terminal=true;
              }else if(frame.state==='FAILED'&&keys==='error_code,schema_version,state'&&frame.error_code==='OUTREACH_HOST_FAILED'){
                terminal=true;
              }else throw failure();
            }
            if(terminal&&pending.length)throw failure();
          }catch{invalid();}
        });
        active.on('close',(code,terminationSignal)=>{
          if(code!==0||terminationSignal||pending.length||!terminal)protocolBad=true;
          finish(code===0&&!terminationSignal);
        });
        watch(signal);
        write({schema_version:SCHEMA,action:'CHECK',runtime_path:owned.runtimePath,profile_path:path.join(owned.profileRoot,owned.profileId),output_path:path.join(owned.outputRoot,randomUUID()),context:snapshot,timeout_seconds:90});
      }catch{invalid();if(!child)finish();}
      return checked;
    },
    async execute(context,operation,signal){
      try{
        if(!ready||executed||stopping||settled||signal.aborted||JSON.stringify(parseNativeOutreachContext(context))!==contextWire)throw failure();
        const {requestId,claimId,dispatchBefore}=operation,remaining=Date.parse(dispatchBefore)-Date.now();
        if(Object.keys(operation).sort().join(',')!=='claimId,dispatchBefore,requestId'||!uuid.test(requestId)||!uuid.test(claimId)||!/^\d{4}-.*(?:Z|[+-]\d{2}:\d{2})$/.test(dispatchBefore)||!Number.isFinite(remaining)||remaining<=0||remaining>35000)throw failure();
        executed=true;watch(signal);write({schema_version:SCHEMA,action:'EXECUTE',operation:{requestId,claimId,dispatchBefore}});
      }catch{stopRequested();throw failure();}
      return result;
    },
    async stop(){stopRequested();await result;if(!clean)throw failure();},
    cleanupConfirmed:()=>clean,
  };
}
