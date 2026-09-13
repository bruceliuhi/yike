import {useEffect,useState} from 'react';
import type {YikeDesktopApi} from '../../../shared/contracts';
import type {PortableRuntimeStatus} from '../../../shared/portableRuntime';
import {Notice} from '../../components/ui';
export function PortableRuntimeNotice(){
  const [status,setStatus]=useState<PortableRuntimeStatus|null>(null);
  useEffect(()=>{
    const bridge=(window as unknown as {yikeDesktop?:YikeDesktopApi}).yikeDesktop;
    if(!bridge?.getPortableRuntimeStatus)return;
    let active=true,timer:ReturnType<typeof setTimeout>|undefined;
    async function read(){
      try {const result=await bridge!.getPortableRuntimeStatus!();
        if(!active)return;
        if(!['NOT_REQUIRED','PREPARING','READY','FAILED'].includes(result.state))throw Error();
        setStatus(result);if(result.state==='PREPARING')timer=setTimeout(()=>void read(),1000);
      }catch{if(active)setStatus({state:'FAILED'});}
    }
    void read();return ()=>{active=false;if(timer)clearTimeout(timer);};
  },[]);
  if(!status||status.state==='NOT_REQUIRED')return null;
  if(status.state==='PREPARING')return <Notice>正在准备，请稍候…</Notice>;
  if(status.state==='FAILED')return <Notice tone="error">准备失败，请重新打开客户端；若仍失败，请联系支持。</Notice>;
  return null;
}
