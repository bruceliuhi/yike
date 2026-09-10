import {afterEach,expect,it,vi} from 'vitest';
import {createPlatformConnectionController, type PlatformConnectionControllerOptions} from '../src/main/platformConnectionController';
import type {ApiResult} from '../src/shared/contracts';
const id=(n:number)=>`00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
const account='66c01234abcdef0123456789';
const NOW=Date.parse('2026-09-10T05:00:00Z');
function deferred<T>() {let resolve!:(v:T)=>void,reject!:(e:unknown)=>void;const promise=new Promise<T>((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};}
const cleanups:Array<()=>Promise<void>>=[];
afterEach(async()=>{for(const fn of cleanups.splice(0))await fn();vi.useRealTimers();});
function fixture(platform:'XIAOHONGSHU'|'DOUYIN'|'BILIBILI'='XIAOHONGSHU', accountId=account) {
 let current=true,deviceVersion=1,now=NOW,record:any=null,row:any=null,mode='',applied=0,flowId='';
 const opened=deferred<void>(),completed=deferred<{account_public_id:string;checked_at:string}>();
 const calls:any[]=[],saved:any[]=[],receipts=new Map();
 const stop=vi.fn(async()=>{}),close=vi.fn();
 const store={
  open:vi.fn(async(scope:any)=>record??(record={version:1,scope,flowId:id(3),profileId:id(4),state:'PENDING',registration:null,verification:null})),
  read:vi.fn(async()=>structuredClone(record)),
  setOperation:vi.fn(async(_scope:any,_flow:string,op:any)=>{saved.push(structuredClone(op));record={...record,[op.action==='REGISTER'?'registration':'verification']:op};return structuredClone(record);}),
  resolve:vi.fn(async()=>record={...record,state:'RESOLVED'})};
 const transport={requestExecution:vi.fn(),requestCandidate:vi.fn(),requestConnection:vi.fn(async(input:any):Promise<ApiResult>=>{
  calls.push(structuredClone(input));
  if(input.operation==='connections.current')return {ok:true,status:200,data:{items:row?[row]:[]}};
  if(input.operation==='connections.receipt')return receipts.has(input.payload.request_id)?{ok:true,status:200,data:receipts.get(input.payload.request_id)}:{ok:false,status:404,error:'not_found'};
  const op=input.payload;expect(saved.some(x=>x.request_id===op.request_id)).toBe(true);applied++;
  row={connection_id:id(5),device_id:id(1),account_public_id:accountId,platform,status:op.action==='REGISTER'?'UNVERIFIED':'CONNECTED',connection_version:op.expected_connection_version+1,connected_at:'2026-09-10T05:00:00Z',disconnected_at:null};
  const receipt={request_id:op.request_id,device_id:op.device_id,action:op.action,state:'SUCCEEDED',connection_id:row.connection_id,connection_version:row.connection_version,connection_status:row.status,error_code:null};
  receipts.set(op.request_id,receipt);
  if(op.action==='VERIFY'&&mode==='disconnect')row={...row,status:'DISCONNECTED',connection_version:row.connection_version+1};
  if(op.action==='VERIFY'&&mode==='wrong-platform')row={...row,platform:platform==='DOUYIN'?'XIAOHONGSHU':'DOUYIN'};
  if(op.action==='REGISTER'&&mode==='unknown'){mode='';return {ok:false,status:0,error:'SERVICE_UNAVAILABLE'};}
  if(op.action==='REGISTER'&&mode==='logout')current=false;
  return {ok:true,status:200,data:receipt};
 })};
 const identity:PlatformConnectionControllerOptions['identity']={getStatus:()=>({state:'READY',deviceId:id(1),credentialVersion:deviceVersion}),openWorkerScope:vi.fn(async()=>({ok:true as const,scope:{session:{userId:'owner',sessionId:id(2),isCurrent:()=>current},device:{deviceId:id(1),credentialVersion:1},transport,close}}))};
 const login={start:vi.fn(()=>({opened:opened.promise,completed:completed.promise,stop}))};
 const controller=createPlatformConnectionController({serviceOrigin:'https://pilot.example',identity,store,login,now:()=>now});
 cleanups.push(()=>controller.shutdown());
 async function openFlow() {const p=controller.execute({action:'OPEN',platform});opened.resolve();const result=await p;if('flowId' in result)flowId=result.flowId;return result;}
 async function authenticate() {await openFlow();completed.resolve({account_public_id:accountId,checked_at:'2026-09-10T05:00:00Z'});await Promise.resolve();}
 const check=()=>controller.execute({action:'CHECK',platform,flowId});
 return {controller,identity,login,store,transport,opened,completed,calls,saved,stop,close,openFlow,authenticate,check,receipts,
  setMode:(s:string)=>mode=s,setCurrent:(b:boolean)=>current=b,setDeviceVersion:(v:number)=>deviceVersion=v,setNow:(v:number)=>now=v,
  getFlowId:()=>flowId,getRecord:()=>record,getRow:()=>row,setRow:(r:any)=>row=r,applied:()=>applied};
}
it.each([['DOUYIN','owner.handle-1'],['BILIBILI','1234567890']] as const)('binds REGISTER, VERIFY and current row to %s',async(platform,accountId)=>{
 const f=fixture(platform,accountId);await f.authenticate();const result=await f.check();expect(result.state).toBe('CONNECTED');
 expect(f.login.start).toHaveBeenCalledWith({profileId:expect.any(String),platform});
 expect(f.saved).toEqual(expect.arrayContaining([expect.objectContaining({action:'REGISTER',platform,account_public_id:accountId}),expect.objectContaining({action:'VERIFY',platform,account_public_id:accountId})]));
 expect((await f.controller.execute({action:'CHECK',platform:'XIAOHONGSHU',flowId:f.getFlowId()})).state).toBe('INVALID_REQUEST');
 expect((await f.controller.execute({action:'CANCEL',platform:'XIAOHONGSHU',flowId:f.getFlowId()})).state).toBe('INVALID_REQUEST');
});
it('rejects a CONNECTED row from another platform',async()=>{
 const f=fixture('DOUYIN','owner.handle-1');await f.authenticate();f.setMode('wrong-platform');
 expect(await f.check()).toEqual({state:'FAILED',error:'CURRENT_CONNECTION_CHANGED'});
});
it('does not report OPENED before real login progress or write registration before authentication',async()=>{
 const f=fixture();let resolved=false;const p=f.controller.execute({action:'OPEN',platform:'XIAOHONGSHU'}).then((r:any)=>{resolved=true;return r;});
 await Promise.resolve();await Promise.resolve();expect(resolved).toBe(false);expect(f.calls).toEqual([]);
 f.opened.resolve();const result=await p;expect(result).toEqual({state:'OPENED',flowId:expect.any(String)});
 expect(await f.controller.execute({action:'CHECK',platform:'XIAOHONGSHU',flowId:result.flowId})).toEqual({state:'WAITING_LOGIN',flowId:result.flowId});expect(f.calls).toEqual([]);
});
it('persists original REGISTER and VERIFY before sending then checks current exact version',async()=>{
 const f=fixture();await f.authenticate();const result=await f.check();
 expect(result.state).toBe('CONNECTED');if(result.state!=='CONNECTED')throw Error('expected connection');expect(result.connection).toEqual(f.getRow());expect(f.saved.map(x=>x.action)).toEqual(['REGISTER','VERIFY']);
 expect(f.saved[1]).toMatchObject({connection_id:id(5),expected_connection_version:1,account_public_id:account,session_ref:`vault://platform/${id(4)}`});
 expect(f.calls.at(-1)).toEqual({operation:'connections.current'});expect(f.getRecord().state).toBe('RESOLVED');
});
it('unknown registration resumes its original UUID receipt without another POST',async()=>{
 const f=fixture();await f.authenticate();f.setMode('unknown');expect((await f.check()).state).toBe('UNKNOWN');
 const original=f.saved[0].request_id;expect(f.getRecord().state).toBe('PENDING');
 expect((await f.check()).state).toBe('CONNECTED');expect(f.saved[0].request_id).toBe(original);expect(f.applied()).toBe(2);
});
it('historical successful VERIFY cannot resurrect a subsequently disconnected current row',async()=>{
 const f=fixture();await f.authenticate();f.setMode('disconnect');expect(await f.check()).toEqual({state:'FAILED',error:'CURRENT_CONNECTION_CHANGED'});
 expect(f.getRow().status).toBe('DISCONNECTED');expect(f.applied()).toBe(2);
});
it('rejects stale login observations without writing',async()=>{
 const f=fixture();await f.authenticate();f.setNow(NOW+121000);expect(await f.check()).toEqual({state:'FAILED',error:'LOGIN_EXPIRED'});expect(f.applied()).toBe(0);
});
it('a cancelled older browser attempt cannot cancel a resumed pending profile',async()=>{
 const f=fixture();await f.openFlow();const old=f.getFlowId();await f.openFlow();expect(f.getFlowId()).not.toBe(old);
 expect((await f.controller.execute({action:'CANCEL',platform:'XIAOHONGSHU',flowId:old})).state).toBe('INVALID_REQUEST');expect(f.stop).toHaveBeenCalledTimes(1);
});
it('recovered pending requests cannot register a different logged-in platform account',async()=>{
 const f=fixture();await f.authenticate();f.setMode('unknown');await f.check();f.getRecord().registration.account_public_id='other12345';
 expect(await f.check()).toEqual({state:'FAILED',error:'ACCOUNT_MISMATCH'});expect(f.applied()).toBe(1);
});
it('freshness expiring during a service round-trip prevents the next mutation',async()=>{
 const f=fixture();await f.authenticate();f.transport.requestConnection.mockImplementationOnce(async()=>{f.setNow(NOW+121000);return {ok:true,status:200,data:{items:[]}};});
 expect(await f.check()).toEqual({state:'FAILED',error:'LOGIN_EXPIRED'});expect(f.applied()).toBe(0);
});
it('unknown physical stop poisons reopening instead of overlapping browser profiles',async()=>{
 const f=fixture();await f.openFlow();f.stop.mockRejectedValue(new Error('SOURCE_STOP_FAILED'));
 expect(await f.controller.execute({action:'CANCEL',platform:'XIAOHONGSHU',flowId:f.getFlowId()})).toEqual({state:'FAILED',error:'SOURCE_STOP_FAILED'});
 expect(await f.openFlow()).toEqual({state:'FAILED',error:'SOURCE_STOP_FAILED'});expect(f.login.start).toHaveBeenCalledTimes(1);
 cleanups.pop();await expect(f.controller.shutdown()).rejects.toThrow('SOURCE_STOP_FAILED');
});
it('logout between registration and VERIFY prevents further mutations and result disclosure',async()=>{
 const f=fixture();await f.authenticate();f.setMode('logout');expect((await f.check()).state).toBe('SESSION_CHANGED');expect(f.applied()).toBe(1);
});
it('device credential change invalidates the original login scope',async()=>{
 const f=fixture();await f.authenticate();f.setDeviceVersion(2);expect((await f.check()).state).toBe('SESSION_CHANGED');expect(f.applied()).toBe(0);
});
it('stale CANCEL cannot stop a different flow; valid cancel waits physical stop',async()=>{
 const f=fixture();await f.openFlow();expect((await f.controller.execute({action:'CANCEL',platform:'XIAOHONGSHU',flowId:id(8)})).state).toBe('INVALID_REQUEST');expect(f.stop).not.toHaveBeenCalled();
 const physical=deferred<void>();f.stop.mockImplementation(()=>physical.promise);let done=false;
 const p=f.controller.execute({action:'CANCEL',platform:'XIAOHONGSHU',flowId:f.getFlowId()}).then((v:any)=>{done=true;return v;});await Promise.resolve();expect(done).toBe(false);
 physical.resolve();expect(await p).toEqual({state:'CANCELLED',flowId:f.getFlowId()});expect(f.close).toHaveBeenCalled();
});
it('strict renderer commands reject identity, profile paths and claimed status',async()=>{
 const f=fixture();for(const extra of [{profile_path:'C:/private'},{account_public_id:account},{status:'CONNECTED'},{device_id:id(1)}])expect((await f.controller.execute({action:'OPEN',platform:'XIAOHONGSHU',...extra})).state).toBe('INVALID_REQUEST');
 expect(f.login.start).not.toHaveBeenCalled();
});
