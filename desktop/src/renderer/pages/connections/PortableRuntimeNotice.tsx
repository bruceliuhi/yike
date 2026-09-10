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
  if(status.state==='PREPARING')return <Notice>正在准备本机运行环境，请稍候。完成后再连接平台账号；此过程不会登录或采集。</Notice>;
  if(status.state==='FAILED')return <Notice tone="error">本机运行环境准备失败，平台操作尚未启用。请重新打开客户端核对；若仍失败，请联系支持，不要手工替换运行文件。</Notice>;
  return <Notice>本机运行环境已准备好。平台账号仍需单独连接，任务仍需你确认后启动。</Notice>;
}
