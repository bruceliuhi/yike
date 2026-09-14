import {afterEach, beforeEach, expect, it, vi} from 'vitest';
import {EventEmitter} from 'node:events';
import {PassThrough} from 'node:stream';
import {lstatSync} from 'node:fs';

vi.mock('node:fs', () => ({lstatSync: vi.fn()}));
const schema_version = 'windows-source-view-v1';
const input = {profileId:'00000000-0000-4000-8000-000000000001',expectedAccount:'abc12345',
  noteId:'0123456789abcdef01234567',authorId:null,originalQuery:'业务搜索',signal:new AbortController().signal};
const opened = {schema_version,state:'SOURCE_OPENED'};
const closed = {schema_version,state:'CLOSED'};
const tick = () => vi.advanceTimersByTimeAsync(0);
beforeEach(() => {
  vi.useFakeTimers();
  vi.mocked(lstatSync).mockImplementation((p: any) => ({isFile:()=>String(p).endsWith('.exe'),
    isDirectory:()=>!String(p).endsWith('.exe'),isSymbolicLink:()=>false}) as any);
});
afterEach(() => {vi.useRealTimers();vi.unstubAllEnvs();vi.clearAllMocks();});
async function fixture(changes = {}) {
  const module = await import('../src/main/sourceViewDriver').catch(()=>null);
  expect(module,'main-only source driver must exist').not.toBeNull();
  const child = Object.assign(new EventEmitter(),{stdin:new PassThrough(),stdout:new PassThrough(),stderr:new PassThrough(),kill:vi.fn()});
  const spawn = vi.fn(() => child as any);
  const options = {pythonExecutable:'C:\\test\\python.exe',projectRoot:'C:\\project',runtimePath:'C:\\runtime',
    profileRoot:'C:\\private\\profiles',outputRoot:'C:\\private\\outputs',spawn,...changes};
  return {driver:module!.createSourceViewDriver(options),child,spawn,options,
    frame:(value:unknown)=>child.stdout.write(JSON.stringify(value)+'\n'),close:(code=0)=>child.emit('close',code,null)};
}
it('sends only bounded source targets to fixed host without secrets and waits physical close',async()=>{
  vi.stubEnv('DATABASE_URL','secret');vi.stubEnv('PYTHONPATH','untrusted');
  const f=await fixture();const run=f.driver.start(input);await tick();
  expect(f.spawn).toHaveBeenCalledWith(f.options.pythonExecutable,['-B','-X','utf8','-m','app.windows_source_view'],
    expect.objectContaining({cwd:f.options.projectRoot,shell:false,windowsHide:true,stdio:['pipe','pipe','pipe']}));
  const env=(f.spawn.mock.calls[0] as any)[2].env;
  for(const key of ['DATABASE_URL','PYTHONPATH','PATH'])expect(env).not.toHaveProperty(key);
  const wire=JSON.parse(f.child.stdin.read().toString());
  expect(wire).toEqual({schema_version,runtime_path:f.options.runtimePath,
    profile_path:f.options.profileRoot+'\\'+input.profileId,output_path:expect.stringMatching(/^C:\\private\\outputs\\[a-f0-9-]{36}$/),
    timeout_seconds:300,note_id:input.noteId,expected_account:input.expectedAccount,author_id:null,original_query:input.originalQuery});
  expect(f.child.stdin.writableEnded).toBe(false);
  let ready=false,done=false;void run.opened.then(()=>{ready=true;});void run.completed.then(()=>{done=true;});
  await tick();expect(ready).toBe(false);f.frame(opened);await run.opened;
  f.frame(closed);f.child.emit('exit',0,null);await tick();expect(done).toBe(false);
  f.close();await run.completed;await run.stop();
});
it.each([
  {profileId:'../escape'},{expectedAccount:'bad account'},{noteId:'https://evil/'},{authorId:'../escape'},
  {originalQuery:''},{originalQuery:'a'.repeat(201)},{originalQuery:'hello\nworld'},
  {originalQuery:'\ud800'},{originalQuery:null,authorId:null},
])('rejects invalid targets %s before spawning',async changes=>{
  const f=await fixture();const run=f.driver.start({...input,...changes});
  await expect(run.completed).rejects.toThrow('XHS_SOURCE_INVALID_INPUT');await run.stop();expect(f.spawn).not.toHaveBeenCalled();
});
it.each(['missing','relative','overlap','symlink'])('rejects unsafe %s paths',async kind=>{
  const f=await fixture(kind==='relative'?{runtimePath:'relative'}:kind==='overlap'?{outputRoot:'C:\\private\\profiles'}:{});
  if(kind==='missing')vi.mocked(lstatSync).mockImplementation(()=>{throw new Error('private path');});
  if(kind==='symlink')vi.mocked(lstatSync).mockReturnValue({isSymbolicLink:()=>true} as any);
  const run=f.driver.start(input);await expect(run.completed).rejects.toThrow('XHS_SOURCE_INVALID_INPUT');await run.stop();expect(f.spawn).not.toHaveBeenCalled();
});
it.each(['noOpened','duplicateOpened','duplicateTerminal','unknownField','duplicateKey','invalidUtf8','oversize','truncated','exit','missingTerminal','badCode','nonString'])
('poisons stop for protocol/cleanup uncertainty %s',async kind=>{
  const f=await fixture();const run=f.driver.start(input);await tick();f.child.stderr.write('token=private');
  if(kind!=='noOpened')f.frame(opened);
  if(kind==='duplicateOpened')f.frame(opened);
  if(kind==='unknownField')f.frame({...closed,token:'private'});
  else if(kind==='duplicateKey')f.child.stdout.write('{"schema_version":"windows-source-view-v1","state":"FAILED","\\u0073tate":"CLOSED"}\n');
  else if(kind==='invalidUtf8')f.child.stdout.write(Buffer.from([255,10]));
  else if(kind==='oversize')f.child.stdout.write('a'.repeat(16385));
  else if(kind==='truncated')f.child.stdout.write(JSON.stringify(closed));
  else if(kind==='badCode')f.frame({schema_version,state:'FAILED',error_code:'token=private'});
  else if(kind==='nonString')f.frame({schema_version,state:'FAILED',error_code:2});
  else if(kind!=='missingTerminal')f.frame(closed);
  if(kind==='duplicateTerminal')f.frame(closed);f.close(kind==='exit'?1:0);
  await expect(run.completed).rejects.toThrow('SOURCE_HOST_FAILED');await expect(run.stop()).rejects.toThrow('SOURCE_STOP_FAILED');
});
it.each(['XHS_SOURCE_INVALID_INPUT','XHS_SOURCE_ORIGIN_CHANGED','XHS_SOURCE_ACCOUNT_CHANGED','XHS_SOURCE_PLATFORM_BLOCKED',
  'XHS_SOURCE_SEARCH_UNAVAILABLE','XHS_SOURCE_NOT_FOUND','XHS_SOURCE_DETAIL_UNAVAILABLE','XHS_SOURCE_UNAVAILABLE'])
