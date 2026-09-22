import {useEffect, useRef, useState} from 'react';
import {deviceIdentityStatusSchema, type DeviceIdentityRetry, type DeviceIdentityStatus} from '../../../shared/deviceIdentity';
import {boundedRequest} from '../../app/boundedRequest';
import {Button, Notice} from '../../components/ui';
import type {DeviceIdentityApi} from '../../services/deviceIdentity';
export type {DeviceIdentityApi} from '../../services/deviceIdentity';
export const deviceIdentityLabels: Readonly<Record<DeviceIdentityStatus['state'], string>> = {
  NOT_PREPARED:'尚未核验本机身份', READY:'上次身份核验通过',
  REGISTRATION_UNKNOWN:'设备登记结果未知', PROOF_UNKNOWN:'设备核验结果未知',
  REVOKED:'本机身份已撤销，请联系支持', KEY_MISSING:'本机设备暂不可用，请联系支持',
  KEY_MISMATCH:'本机设备暂不可用，请联系支持', SESSION_CHANGED:'会话已变化，请重新核验',
  SIGNED_OUT:'请先登录当前账号', BUSY:'已有身份操作正在处理，请稍后核对',
  SERVICE_UNAVAILABLE:'客户服务暂不可用，请稍后核对',
  INVALID_REQUEST:'请求未被接受，请重新核验', FAILED:'核验结果尚未确认，请重新核对',
};
export function DeviceIdentityPanel({api, scope}: {api: DeviceIdentityApi; scope: string}) {
  const [status,setStatus] = useState<DeviceIdentityStatus>({state:'NOT_PREPARED'});
  const [busy,setBusy] = useState(true);
  const [confirmed,setConfirmed] = useState(false);
  const generation = useRef(0);
  const pending = useRef(false);
  useEffect(() => {
    const id = ++generation.current;
    pending.current = true; setBusy(true); setConfirmed(false); setStatus({state:'NOT_PREPARED'});
    void boundedRequest(()=>api.getStatus(),{timeoutMs:15_000,timeoutMessage:'状态读取超时'}).then(value=> {
      if (id === generation.current) setStatus(deviceIdentityStatusSchema.parse(value));
    }).catch(()=>{if(id === generation.current) setStatus({state:'FAILED'});})
      .finally(()=>{if(id === generation.current){pending.current=false;setBusy(false);}});
    return ()=>{generation.current++;};
  },[api,scope]);
  const unknown = status.state === 'REGISTRATION_UNKNOWN' || status.state === 'PROOF_UNKNOWN';
  const stopped = ['KEY_MISSING','KEY_MISMATCH','REVOKED','SIGNED_OUT'].includes(status.state);
  async function prepare(retry: boolean) {
    if (pending.current || stopped || (!unknown || retry) && !confirmed) return;
    const options:DeviceIdentityRetry = retry ? status.state === 'REGISTRATION_UNKNOWN' ? {retryRegistration:true} : {retryProof:true} : {};
    const id=++generation.current;
    pending.current=true;setBusy(true);setConfirmed(false);
    try {
      const value=await boundedRequest(()=>api.prepare(options),{timeoutMs:90_000,timeoutMessage:'身份核验结果未知'});
      if(id === generation.current) setStatus(deviceIdentityStatusSchema.parse(value));
    } catch {if(id === generation.current) setStatus({state:'FAILED'});}
    finally {if(id === generation.current){pending.current=false;setBusy(false);}}
  }
  return <section aria-label="本机设备身份">
    <p role="status">{deviceIdentityLabels[status.state]}</p>
    <p className="field-hint">本机身份核验只用于设备授权，不代表平台已连接或使用授权已激活。</p>
    {unknown && <Notice>请先核对原请求；核对不会重复登记，重试需再次明确确认。</Notice>}
    {!stopped && <>
      {unknown && <Button disabled={busy} onClick={()=>void prepare(false)}>核对原请求</Button>}
      <label className="checkbox-row"><input type="checkbox" checked={confirmed} disabled={busy} onChange={event=>setConfirmed(event.target.checked)}/>
        {unknown ? '确认重试同一原请求，不创建新的设备身份' : '确认在当前账号下核验本机设备'}
      </label>
      <Button loading={busy} disabled={busy || !confirmed} onClick={()=>void prepare(unknown)}>
        {unknown ? '确认后重试原请求' : '核验本机设备'}
      </Button>
    </>}
  </section>;
}
