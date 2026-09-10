import {useEffect,useMemo,useRef,useState} from 'react';
import {Button,Notice} from '../../components/ui';
import type {Opportunity,Session} from '../../domain/models';
import type {ReplyEvidence} from '../../../shared/replyEvidence';
import {nativeReplyResultSchema,type NativeReplyError} from '../../../shared/nativeReply';
import type {YikeDesktopApi} from '../../../shared/contracts';
import {nativeOutreachLedgerKey,readNativeOutreachRecord} from '../outreach/nativeOutreachLedger';
import {isSample} from '../opportunities/OpportunityEvidence';

const errors:Record<NativeReplyError,string>={
  INVALID_REQUEST:'原请求无效，无法同步。',BUSY:'已有原生回复同步正在进行，请稍后再试。',SESSION_CHANGED:'登录身份已变化，请刷新后重试。',
  DEVICE_NOT_READY:'本机设备身份尚未就绪。',CONNECTION_CHANGED:'原平台连接已变化，请重新核实连接。',SOURCE_UNAVAILABLE:'原生回复来源暂不可用。',
  SOURCE_STOP_FAILED:'回复来源未能安全停止，当前同步已阻止。',REPLY_SYNC_FAILED:'原生回复同步失败，请稍后核对。',
};
function bridge(){return (window as unknown as {yikeDesktop?:YikeDesktopApi}).yikeDesktop?.nativeReplyCommand;}

export function NativeReplySync({session,opportunity,evidence,onSynced}:{session:Session;opportunity:Opportunity;evidence:ReplyEvidence[];onSynced:()=>void}){
  const scope=`${session.authenticated}:${session.userId ?? ''}:${session.accountScope?.id ?? ''}:${session.accountScope?.version ?? ''}:${opportunity.id}`;
  const generation=useRef(0),[running,setRunning]=useState<string|null>(null),[message,setMessage]=useState('');
  useEffect(()=>{generation.current+=1;setRunning(null);setMessage('');return()=>{generation.current+=1;};},[scope]);
  const eligible=session.authenticated && !!session.userId && !!session.accountScope && !isSample(opportunity) && opportunity.platform==='xhs';
  const requests=useMemo(()=>{
    if(!eligible)return [];
    const values:string[]=[];
    try {const record=readNativeOutreachRecord(nativeOutreachLedgerKey(session,opportunity.id,'comment'));if(record)values.push(record.binding.requestId);} catch {/* A local hint may be unreadable; main remains authoritative. */}
    for(const row of evidence)if(row.event.kind==='PLATFORM_REPLY' && row.event.platform==='XIAOHONGSHU' && row.event.channel==='comment')values.push(row.event.outreach_request_id);
    return [...new Set(values)];
  },[eligible,session,opportunity.id,evidence]);
  if(!eligible)return null;
  const command=bridge();
  async function sync(requestId:string){
    if(!command || running)return;
    const turn=++generation.current;setRunning(requestId);setMessage('');
    try {
      const parsed=nativeReplyResultSchema.safeParse(await command({action:'SYNC',opportunityId:opportunity.id,requestId}));
      if(turn!==generation.current)return;
      if(!parsed.success || (parsed.data.state==='SYNCED' && parsed.data.requestId!==requestId)){setMessage('本次同步结果未确认，请稍后核对保存证据。');return;}
      const result=parsed.data;
      if(result.state==='SYNCED')setMessage(`${result.coverage==='COMPLETE'?'完整':'部分'}范围读取：${result.observed} 条；保存并核实：${result.recorded} 条（包含去重结果）。`);
      else setMessage(`${errors[result.error]}已保存并核实：${result.recorded} 条（包含去重结果）。`);
      onSynced();
    } catch {if(turn===generation.current)setMessage('本次同步结果未确认，请稍后核对保存证据。');}
    finally {if(turn===generation.current)setRunning(null);}
  }
  return <div>
    <h3>同步小红书公开评论回复</h3>
    {!requests.length?<Notice>需先完成并核实原生联系，才能从原请求同步公开评论回复；这里不能手工填写请求 ID。</Notice>:
      !command?<Notice>请在意客AI桌面客户端中同步原生回复。</Notice>:
      <>{requests.map(requestId=><Button key={requestId} variant="secondary" loading={running===requestId} disabled={running!==null} onClick={()=>sync(requestId)}>同步原请求 {requestId}</Button>)}</>}
    {message && <Notice tone={message.includes('范围读取')?'success':'error'}>{message}</Notice>}
  </div>;
}
