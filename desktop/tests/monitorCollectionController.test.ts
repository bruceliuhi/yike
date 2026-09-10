import {expect,it,vi} from 'vitest';
import {createMonitorCollectionController} from '../src/main/monitorCollectionController';
const id=(n:number)=>`00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
const schedule={kind:'interval',times:[],interval:1,start:'09:00',end:'18:00',timezone:'Asia/Shanghai',policyVersion:1};
const target={platform:'BILIBILI',access_mode:'PLATFORM_ACCOUNT',connection_id:id(5),connection_version:1};
const plan={plan_id:id(1),profile_version_id:id(2),strategy_version_id:id(3),configuration_sha256:'a'.repeat(64),schedule,state:'ACTIVE',revision:1,next_due_at:'2026-09-11T10:00:00Z',execution_status:'NOT_CONNECTED'};
function fixture(){
 let current=true,sessionId=id(20);const calls:any[]=[];let override:((input:any)=>any)|null=null;
 const scope={session:{userId:'owner',get sessionId(){return sessionId;},isCurrent:()=>current},device:{deviceId:id(6),credentialVersion:1},transport:{requestExecution:vi.fn(async(input:any)=>{
  if(override){const value=override(input);if(value)return value;}
  calls.push(input);if(input.operation==='monitor.support')return {ok:true,status:200,data:{schema_version:'monitor-runtime-support-v1',mode:'three-platform-monitor-v1'}};
  if(input.operation==='monitor.list')return {ok:true,status:200,data:{schema_version:'monitor-plans-v1',plans:[plan],execution_status:'NOT_CONNECTED'}};
  if(input.operation==='monitor.pulse')return {ok:true,status:200,data:{schema_version:'monitor-runtime-v1',plan_id:id(1),plan_revision:1,state:'READY',server_time:'2026-09-11T09:00:00Z',next_due_at:'2026-09-11T10:00:00Z',occurrence:{id:id(7),scheduled_at:'2026-09-11T09:00:00Z',expires_at:'2026-09-11T09:01:30Z',start_request:{schema_version:'execution-runtime-v1',request_id:id(8),operation:'START',device_id:id(6),credential_version:1,profile_version_id:id(2),strategy_version_id:id(3),configuration_sha256:'a'.repeat(64),targets:[target]},task_id:null}}};
  throw new Error('unexpected');})},close:vi.fn()};
 const identity={openWorkerScope:vi.fn(async()=>({ok:true,scope})),getStatus:()=>({state:'READY',deviceId:id(6),credentialVersion:1})};
 const foreground={canStart:vi.fn(()=>true),validateMonitorBinding:vi.fn(async()=>true),startMonitor:vi.fn(async()=>({state:'RECORDED'})),cancel:vi.fn(),stop:vi.fn(async()=>{})};
 const controller=createMonitorCollectionController({identity:identity as any,foreground,intervalMs:20_000,autoStart:false});
 return {controller,scope,foreground,calls,invalidate:()=>current=false,relogin:()=>{sessionId=id(21);},respond:(fn:(input:any)=>any)=>override=fn};
}
it('explicit attach then tick pulses with busy truth and runs only the original reserved START',async()=>{
 const f=fixture();expect(await f.controller.execute({action:'ATTACH',planId:id(1),expectedRevision:1,targets:[target],humanConfirmed:true})).toMatchObject({state:'ATTACHED'});
 await f.controller.tick();
 expect(f.calls.find(x=>x.operation==='monitor.pulse').payload.can_start).toBe(true);
 expect(f.foreground.startMonitor).toHaveBeenCalledWith(expect.objectContaining({request_id:id(8)}));
 await f.controller.shutdown();
});
it('busy pulse never opens a second source and session change detaches',async()=>{
 const f=fixture();f.foreground.canStart.mockReturnValue(false);await f.controller.execute({action:'ATTACH',planId:id(1),expectedRevision:1,targets:[target],humanConfirmed:true});
 await f.controller.tick();expect(f.calls.find(x=>x.operation==='monitor.pulse').payload.can_start).toBe(false);expect(f.foreground.startMonitor).not.toHaveBeenCalled();
 f.relogin();await f.controller.tick();expect(f.foreground.cancel).not.toHaveBeenCalled();const list=await f.controller.execute({action:'LIST'});expect(list).toMatchObject({state:'LIST',plans:[{localState:'DETACHED'}]});await f.controller.shutdown();
});

it('unknown CREATE keeps its request and RECEIPT verifies without attaching historical intent',async()=>{
 const f=fixture();f.respond(input=>input.operation==='monitor.create'?{ok:false,status:503,error:'unavailable'}:null);
 const create={action:'CREATE' as const,requestId:id(1),profileVersionId:id(2),strategyVersionId:id(3),targets:[target],humanConfirmed:true as const};
 expect(await f.controller.execute(create)).toEqual({state:'UNKNOWN',requestId:id(1)});
 f.respond(input=>input.operation==='monitor.receipt'?{ok:true,status:200,data:{schema_version:'monitor-plans-v1',request_id:id(1),operation:'CREATE',plan,recorded_at:'2026-09-11T09:00:00Z'}}:null);
 expect(await f.controller.execute({action:'RECEIPT',command:create})).toMatchObject({state:'RECORDED',plan:{localState:'DETACHED'}});
});

it('shutdown fences an in-flight attach before it can mutate local ownership',async()=>{
 const f=fixture();let release!:()=>void;f.foreground.validateMonitorBinding.mockImplementation(()=>new Promise<boolean>(resolve=>{release=()=>resolve(true);}));
 const pending=f.controller.execute({action:'ATTACH',planId:id(1),expectedRevision:1,targets:[target],humanConfirmed:true});while(!release)await new Promise(resolve=>setImmediate(resolve));
 const closing=f.controller.shutdown();release();await closing;expect(await pending).toMatchObject({state:'SESSION_CHANGED'});
 expect(await f.controller.execute({action:'LIST'})).toEqual({state:'SERVICE_UNAVAILABLE'});
});

it('pause works after support is disabled and stops only the exact observed task',async()=>{
 const f=fixture();await f.controller.execute({action:'ATTACH',planId:id(1),expectedRevision:1,targets:[target],humanConfirmed:true});
 const startRequest={schema_version:'execution-runtime-v1',request_id:id(8),operation:'START',device_id:id(6),credential_version:1,profile_version_id:id(2),strategy_version_id:id(3),configuration_sha256:'a'.repeat(64),targets:[target]};
 f.respond(input=>input.operation==='monitor.pulse'?{ok:true,status:200,data:{schema_version:'monitor-runtime-v1',plan_id:id(1),plan_revision:1,state:'RUNNING',server_time:'2026-09-11T09:00:00Z',next_due_at:'2026-09-11T10:00:00Z',occurrence:{id:id(7),scheduled_at:'2026-09-11T09:00:00Z',expires_at:'2026-09-11T09:01:30Z',start_request:startRequest,task_id:id(9)}}}:null);
 await f.controller.tick();f.respond(input=>input.operation==='monitor.support'?{ok:true,status:200,data:{schema_version:'monitor-runtime-support-v1',mode:null}}:input.operation==='monitor.state'?{ok:true,status:200,data:{schema_version:'monitor-plans-v1',request_id:id(10),operation:'SET_STATE',plan:{...plan,state:'PAUSED',revision:2,next_due_at:null},recorded_at:'2026-09-11T09:00:00Z'}}:null);
 expect(await f.controller.execute({action:'SET_STATE',requestId:id(10),planId:id(1),expectedRevision:1,state:'PAUSED',humanConfirmed:true})).toMatchObject({state:'RECORDED'});
 expect(f.foreground.stop).toHaveBeenCalledWith(id(9));expect(f.foreground.stop).not.toHaveBeenCalledWith(undefined);
});

it('failed physical stop keeps exact task visible and never submits PAUSED',async()=>{
 const f=fixture();await f.controller.execute({action:'ATTACH',planId:id(1),expectedRevision:1,targets:[target],humanConfirmed:true});
 const startRequest={schema_version:'execution-runtime-v1',request_id:id(8),operation:'START',device_id:id(6),credential_version:1,profile_version_id:id(2),strategy_version_id:id(3),configuration_sha256:'a'.repeat(64),targets:[target]};
 f.respond(input=>input.operation==='monitor.pulse'?{ok:true,status:200,data:{schema_version:'monitor-runtime-v1',plan_id:id(1),plan_revision:1,state:'RUNNING',server_time:'2026-09-11T09:00:00Z',next_due_at:'2026-09-11T10:00:00Z',occurrence:{id:id(7),scheduled_at:'2026-09-11T09:00:00Z',expires_at:'2026-09-11T09:01:30Z',start_request:startRequest,task_id:id(9)}}}:null);await f.controller.tick();
 f.foreground.stop.mockRejectedValue(new Error('SOURCE_STOP_FAILED'));f.respond(input=>input.operation==='monitor.state'?(()=>{throw new Error('must not submit')})():null);
 expect(await f.controller.execute({action:'SET_STATE',requestId:id(10),planId:id(1),expectedRevision:1,state:'PAUSED',humanConfirmed:true})).toEqual({state:'SERVICE_UNAVAILABLE'});
 const listing=await f.controller.execute({action:'LIST'});expect(listing).toMatchObject({state:'LIST',plans:[{localState:'STOP_UNCONFIRMED',taskId:id(9),lastError:'SOURCE_STOP_FAILED'}]});
});
