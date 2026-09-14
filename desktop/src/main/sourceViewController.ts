import {expectedRawCandidateEvidenceSchema} from '../shared/rawCandidateEvidence';
import {resolveXhsSourceTarget} from './xhsSourceTarget';
import {resolveCollectionAccount} from './collectionAccountBinding';
import type {createDeviceIdentityController,DeviceWorkerScope} from './deviceIdentityController';
import type {createConnectionProfileStore} from './connectionProfileStore';

import type {SourceViewResult} from '../shared/sourceView';
export interface SourceViewRun {opened:Promise<void>;completed:Promise<void>;stop():Promise<void>}
export interface SourceViewStart {profileId:string;expectedAccount:string;noteId:string;authorId:string|null;originalQuery:string|null;signal:AbortSignal}
export interface SourceViewControllerOptions {
  serviceOrigin:string;
  identity:Pick<ReturnType<typeof createDeviceIdentityController>,'openWorkerScope'|'getStatus'|'requestApi'>;
  store:Pick<ReturnType<typeof createConnectionProfileStore>,'read'>;
  driver:{start(input:SourceViewStart):SourceViewRun};
}
type Flow={scope:DeviceWorkerScope;run:SourceViewRun;abort:()=>void;timer:ReturnType<typeof setInterval>|null;stopping:Promise<void>|null;released:boolean};
/** Viewing is not evidence verification or consent to contact. No write API is used. */
export function createSourceViewController(options:SourceViewControllerOptions) {
  let active:Flow|null=null,closed=false,poisoned=false,opening:Promise<void>|null=null;
  const failed=():SourceViewResult=>({state:'FAILED',error:poisoned?'SOURCE_STOP_FAILED':'SOURCE_VIEW_UNAVAILABLE'});
  function current(scope:DeviceWorkerScope) {
    const status=options.identity.getStatus();
    return !closed && !!scope.signal && !scope.signal.aborted && scope.session.isCurrent() && status.state==='READY' &&
      status.deviceId===scope.device.deviceId && status.credentialVersion===scope.device.credentialVersion;
  }
  function guard(scope:DeviceWorkerScope) {if(!current(scope))throw new Error('SOURCE_VIEW_UNAVAILABLE');}
  function release(flow:Flow) {
    if(flow.released)return;flow.released=true;
    if(flow.timer)clearInterval(flow.timer);
    flow.scope.signal?.removeEventListener('abort',flow.abort);
    flow.scope.close();if(active===flow)active=null;
  }
  function stop(flow:Flow):Promise<void> {
    if(flow.stopping)return flow.stopping;
    flow.stopping=Promise.resolve().then(()=>flow.run.stop()).catch(()=>{poisoned=true;throw new Error('SOURCE_STOP_FAILED');}).finally(()=>release(flow));
    void flow.stopping.catch(()=>{});return flow.stopping;
  }
  return {
    async open(input:unknown):Promise<SourceViewResult> {
      if(closed || poisoned)return failed();
      if(active || opening)return {state:'BUSY'};
      let finish!:()=>void;opening=new Promise<void>(resolve=>{finish=resolve;});
      let scope:DeviceWorkerScope|null=null,flow:Flow|null=null;
      try {
        const binding=expectedRawCandidateEvidenceSchema.parse(input);
        const result=await options.identity.openWorkerScope();if(!result.ok)return failed();
        scope=result.scope;guard(scope);
        const response=await options.identity.requestApi({operation:'candidates.rawEvidence',payload:{candidateId:binding.candidateId}});guard(scope);
        if(!response.ok)throw new Error();
        const target=resolveXhsSourceTarget(response.data,binding);
        if(target.deviceId!==scope.device.deviceId)throw new Error();
        const account=await resolveCollectionAccount({serviceOrigin:options.serviceOrigin,scope,store:options.store,target:target.connection});guard(scope);
        const run=options.driver.start({profileId:account.profileId,expectedAccount:account.accountPublicId,noteId:target.noteId,
          authorId:target.originalAuthorId,originalQuery:target.query,signal:scope.signal!});
        flow={scope,run,abort:()=>{},timer:null,stopping:null,released:false};
        const owned=flow;active=owned;
        owned.abort=()=>{void stop(owned).catch(()=>{});};
        scope.signal!.addEventListener('abort',owned.abort,{once:true});
        owned.timer=setInterval(()=>{if(!current(owned.scope))owned.abort();},500);
        void run.completed.then(()=>{if(!owned.stopping)release(owned);},()=>stop(owned)).catch(()=>{});
        guard(scope);await run.opened;guard(scope);
        if(owned.released || owned.stopping)throw new Error();
        return {state:'OPENED',sourceKind:target.sourceKind};
      } catch(error) {
        if(flow){try{await stop(flow);}catch{/* fixed cleanup failure below */}}
        if(!poisoned && !closed && error instanceof Error && error.message==='XHS_SOURCE_BUSY')return {state:'BUSY'};
        return failed();
      } finally {
        if(scope && !flow)scope.close();opening=null;finish();
      }
    },
    async shutdown() {
      closed=true;
      if(active)await stop(active);
      if(opening)await opening;
      if(active)await stop(active);
      if(poisoned)throw new Error('SOURCE_STOP_FAILED');
    },
  };
}
