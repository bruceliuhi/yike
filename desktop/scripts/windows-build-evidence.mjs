import {createHash, randomUUID} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {existsSync, mkdirSync, readFileSync, readdirSync, realpathSync, renameSync, statSync, writeFileSync} from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const STAGES = ['preflight','dependencies','typecheck','unit-tests','native-smoke','make-win','artifacts','archive-check','packaged-smoke'];
const scriptRoot = path.dirname(fileURLToPath(import.meta.url));
export function sha256(file) {return createHash('sha256').update(readFileSync(file)).digest('hex');}
function git(root,args) {
  const result=spawnSync('git',args,{cwd:root,encoding:'utf8',windowsHide:true});
  return result.status===0?result.stdout.trim():null;
}
function save(report,directory) {
  const destination=path.join(directory,'windows-build.json');const temporary=destination+'.tmp';
  writeFileSync(temporary,JSON.stringify(report,null,2)+'\n');renameSync(temporary,destination);
}
export function createEvidence(root,outputDirectory) {
  root=path.resolve(root);
  const runId=new Date().toISOString().replace(/[:.]/g,'-')+'-'+randomUUID().slice(0,8);
  const directory=path.resolve(outputDirectory||path.join(root,'out/windows-evidence',runId));mkdirSync(directory,{recursive:true});
  const commit=git(root,['rev-parse','HEAD']);const dirty=git(root,['status','--porcelain=v1','--untracked-files=normal']);
  const lock=path.join(root,'package-lock.json');
  const report={schemaVersion:1,runId,startedAt:new Date().toISOString(),finishedAt:null,outcome:'IN_PROGRESS',
    source:{commit,dirty:dirty===null?null:dirty.length>0,gitAvailable:commit!==null&&dirty!==null,lockfile:{path:'package-lock.json',sha256:existsSync(lock)?sha256(lock):null}},
    host:{platform:process.platform,osVersion:os.version(),osRelease:os.release(),osArch:os.machine(),nodeVersion:process.version,nodeArch:process.arch},
    stages:STAGES.map(id=>({id,status:'NOT_RUN',startedAt:null,finishedAt:null,exitCode:null})),artifacts:[],failureCode:null,
    manualAcceptance:'UNTESTED',scope:'Automatic build evidence only; installation, visible startup, uninstall and display scaling require the separate manual record.'};
  save(report,directory);
  const template=path.join(scriptRoot,'../docs/WINDOWS_ACCEPTANCE_TEMPLATE.md');
  writeFileSync(path.join(directory,'WINDOWS_ACCEPTANCE.md'),readFileSync(template,'utf8').replaceAll('{{RUN_ID}}',runId));
  return {root,directory,report};
}
export function beginStage(evidence,id) {
  const stage=evidence.report.stages.find(value=>value.id===id);if(!stage||stage.status!=='NOT_RUN')throw new Error('INVALID_STAGE');
  stage.status='RUNNING';stage.startedAt=new Date().toISOString();save(evidence.report,evidence.directory);
}
export function endStage(evidence,id,exitCode) {
  const stage=evidence.report.stages.find(value=>value.id===id);if(!stage||stage.status!=='RUNNING'||!Number.isInteger(exitCode))throw new Error('INVALID_STAGE');
  Object.assign(stage,{status:exitCode===0?'PASSED':'FAILED',finishedAt:new Date().toISOString(),exitCode});save(evidence.report,evidence.directory);
}
export function addArtifact(evidence,relativePath) {
  const normalized=relativePath.replaceAll('\\','/');
  if(path.isAbsolute(relativePath)||normalized.split('/').some(part=>part==='..')||!normalized.startsWith('out/'))throw new Error('INVALID_ARTIFACT_PATH');
  const absolute=realpathSync(path.resolve(evidence.root,relativePath));
  const relativeReal=path.relative(realpathSync(path.join(evidence.root,'out')),absolute);
  if(relativeReal==='..'||relativeReal.startsWith('..'+path.sep)||path.isAbsolute(relativeReal))throw new Error('INVALID_ARTIFACT_PATH');
  const stat=statSync(absolute);
  if(!stat.isFile())throw new Error('INVALID_ARTIFACT');
  evidence.report.artifacts.push({path:normalized,bytes:stat.size,sha256:sha256(absolute),modifiedAt:stat.mtime.toISOString()});save(evidence.report,evidence.directory);
}
export function finishEvidence(evidence,failureCode=null) {
  const passed=evidence.report.stages.every(stage=>stage.status==='PASSED');
  evidence.report.outcome=passed&&!failureCode?'BUILD_SUCCEEDED':'BUILD_FAILED';
  evidence.report.failureCode=failureCode||(!passed?'INCOMPLETE_BUILD':null);evidence.report.finishedAt=new Date().toISOString();
  save(evidence.report,evidence.directory);return evidence.report.outcome==='BUILD_SUCCEEDED'?0:1;
}
function command(executable,args,root) {
  // Commands and arguments are fixed by this script. Do not save stdout/stderr,
  // process.env, registry settings, usernames, machine names or exception text.
  const result=spawnSync(executable,args,{cwd:root,stdio:'inherit',windowsHide:true});
  return Number.isInteger(result.status)?result.status:1;
}
export function runWindowsBuild(root) {
  const evidence=createEvidence(root);let failureCode=null;
  const run=(id,operation)=>{beginStage(evidence,id);let code=1;try{code=operation();}catch{code=1;}endStage(evidence,id,code);if(code!==0){failureCode=id==='preflight'?'WINDOWS_X64_NODE24_REQUIRED':'STAGE_FAILED';throw new Error('STAGE_FAILED');}};
  try{
    run('preflight',()=>process.platform==='win32'&&process.arch==='x64'&&['x86_64','amd64','x64'].includes(os.machine().toLowerCase())&&process.versions.node.split('.')[0]==='24'?0:1);
    const npm=(args)=>command('cmd.exe',['/d','/s','/c','npm.cmd '+args.join(' ')],evidence.root);
    run('dependencies',()=>npm(['ci']));run('typecheck',()=>npm(['run','typecheck']));run('unit-tests',()=>npm(['test']));
    run('native-smoke',()=>command(process.execPath,['scripts/run-native-service-smoke.mjs'],evidence.root));
    run('make-win',()=>npm(['run','make:win']));
    const archive='out/意客AI-win32-x64/resources/app.asar';
    run('artifacts',()=>{
      const dist='out/make/squirrel.windows/x64';const version=JSON.parse(readFileSync(path.join(evidence.root,'package.json'),'utf8')).version;
      const packages=readdirSync(path.join(evidence.root,dist)).filter(name=>/^YikeAI[-.]/i.test(name)&&name.includes(version)&&name.endsWith('.nupkg'));
      if(!packages.length)return 1;
      for(const relative of [archive,dist+'/YikeAI-Setup.exe',dist+'/RELEASES',...packages.map(name=>dist+'/'+name)])addArtifact(evidence,relative);
      return 0;
    });
    run('archive-check',()=>command(process.execPath,['scripts/verify-package.mjs',archive],evidence.root));
    run('packaged-smoke',()=>command(process.execPath,['scripts/run-packaged-smoke.mjs',archive],evidence.root));
  }catch{failureCode||='SCRIPT_FAILED';}
  const code=finishEvidence(evidence,failureCode);
  console.log(`Windows evidence: ${evidence.directory}`);
  console.log(code===0?'BUILD_SUCCEEDED; manual installation and scaling checks remain UNTESTED.':'BUILD_FAILED; return windows-build.json even when no installer was produced.');
  return code;
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)) {
  try{process.exitCode=runWindowsBuild(path.resolve(scriptRoot,'..'));}
  catch{console.error('Evidence initialization failed. Check that desktop/out is writable; no environment or exception details were recorded.');process.exitCode=1;}
}
