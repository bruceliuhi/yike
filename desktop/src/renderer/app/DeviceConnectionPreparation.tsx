import {createContext, useContext, useEffect, useRef, useState, type ReactNode} from 'react';
import {deviceIdentityStatusSchema, type DeviceIdentityRetry, type DeviceIdentityStatus} from '../../shared/deviceIdentity';
import type {Session} from '../domain/models';
import type {DeviceIdentityApi} from '../services/deviceIdentity';
import {Button, Notice} from '../components/ui';
import {boundedRequest} from './boundedRequest';

type Preparation = {ready:boolean; state:DeviceIdentityStatus['state']; pending:boolean; message:string; retry?:()=>void};
const Context = createContext<Preparation | null>(null);
export const useDeviceConnectionPreparation = () => useContext(Context);

/** Present the same runner inside a focus-trapped dialog as well as globally. */
export function DeviceConnectionPreparationNotice() {
  const preparation = useDeviceConnectionPreparation();
  if (!preparation || preparation.ready) return null;
  return <Notice tone={preparation.pending ? 'info' : 'warning'} action={preparation.retry ?
    <Button onClick={preparation.retry}>重试</Button> : undefined}>
    {preparation.message}
  </Notice>;
}

/** UI readiness is only an observation. Main still authorizes each device operation. */
export function DeviceConnectionPreparation({api, session, confirmed, children}: {
  api?:DeviceIdentityApi; session:Session; confirmed:boolean; children:ReactNode;
}) {
  const [observation,setObservation] = useState<{
    api:DeviceIdentityApi; session:Session; state:DeviceIdentityStatus['state']; pending:boolean;
  } | null>(null);
  const active = !!api && confirmed && session.authenticated;
  const current = active && observation?.api === api && observation.session === session ? observation : null;
  const state = current?.state ?? (active ? 'NOT_PREPARED' : 'SIGNED_OUT');
  const pending = active && (current?.pending ?? true);
  const request = useRef<AbortController | null>(null);
  const run = async (options:DeviceIdentityRetry) => {
    if (!api || !active || request.current) return;
    const abort = new AbortController();
    request.current = abort;
    setObservation({api,session,state:'NOT_PREPARED',pending:true});
    try {
      const result = await boundedRequest(async signal => {
        for (let attempt=0; ; attempt++) {
          // Timeout/unmount stops UI follow-ups, not an already-dispatched IPC.
          if (signal.aborted) throw new Error('stopped');
          // BUSY means this operation did not start. Preserve the user's exact
          // original retry consent; any UNKNOWN below returns without a loop.
          const value = deviceIdentityStatusSchema.parse(await api.prepare(options));
          if (value.state !== 'BUSY' || attempt === 2 || signal.aborted) return value;
          await new Promise<void>(resolve => {
            const finish = () => {clearTimeout(timer);signal.removeEventListener('abort',finish);resolve();};
            const timer = setTimeout(finish,1000);
            signal.addEventListener('abort',finish,{once:true});
            if (signal.aborted) finish();
          });
        }
      }, {signal:abort.signal,timeoutMs:90_000,timeoutMessage:'连接准备尚未完成。'});
      if (!abort.signal.aborted) setObservation({api,session,state:result.state,pending:false});
    } catch {
      if (!abort.signal.aborted) setObservation({api,session,state:'FAILED',pending:false});
    } finally {
      if (request.current === abort) request.current = null;
    }
  };
  useEffect(() => {
    if (active) void run({});
    return () => {request.current?.abort();request.current=null;};
  }, [api, session, active]);
  const stopped = ['REVOKED','KEY_MISSING','KEY_MISMATCH','SIGNED_OUT','SESSION_CHANGED'].includes(state);
  const message = pending ? '正在准备连接…' : stopped ? state === 'SIGNED_OUT' || state === 'SESSION_CHANGED' ? '登录状态已变化，请重新登录。' : '连接暂不可用，请联系支持。' : '连接准备尚未完成，请重试。';
  const retry = active && !pending && !stopped ? ()=>void run(state === 'REGISTRATION_UNKNOWN' ? {retryRegistration:true} : state === 'PROOF_UNKNOWN' ? {retryProof:true} : {}) : undefined;
  return <Context.Provider value={api ? {ready:active && state === 'READY' && !pending,state,pending,message,retry} : null}>
    {active && state !== 'READY' && <div className="connection-preparation" aria-live="polite">
      <DeviceConnectionPreparationNotice />
    </div>}
    {children}
  </Context.Provider>;
}
