import {randomUUID} from 'node:crypto';
import {z} from 'zod';
import {platformConnectionCommandSchema, platformConnectionResultSchema, connectionRegistryRowSchema,
  platformLoginFailureSchema, type PlatformLoginFailure, type PlatformConnectionResult, type ConnectionRegistryRow} from '../shared/platformConnection';
import {validNativeAccount, type NativeLoginPlatform} from '../shared/platformAccount';
import {parseConnectionReceipt, type ConnectionOperation} from '../shared/connectionOperation';
import type {createDeviceIdentityController, DeviceWorkerScope} from './deviceIdentityController';
import type {createConnectionProfileStore, ConnectionProfileScope, ConnectionProfileRecord} from './connectionProfileStore';

type Observation={account_public_id:string;checked_at:string};
type LoginRun={opened:Promise<void>;completed:Promise<Observation>;stop():Promise<void>};
export interface PlatformConnectionControllerOptions {
  serviceOrigin:string;
  identity:Pick<ReturnType<typeof createDeviceIdentityController>,'openWorkerScope'|'getStatus'>;
  store:ReturnType<typeof createConnectionProfileStore>;
  login:{start(input:{profileId:string;platform?:NativeLoginPlatform;signal?:AbortSignal;inspectOnly?:boolean}):LoginRun};
  now?:()=>number;
}
type Flow={id:string;platform:NativeLoginPlatform;record:ConnectionProfileRecord;scope:DeviceWorkerScope;profileScope:ConnectionProfileScope;run:LoginRun;
  observation:Observation|null;loginError:PlatformLoginFailure|null;cancelled:boolean;checking:boolean;
  timer:ReturnType<typeof setInterval>|null;stopping:Promise<void>|null};
const rowsSchema=z.object({items:z.array(connectionRegistryRowSchema).max(10000)}).strict();
const failed=(error:Extract<PlatformConnectionResult,{state:'FAILED'}>['error']='CONNECTION_FAILED'):PlatformConnectionResult=>({state:'FAILED',error});
class FlowFailure extends Error {constructor(readonly result:PlatformConnectionResult){super('CONNECTION_FLOW_FAILED');}}