('rejects known %s failure but proves cleanup',async error_code=>{
  const f=await fixture();const run=f.driver.start(input);await tick();
  f.frame({schema_version,state:'FAILED',error_code});f.close();
  await expect(run.completed).rejects.toThrow(error_code);await expect(run.opened).rejects.toThrow(error_code);await run.stop();
});
it('uses EOF cancellation and suppresses a late ready event until close',async()=>{
  const f=await fixture();const abort=new AbortController();const run=f.driver.start({...input,signal:abort.signal});await tick();abort.abort();
  let stopped=false,ready=false;void run.opened.then(()=>{ready=true;},()=>{});
  const stop=run.stop().then(()=>{stopped=true;});f.frame(opened);await tick();
  expect(f.child.stdin.writableEnded).toBe(true);expect(stopped).toBe(false);expect(ready).toBe(false);
  f.frame({schema_version,state:'CANCELLED',error_code:'XHS_SOURCE_CANCELLED'});f.close();
  await expect(run.completed).rejects.toThrow('XHS_SOURCE_CANCELLED');await stop;
});
it('bounds runtime at 300 seconds and allows 30-second cleanup grace',async()=>{
  const f=await fixture();const run=f.driver.start(input);await tick();
  await vi.advanceTimersByTimeAsync(300000);expect(f.child.stdin.writableEnded).toBe(true);
  f.frame({schema_version,state:'TIMED_OUT',error_code:'XHS_SOURCE_TIMED_OUT'});f.close();
  await expect(run.completed).rejects.toThrow('XHS_SOURCE_TIMED_OUT');await run.stop();
});
it.each(['forced','hostFailure','spawnError'])('poisons stop on %s',async kind=>{
  const f=await fixture();const run=f.driver.start(input);await tick();
  if(kind==='hostFailure'){f.frame({schema_version,state:'FAILED',error_code:'SOURCE_HOST_FAILED'});f.close();}
  if(kind==='spawnError'){f.child.emit('error',new Error('secret'));f.close(-2);}
  const assertion=expect(run.stop()).rejects.toThrow('SOURCE_STOP_FAILED');
  if(kind==='forced'){await vi.advanceTimersByTimeAsync(30000);expect(f.child.kill).toHaveBeenCalledOnce();}
  await assertion;await expect(run.completed).rejects.toThrow(/^SOURCE_(HOST|STOP)_FAILED$/);
});
it('does not spawn for pre-aborted or immediately stopped requests',async()=>{
  const f=await fixture();const abort=new AbortController();abort.abort();
  const run=f.driver.start({...input,signal:abort.signal});await expect(run.completed).rejects.toThrow('XHS_SOURCE_CANCELLED');await run.stop();
  const other=f.driver.start(input);const stop=other.stop();await expect(other.completed).rejects.toThrow('XHS_SOURCE_CANCELLED');await stop;
  expect(f.spawn).not.toHaveBeenCalled();
});
it('reports exclusive-path busy without poisoning cleanup after clean host close',async()=>{
  const f=await fixture();const run=f.driver.start(input);await tick();
  f.frame({schema_version,state:'FAILED',error_code:'XHS_SOURCE_BUSY'});f.close();
  await expect(run.opened).rejects.toThrow('XHS_SOURCE_BUSY');
  await expect(run.completed).rejects.toThrow('XHS_SOURCE_BUSY');await run.stop();
});
it.each(['XHS_SOURCE_CANCELLED','XHS_SOURCE_TIMED_OUT'])('rejects FAILED with mismatched %s code',async error_code=>{
  const f=await fixture();const run=f.driver.start(input);await tick();
  f.frame({schema_version,state:'FAILED',error_code});f.close();
  await expect(run.completed).rejects.toThrow('SOURCE_HOST_FAILED');
  await expect(run.stop()).rejects.toThrow('SOURCE_STOP_FAILED');
});
