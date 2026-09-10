import {beforeEach,afterEach,it,expect,vi} from 'vitest';
import {EventEmitter} from 'node:events';
import {PassThrough} from 'node:stream';
import {lstatSync} from 'node:fs';
import {randomUUID} from 'node:crypto';
vi.mock('node:fs',()=>({lstatSync:vi.fn()}));
const schema_version='windows-platform-outreach-v1';
const id=()=>randomUUID(), sha='a'.repeat(64), actor='a'.repeat(24), author='b'.repeat(24), post='c'.repeat(24);
const tick=()=>vi.advanceTimersByTimeAsync(0);
beforeEach(()=>{vi.useFakeTimers();vi.mocked(lstatSync).mockImplementation((p:any)=>({isSymbolicLink:()=>false,isFile:()=>String(p).endsWith('.exe'),isDirectory:()=>!String(p).endsWith('.exe')}) as any);});
afterEach(()=>{vi.useRealTimers();vi.clearAllMocks();});
async function fixture(){
  const module=await import('../src/main/platformOutreachDriver');
  const opportunityId=id();
  const context:any={schemaVersion:'outreach-context-v1',binding:{opportunityId,channel:'comment',requestId:id(),contentHash:sha},ownerUserId:id(),accountScope:{id:id(),version:1},profileVersionId:id(),
    draft:{opportunityId,channel:'comment',content:'这个项目还在找团队吗？',savedContent:'这个项目还在找团队吗？',version:1,accountId:actor,recipient:author},
    source:{sourceId:id(),evidenceVersion:id(),evidenceSha256:sha,platform:'XIAOHONGSHU',kind:'POST',url:`https://www.xiaohongshu.com/explore/${post}`,excerpt:'synthetic'},
    target:{action:'POST_COMMENT',authorPublicId:author,postId:post,commentId:null},connection:{deviceId:id(),connectionId:id(),connectionVersion:1,accountPublicId:actor,platform:'XIAOHONGSHU'},channelCapability:{status:'UNVERIFIED',reason:'CHANNEL_CHECK_REQUIRED'},authorization:'NOT_GRANTED',contextSha256:sha};
  const child=Object.assign(new EventEmitter(),{stdin:new PassThrough(),stdout:new PassThrough(),stderr:new PassThrough(),kill:vi.fn()});
  const spawn=vi.fn(()=>child as any);
  const driver=module.createPlatformOutreachDriver({pythonExecutable:'C:\\python.exe',projectRoot:'C:\\project',runtimePath:'C:\\runtime',profileRoot:'C:\\private\\profiles',outputRoot:'C:\\private\\outputs',profileId:id(),connection:context.connection,spawn:spawn as any});
  const observation={status:'AVAILABLE',contextSha256:sha,...context.connection,recipientId:author,checkedAt:new Date().toISOString()};delete (observation as any).platform;
  const frame=(value:unknown)=>child.stdout.write(JSON.stringify(value)+'\n');
  const operation={requestId:id(),claimId:id(),dispatchBefore:new Date(Date.now()+20_000).toISOString()};
  const outcome={status:'SENT',confirmed:true,proof:{kind:'ACCEPTED',externalId:'synthetic',sha256:sha,observedAt:new Date().toISOString()}};
  const signal=new AbortController();
  return {driver,child,context,observation,frame,operation,outcome,signal,spawn};
}
it('keeps one fixed host alive between CHECK and one EXECUTE, waits close for result',async()=>{
  const f=await fixture();const check=f.driver.check(f.context,f.signal.signal);await tick();
  const request=JSON.parse(f.child.stdin.read().toString());expect(request).toMatchObject({action:'CHECK',schema_version,context:f.context});
  expect((f.spawn.mock.calls[0] as unknown[])[1]).toEqual(['-B','-X','utf8','-m','app.windows_platform_outreach']);
  f.frame({schema_version,state:'READY',observation:f.observation});expect(await check).toEqual(f.observation);
  const execute=f.driver.execute(f.context,f.operation,f.signal.signal);await tick();expect(JSON.parse(f.child.stdin.read().toString())).toEqual({schema_version,action:'EXECUTE',operation:f.operation});
  let done=false;void execute.then(()=>{done=true;});f.frame({schema_version,state:'RESULT',outcome:f.outcome,cleanupConfirmed:true});await tick();expect(done).toBe(false);
  f.child.emit('close',0,null);expect(await execute).toEqual(f.outcome);expect(f.driver.cleanupConfirmed()).toBe(true);
  await expect(f.driver.execute(f.context,f.operation,f.signal.signal)).rejects.toThrow('OUTREACH_HOST_FAILED');expect(f.spawn).toHaveBeenCalledTimes(1);
});
it('rejects a changed binding before EXECUTE and closes stdin',async()=>{
  const f=await fixture();const check=f.driver.check(f.context,f.signal.signal);await tick();f.child.stdin.read();f.frame({schema_version,state:'READY',observation:f.observation});await check;
  await expect(f.driver.execute({...f.context,draft:{...f.context.draft,content:'changed'}},f.operation,f.signal.signal)).rejects.toThrow('OUTREACH_HOST_FAILED');
  expect(f.child.stdin.writableEnded).toBe(true);f.child.emit('close',0,null);
});
it('preserves a valid late receipt after cancellation/cleanup failure without another action',async()=>{
  const f=await fixture();const check=f.driver.check(f.context,f.signal.signal);await tick();f.frame({schema_version,state:'READY',observation:f.observation});await check;
  const execute=f.driver.execute(f.context,f.operation,f.signal.signal);f.signal.abort();expect(f.child.stdin.writableEnded).toBe(true);
  f.frame({schema_version,state:'RESULT',outcome:f.outcome,cleanupConfirmed:false});f.child.emit('close',0,null);
  expect(await execute).toEqual(f.outcome);expect(f.driver.cleanupConfirmed()).toBe(false);
});
it('fails closed on duplicate/malformed READY and bounds cleanup',async()=>{
  const f=await fixture();const check=f.driver.check(f.context,f.signal.signal);const failed=expect(check).rejects.toThrow('OUTREACH_HOST_FAILED');await tick();
  f.child.stdout.write('{"schema_version":"windows-platform-outreach-v1","state":"READY","state":"FAILED"}\n');
  await vi.advanceTimersByTimeAsync(30_000);await failed;expect(f.child.kill).toHaveBeenCalledOnce();expect(f.driver.cleanupConfirmed()).toBe(false);
});
it('does not launch with an aborted signal or wrong owned connection',async()=>{
  const f=await fixture();f.signal.abort();await expect(f.driver.check(f.context,f.signal.signal)).rejects.toThrow('OUTREACH_HOST_FAILED');expect(f.spawn).not.toHaveBeenCalled();
  const g=await fixture();await expect(g.driver.check({...g.context,connection:{...g.context.connection,connectionId:id()}},g.signal.signal)).rejects.toThrow('OUTREACH_HOST_FAILED');expect(g.spawn).not.toHaveBeenCalled();
});