/** The main process owns identity, profile and immutable request IDs; renderer owns only the user's action. */
export function createPlatformConnectionController({serviceOrigin,identity,store,login,now=Date.now}:PlatformConnectionControllerOptions) {
  let active:Flow|null=null,opening=false,shuttingDown=false;
  function current(f:Flow) {
    const device=identity.getStatus();
    return !shuttingDown && active===f && !f.cancelled && f.scope.session.isCurrent() && device.state==='READY' &&
      device.deviceId===f.scope.device.deviceId && device.credentialVersion===f.scope.device.credentialVersion;
  }
  function guard(f:Flow) {if(!current(f))throw new FlowFailure({state:'SESSION_CHANGED'});}
  function guardFresh(f:Flow) {
    guard(f);
    if(f.observation && (now()-Date.parse(f.observation.checked_at)>120000 || Date.parse(f.observation.checked_at)-now()>5000))throw new FlowFailure(failed('LOGIN_EXPIRED'));
  }
  function loginStatus(f:Flow):PlatformConnectionResult {
    guard(f);
    if(f.loginError)return failed(f.loginError);
    if(!f.observation)return {state:'WAITING_LOGIN',flowId:f.id};
    const {account_public_id,checked_at}=f.observation;
    if(!validNativeAccount(f.platform,account_public_id) || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(checked_at) || !Number.isFinite(Date.parse(checked_at)))return failed();
    guardFresh(f);
    return {state:'LOGIN_READY',flowId:f.id};
  }
  function stop(f:Flow):Promise<void> {
    if(f.stopping)return f.stopping;
    f.cancelled=true;
    if(f.timer){clearInterval(f.timer);f.timer=null;}
    f.stopping=Promise.resolve().then(()=>f.run.stop()).finally(()=>f.scope.close());
    // A failed physical stop stays poisoned, including on a later OPEN or shutdown.
    void f.stopping.catch(()=>{});
    return f.stopping;
  }
  async function readRows(f:Flow):Promise<ConnectionRegistryRow[]> {
    guard(f);
    const response=await f.scope.transport.requestConnection({operation:'connections.current'});guard(f);
    if(!response.ok)throw new FlowFailure({state:'UNKNOWN',flowId:f.id});
    const rows=rowsSchema.parse(response.data).items;
    if(new Set(rows.map(r=>r.connection_id)).size!==rows.length)throw new Error('INVALID_CONNECTION_ROWS');
    return rows;
  }
  async function stopReader(f:Flow) {
    const stopping=f.run.stop();
    try {await stopping;guard(f);}
    catch(error) {
      if(error instanceof FlowFailure)throw error;
      f.cancelled=true;if(f.timer){clearInterval(f.timer);f.timer=null;}
      f.stopping=stopping.finally(()=>f.scope.close());void f.stopping.catch(()=>{});
      throw new FlowFailure(failed('SOURCE_STOP_FAILED'));
    }
  }
  async function refreshObservation(f:Flow,previous:Observation):Promise<Observation> {
    // CHECK is the user's action. STATUS never launches a reader or writes.
    await stopReader(f);guard(f);
    f.run=login.start({profileId:f.record.profileId,platform:f.platform,inspectOnly:true});
    let observed:Observation;
    try {observed=await f.run.completed;guard(f);}
    catch(error) {
      if(error instanceof FlowFailure)throw error;
      await stopReader(f);
      const code=platformLoginFailureSchema.safeParse(error instanceof Error?error.message:null);
      throw new FlowFailure(failed(code.success?code.data:'CONNECTION_FAILED'));
    }
    if(!validNativeAccount(f.platform,observed.account_public_id) || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(observed.checked_at) ||
       !Number.isFinite(Date.parse(observed.checked_at)))throw new Error('INVALID_LOGIN_OBSERVATION');
    if(observed.account_public_id!==previous.account_public_id)throw new FlowFailure(failed('ACCOUNT_MISMATCH'));
    f.observation=observed;guardFresh(f);return observed;
  }
  async function persist(f:Flow,op:ConnectionOperation) {
    guardFresh(f);f.record=await store.setOperation(f.profileScope,f.record.flowId,op);guardFresh(f);
    return op;
  }
  async function submitOrRecover(f:Flow,op:ConnectionOperation) {
    guardFresh(f);
    let response=await f.scope.transport.requestConnection({operation:'connections.receipt',payload:{request_id:op.request_id}});guardFresh(f);
    // CHECK is an explicit user retry, using precisely the already-persisted original body and UUID.
    if(!response.ok && response.status===404) {
      response=await f.scope.transport.requestConnection({operation:'connections.apply',payload:op});guardFresh(f);
    }
    if(!response.ok)throw new FlowFailure({state:'UNKNOWN',flowId:f.id});
    const receipt=parseConnectionReceipt(response.data,op);
    if(receipt.state!=='SUCCEEDED') {
      f.record=await store.resolve(f.profileScope,f.record.flowId);guard(f);
      throw new FlowFailure(failed());
    }
    return receipt;
  }
  async function check(f:Flow):Promise<PlatformConnectionResult> {
    guard(f);
    if(f.loginError){const error=f.loginError;await stop(f);return failed(error);}
    if(!f.observation)return {state:'WAITING_LOGIN',flowId:f.id};
    let observation=f.observation;const checked=Date.parse(observation.checked_at);
    if(!validNativeAccount(f.platform,observation.account_public_id) || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(observation.checked_at) || !Number.isFinite(checked))throw new Error('INVALID_LOGIN_OBSERVATION');
    if(checked-now()>5000)return failed('LOGIN_EXPIRED');
    if(now()-checked>120000)observation=await refreshObservation(f,observation);
    const record=await store.read(f.profileScope);guard(f);
    if(!record || record.flowId!==f.record.flowId)throw new Error('CONNECTION_PROFILE_CHANGED');
    f.record=record;
    if(record.registration && record.registration.account_public_id!==observation.account_public_id)return failed('ACCOUNT_MISMATCH');
    let registration=record.registration;
    if(!registration) {
      const rows=await readRows(f);
      const matches=rows.filter(r=>r.device_id===f.scope.device.deviceId && r.platform===f.platform && r.account_public_id===observation.account_public_id);
      if(matches.length>1)throw new Error('AMBIGUOUS_CONNECTION');
      registration=await persist(f,{request_id:randomUUID(),action:'REGISTER',device_id:f.scope.device.deviceId,connection_id:null,
        expected_connection_version:matches[0]?.connection_version??0,platform:f.platform,account_public_id:observation.account_public_id,
        session_ref:`vault://platform/${record.profileId}`});
    }
    const registered=await submitOrRecover(f,registration);
    const verification=f.record.verification??await persist(f,{...registration,request_id:randomUUID(),action:'VERIFY',
      connection_id:registered.connection_id!,expected_connection_version:registered.connection_version!});
    // Protected storage must not combine a prior VERIFY with a different registration receipt.
    if(verification.connection_id!==registered.connection_id || verification.expected_connection_version!==registered.connection_version)throw new Error('CONNECTION_RECEIPT_CHANGED');
    const verified=await submitOrRecover(f,verification);
    const rows=await readRows(f);
    const connection=rows.find(r=>r.connection_id===verified.connection_id && r.device_id===f.scope.device.deviceId &&
      r.platform===f.platform && r.account_public_id===observation.account_public_id && r.connection_version===verified.connection_version && r.status==='CONNECTED');
    // The historical receipt is not current authority. Version also fences changes to the private session_ref.
    f.record=await store.resolve(f.profileScope,f.record.flowId);guardFresh(f);
    return connection?{state:'CONNECTED',flowId:f.id,connection}:failed('CURRENT_CONNECTION_CHANGED');
  }
  return {
    async execute(input:unknown):Promise<PlatformConnectionResult> {
      const parsed=platformConnectionCommandSchema.safeParse(input);
      if(!parsed.success)return {state:'INVALID_REQUEST'};
      if(shuttingDown)return {state:'SERVICE_UNAVAILABLE'};
      const command=parsed.data;
      if(command.action==='OPEN') {
        if(opening || active?.checking)return {state:'BUSY'};
        opening=true;let openedScope:DeviceWorkerScope|null=null;
        try {
          if(active){await stop(active);active=null;}
          const captured=await identity.openWorkerScope();
          if(!captured.ok)return captured.state==='FAILED'?failed():{state:captured.state};
          openedScope=captured.scope;
          const profileScope:ConnectionProfileScope={serviceOrigin,userId:openedScope.session.userId,deviceId:openedScope.device.deviceId,platform:command.platform};
          const record=await store.open(profileScope);
          if(shuttingDown || !openedScope.session.isCurrent()){openedScope.close();return {state:'SESSION_CHANGED'};}
          const device=identity.getStatus();
          if(device.state!=='READY' || device.deviceId!==openedScope.device.deviceId || device.credentialVersion!==openedScope.device.credentialVersion){openedScope.close();return {state:'SESSION_CHANGED'};}
          const run=login.start({profileId:record.profileId,platform:command.platform});
          const f:Flow={id:randomUUID(),platform:command.platform,record,scope:openedScope,profileScope,run,observation:null,loginError:null,cancelled:false,checking:false,timer:null,stopping:null};
          active=f;
          void run.completed.then(value=>{if(current(f))f.observation=value;},error=>{
            const parsed=platformLoginFailureSchema.safeParse(error instanceof Error?error.message:null);
            f.loginError=parsed.success?parsed.data:'CONNECTION_FAILED';
          });
          f.timer=setInterval(()=>{if(!current(f))void stop(f).catch(()=>{});},100);f.timer.unref?.();
          try {await run.opened;guard(f);return {state:'OPENED',flowId:f.id};}
          catch {await stop(f);return failed(f.loginError??'CONNECTION_FAILED');}
        } catch {
          if(!active)openedScope?.close();
          return failed(active?.stopping?'SOURCE_STOP_FAILED':'CONNECTION_FAILED');
        } finally {opening=false;}
      }
      const f=active;
      if(!f || command.flowId!==f.id || command.platform!==f.platform)return {state:'INVALID_REQUEST'};
      if(command.action==='STATUS') {
        try {return loginStatus(f);}
        catch(e) {return e instanceof FlowFailure?e.result:failed();}
      }
      if(command.action==='CANCEL') {
        try {await stop(f);if(active===f)active=null;return {state:'CANCELLED',flowId:command.flowId};}
        catch {return failed('SOURCE_STOP_FAILED');}
      }
      if(f.checking || opening)return {state:'BUSY'};
      f.checking=true;
      try {return platformConnectionResultSchema.parse(await check(f));}
      catch(e) {return e instanceof FlowFailure?e.result:failed(f.stopping?'SOURCE_STOP_FAILED':'CONNECTION_FAILED');}
      finally {f.checking=false;}
    },
    async shutdown() {shuttingDown=true;if(active)await stop(active);},
  };
}
