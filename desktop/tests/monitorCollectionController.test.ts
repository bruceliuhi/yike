import {expect,it,vi} from 'vitest';
import {createMonitorCollectionController} from '../src/main/monitorCollectionController';
const id=(n:number)=>`00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
const schedule={kind:'interval',times:[],interval:1,start:'09:00',end:'18:00',timezone:'Asia/Shanghai',policyVersion:1};
const target={platform:'BILIBILI',access_mode:'PLATFORM_ACCOUNT',connection_id:id(5),connection_version:1};
const plan={plan_id:id(1),profile_version_id:id(2),strategy_version_id:id(3),configuration_sha256:'a'.repeat(64),schedule,state:'ACTIVE',revision:1,next_due_at:'2026-09-11T10:00:00Z',execution_status:'NOT_CONNECTED'};
function fixture(){
 let current=true;const calls:any[]=[];
 const scope={session:{userId:'owner',sessionId:id(20),isCurrent:()=>current},device:{deviceId:id(6),credentialVersion:1},transport:{requestExecution:vi.fn(async(input:any)=>{
  calls.push(input);if(input.operation==='monitor.support')return {ok:true,status:200,data:{schema_version:'monitor-runtime-support-v1',mode:'three-platform-monitor-v1'}};
  if(input.operation==='monitor.list')return {ok:true,status:200,data:{schema_version:'monitor-plans-v1',plans:[plan],execution_status:'NOT_CONNECTED'}};
  if(input.operation==='monitor.pulse')return {ok:true,status:200,data:{schema_version:'monitor-runtime-v1',plan_id:id(1),plan_revision:1,state:'READY',server_time:'2026-09-11T09:00:00Z',next_due_at:'2026-09-11T10:00:00Z',occurrence:{id:id(7),scheduled_at:'2026-09-11T09:00:00Z',expires_at:'2026-09-11T09:01:30Z',start_request:{schema_version:'execution-runtime-v1',request_id:id(8),operation:'START',device_id:id(6),credential_version:1,profile_version_id:id(2),strategy_version_id:id(3),configuration_sha256:'a'.repeat(64),targets:[target]},task_id:null}}};
  throw new Error('unexpected');})},close:vi.fn()};
 const identity={openWorkerScope:vi.fn(async()=>({ok:true,scope})),getStatus:()=>({state:'READY',deviceId:id(6),credentialVersion:1})};
 const foreground={canStart:vi.fn(()=>true),validateMonitorBinding:vi.fn(async()=>true),startMonitor:vi.fn(async()=>({state:'RECORDED'})),cancel:vi.fn()};
 const controller=createMonitorCollectionController({identity:identity as any,foreground,intervalMs:20_000,autoStart:false});
 return {controller,scope,foreground,calls,invalidate:()=>current=false};
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
 f.invalidate();await f.controller.tick();expect(f.foreground.cancel).toHaveBeenCalled();await f.controller.shutdown();
});
