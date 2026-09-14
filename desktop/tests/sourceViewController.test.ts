import {afterEach,describe,expect,it,vi} from 'vitest';
import {createSourceViewController} from '../src/main/sourceViewController';
import {resolveCollectionAccount} from '../src/main/collectionAccountBinding';
import {rawEvidenceBinding,rawEvidenceFixture} from './fixtures/rawCandidateEvidence';
vi.mock('../src/main/collectionAccountBinding',()=>({resolveCollectionAccount:vi.fn()}));
function deferred<T>() {let resolve!:(v:T)=>void, reject!:(e:Error)=>void;const promise=new Promise<T>((a,b)=>{resolve=a;reject=b;});void promise.catch(()=>{});return {promise,resolve,reject};}
function setup() {
  const raw=rawEvidenceFixture(),ob=raw.observations.items[0],c=raw.candidate;
  c.platform=ob.platform='XIAOHONGSHU';c.kind='COMMENT';c.external_source_id='a'.repeat(24);c.external_comment_id='b'.repeat(24);
  c.current_version.public_url=ob.content.public_url=`https://www.xiaohongshu.com/explore/${c.external_source_id}?comment_id=${c.external_comment_id}`;
  ob.execution_context.access_mode='PLATFORM_ACCOUNT';ob.execution_context.connection_id='dddddddd-dddd-4ddd-8ddd-dddddddddddd';ob.execution_context.connection_version=2;
  const abort=new AbortController(),opened=deferred<void>(),completed=deferred<void>();
  const scope={session:{userId:'test-user',sessionId:'epoch',isCurrent:()=>!abort.signal.aborted},device:{deviceId:ob.execution_context.device_id,credentialVersion:3},signal:abort.signal,
    transport:{requestConnection:vi.fn(),requestExecution:vi.fn(),requestCandidate:vi.fn()},close:vi.fn(()=>abort.abort())};
  const identity={openWorkerScope:vi.fn(async()=>({ok:true as const,scope})),getStatus:vi.fn(()=>({state:'READY' as const,...scope.device})),requestApi:vi.fn(async()=>({ok:true as const,status:200,data:raw}))};
  const run={opened:opened.promise,completed:completed.promise,stop:vi.fn(async()=>{completed.resolve();})};
  const driver={start:vi.fn(()=>run)},store={read:vi.fn()};
  vi.mocked(resolveCollectionAccount).mockResolvedValue({profileId:'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee',accountPublicId:'f'.repeat(24)});
  const controller=createSourceViewController({serviceOrigin:'https://example.test',identity,store,driver});
  return {controller,identity,scope,abort,opened,completed,run,driver,raw};
}
afterEach(()=>{vi.clearAllMocks();});
describe('readonly source view controller',()=>{
  it('fetches bound fresh evidence, uses protected account and distinguishes comment parent',async()=>{
    const s=setup();s.opened.resolve();
    expect(await s.controller.open(rawEvidenceBinding)).toEqual({state:'OPENED',sourceKind:'COMMENT'});
    expect(s.identity.requestApi).toHaveBeenCalledWith({operation:'candidates.rawEvidence',payload:{candidateId:rawEvidenceBinding.candidateId}});
    expect(s.driver.start).toHaveBeenCalledWith(expect.objectContaining({profileId:'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee',expectedAccount:'f'.repeat(24),noteId:'a'.repeat(24),authorId:null,originalQuery:'  原查询  ',signal:expect.any(AbortSignal)}));
    expect(s.scope.close).not.toHaveBeenCalled();await s.controller.shutdown();expect(s.run.stop).toHaveBeenCalledOnce();expect(s.scope.close).toHaveBeenCalledOnce();
  });
  it('rejects renderer URLs before any private request',async()=>{
    const s=setup();expect(await s.controller.open({...rawEvidenceBinding,url:'https://evil.test'})).toEqual({state:'FAILED',error:'SOURCE_VIEW_UNAVAILABLE'});
    expect(s.identity.openWorkerScope).not.toHaveBeenCalled();
  });
  it('rejects stale evidence and other-device candidates without launching',async()=>{
    for(const change of ['stale','device']) {
      const s=setup();if(change==='stale')s.raw.candidate.revision++;else s.raw.observations.items[0].execution_context.device_id='00000000-0000-4000-8000-000000000000';
      expect(await s.controller.open(rawEvidenceBinding)).toEqual({state:'FAILED',error:'SOURCE_VIEW_UNAVAILABLE'});expect(s.driver.start).not.toHaveBeenCalled();expect(s.scope.close).toHaveBeenCalledOnce();
    }
  });
  it('does not launch when session changes while fetching',async()=>{
    const s=setup();s.identity.requestApi.mockImplementation(async()=>{s.abort.abort();return {ok:true,status:200,data:s.raw};});
    expect(await s.controller.open(rawEvidenceBinding)).toEqual({state:'FAILED',error:'SOURCE_VIEW_UNAVAILABLE'});expect(s.driver.start).not.toHaveBeenCalled();
  });
  it('rejects duplicate opens and stops live viewing on session abort',async()=>{
    const s=setup();s.opened.resolve();await s.controller.open(rawEvidenceBinding);
    expect(await s.controller.open(rawEvidenceBinding)).toEqual({state:'BUSY'});s.abort.abort();await vi.waitFor(()=>expect(s.run.stop).toHaveBeenCalledOnce());
    await vi.waitFor(()=>expect(s.scope.close).toHaveBeenCalledOnce());
  });
  it('keeps unknown cleanup poisoned rather than opening another browser',async()=>{
    const s=setup();s.run.stop.mockRejectedValue(new Error('SECRET'));s.opened.reject(new Error('SOURCE_HOST_FAILED'));
    expect(await s.controller.open(rawEvidenceBinding)).toEqual({state:'FAILED',error:'SOURCE_STOP_FAILED'});
    expect(await s.controller.open(rawEvidenceBinding)).toEqual({state:'FAILED',error:'SOURCE_STOP_FAILED'});
    await expect(s.controller.shutdown()).rejects.toThrow('SOURCE_STOP_FAILED');
  });
  it('reports a confirmed prelaunch lock conflict as recoverable busy',async()=>{
    const s=setup();s.opened.reject(new Error('XHS_SOURCE_BUSY'));s.completed.reject(new Error('XHS_SOURCE_BUSY'));
    expect(await s.controller.open(rawEvidenceBinding)).toEqual({state:'BUSY'});
    await expect(s.controller.shutdown()).resolves.toBeUndefined();
  });
  it('releases a normally closed browser and hides raw runtime errors',async()=>{
    const s=setup();s.opened.resolve();await s.controller.open(rawEvidenceBinding);s.completed.resolve();await vi.waitFor(()=>expect(s.scope.close).toHaveBeenCalledOnce());
    expect(s.run.stop).not.toHaveBeenCalled();await s.controller.shutdown();
  });
});
