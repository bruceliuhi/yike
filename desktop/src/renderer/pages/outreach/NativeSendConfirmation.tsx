import {useEffect,useRef,useState} from 'react';
import {z} from 'zod';
import {useApp} from '../../app/context';
import {Button,Modal,Notice} from '../../components/ui';
import type {ContactDraft,Opportunity,PlatformConnection} from '../../domain/models';
import {nativeOutreachBindingSchema,type NativeOutreachBinding,type NativeOutreachResult} from '../../../shared/nativeOutreach';
import {nativeOutreachLedgerKey,readNativeOutreachRecord,writeNativeOutreachRecord,useNativeOutreachRecord,storageMessage} from './nativeOutreachLedger';
import type {YikeDesktopApi} from '../../../shared/contracts';

export function nativeOutreachCommand() {
  const bridge=(window as unknown as {yikeDesktop?:YikeDesktopApi}).yikeDesktop;
  return bridge?.nativeOutreachCommand?.bind(bridge);
}

type Prepared=Extract<NativeOutreachResult,{state:'PREPARED'}>;
const draftFields=['opportunityId','channel','content','savedContent','version','accountId','recipient'] as const;
const messages:Record<string,string>={BUSY:'另一个原生操作尚未结束，请先核对原请求。',SESSION_CHANGED:'登录身份已变化，请返回重新核对。',DEVICE_NOT_READY:'设备尚未就绪，请先完成设备连接。',FLOW_EXPIRED:'确认信息已过期，请返回重新准备。',DRAFT_CHANGED:'已保存草稿已变化，请返回同步后重新准备。',CONNECTION_CHANGED:'连接账号或版本已变化，请返回重新核对。',CHANNEL_UNVERIFIED:'平台渠道尚未核验通过，当前未确认发送。',CONFIRMATION_UNCONFIRMED:'确认队列结果未确定，请核对原请求。',SOURCE_STOP_FAILED:'原生任务清理尚未确认，不能重新发送。'};
const fallback='原生操作未完成，请核对原请求；不会自动重新发送。';
export function NativeSendConfirmation({row,draft,connection,onClose,fingerprint}:{row:Opportunity;draft:ContactDraft;connection?:PlatformConnection;onClose:()=>void;fingerprint:string}) {
  const {session}=useApp();
  const key=nativeOutreachLedgerKey(session,row.id,draft.channel);
  const ledger=useNativeOutreachRecord(key);
  const [snapshot]=useState(()=>({draft:{...draft},fingerprint,key}));
  const [prepared,setPrepared]=useState<Prepared|null>(null),[checked,setChecked]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState(''),[queued,setQueued]=useState(false);
  const active=useRef<string|null>(null),mounted=useRef(false),generation=useRef(0),working=useRef(false);
  const live=useRef({fingerprint,key});live.current={fingerprint,key};
  const changed=snapshot.fingerprint!==fingerprint || snapshot.key!==key;
  const command=nativeOutreachCommand();
  const current=()=>mounted.current && live.current.fingerprint===snapshot.fingerprint && live.current.key===snapshot.key;
  const cancel=(flowId:string)=>{try {void command?.({action:'CANCEL',flowId}).catch(()=>{});}catch {/* Preserve any pending binding. */}};
  useEffect(()=>{mounted.current=true;return ()=>{mounted.current=false;generation.current++;if(active.current)cancel(active.current);};},[]);
  useEffect(()=>{if(changed){setChecked(false);if(active.current){cancel(active.current);active.current=null;}}},[changed]);
  const blocked=!session.authenticated || !session.accountScope || row.sample || row.platform!=='xhs' || draft.channel!=='comment' ||
    draft.opportunityId!==row.id || draft.content!==draft.savedContent || !draft.content.trim() || row.profileStatus!=='CONFIRMED' || row.sourceStatus!=='OPEN' ||
    !connection || connection.platform!=='xhs' || connection.status!=='CONNECTED' || connection.accountId!==draft.accountId || !draft.accountId;
  async function inspect() {
    if(!command || blocked || changed || working.current || ledger.error || ledger.record)return;
    working.current=true;setBusy(true);setError('');const at=generation.current,requestId=crypto.randomUUID();
    try {
      const value=await command({action:'PREPARE',requestId,draft:snapshot.draft});
      if(!current() || at!==generation.current){if(value.state==='PREPARED')cancel(value.flowId);return;}
      if(value.state!=='PREPARED')throw new Error(value.state==='FAILED'?(messages[value.error]||fallback):fallback);
      active.current=value.flowId;
      const binding=nativeOutreachBindingSchema.parse(value.binding),c=value.context;
      if(!z.string().uuid().safeParse(value.flowId).success || binding.requestId!==requestId || binding.tenantId!==session.accountScope?.id ||
        c.ownerUserId!==session.userId || c.accountScope.id!==binding.tenantId || c.contextSha256!==binding.contextSha256 ||
        c.source.platform!=='XIAOHONGSHU' || c.connection.platform!=='XIAOHONGSHU' || c.connection.accountPublicId!==snapshot.draft.accountId ||
        c.profileVersionId!==row.profileVersionId || draftFields.some(k=>c.draft[k]!==snapshot.draft[k]))throw new Error('确认信息与当前草稿或身份不一致，请返回重新准备。');
      setPrepared({...value,binding});setChecked(false);
    }catch(e){if(current()){setError(e instanceof Error && (Object.values(messages).includes(e.message)||e.message===fallback||e.message.startsWith('确认信息与'))?e.message:fallback);if(active.current){cancel(active.current);active.current=null;}}}
    finally {working.current=false;if(current())setBusy(false);}
  }
  function accept(value:NativeOutreachResult,binding:NativeOutreachBinding) {
    if(!current())return;
    if(value.state==='FAILED'){setError(messages[value.error]||fallback);return;}
    if(value.state!=='RESULT' || JSON.stringify(nativeOutreachBindingSchema.parse(value.binding))!==JSON.stringify(binding))throw new Error();
    const r=value.result;
    if((r.state==='RECONCILED'||r.state==='RESULT_RECORDED') && r.serverAccepted && r.receipt.requestId===binding.requestId &&
      (r.receipt.claimId===undefined||r.receipt.claimId===binding.claimId) && r.receipt.dispatchAllowed===false) {
      const receipt=r.receipt;
      if(receipt.state==='SENT' && receipt.deliveryConfirmed===true && receipt.evidenceAuthority==='DEVICE_ATTESTED_PLATFORM_RECEIPT') {
        writeNativeOutreachRecord(key,{binding,state:'SENT'},binding);setMessage('渠道已确认发送成功，不会重复发送。');setQueued(false);return;
      }
      if(receipt.state==='CANCELLED' || receipt.state==='FAILED' && receipt.confirmedNotDelivered===true && receipt.evidenceAuthority==='DEVICE_ATTESTED_PLATFORM_RECEIPT') {
        writeNativeOutreachRecord(key,null,binding);setPrepared(null);setChecked(false);setQueued(false);setMessage(receipt.state==='CANCELLED'?'原请求已取消；如需发送，请重新准备并确认。':'渠道已确认未送达；如需发送，请重新准备并确认。');return;
      }
      setQueued(receipt.state==='QUEUED');
    }
    setMessage('发送结果尚未确定，原请求保护已保留；只能核对或补报结果，不会重新发送。');
  }
  async function confirm() {
    if(!command || !prepared || !checked || blocked || changed || working.current || ledger.record || ledger.error)return;
    working.current=true;setBusy(true);setError('');
    try {
      // Synchronous write + exact readback must finish before the native CONFIRM.
      writeNativeOutreachRecord(key,{binding:prepared.binding,state:'PENDING'});
      const value=await command({action:'CONFIRM',flowId:prepared.flowId,humanConfirmed:true});
      if(!current())return;active.current=null;accept(value,prepared.binding);
    }catch(e){if(current())setError(e instanceof Error && e.message===storageMessage?storageMessage:fallback);}
    finally {working.current=false;if(current())setBusy(false);}
  }
  async function recover(action:'RECONCILE'|'RESUME_RESULT'|'CANCEL_QUEUED') {
    if(!command || working.current || changed || !session.authenticated || ledger.error)return;
    working.current=true;setBusy(true);setError('');
    try {
      const original=readNativeOutreachRecord(key);if(!original || original.state!=='PENDING')return;
      const value=await command({action,binding:original.binding});
      if(current())accept(value,original.binding);
    }catch {if(current())setError(fallback);}
    finally {working.current=false;if(current())setBusy(false);}
  }
  const close=()=>{mounted.current=false;generation.current++;if(active.current){cancel(active.current);active.current=null;}onClose();};
  const c=prepared?.context;
  return <Modal title="确认发送" onClose={close} footer={<><Button onClick={close}>返回修改</Button><Button variant="primary" loading={busy} disabled={!prepared||!checked||blocked||changed||!!ledger.record||!!ledger.error} onClick={()=>void confirm()}>确认并发送</Button></>}>
    <p className="muted">核对当前已保存的全文。平台与账号将在你确认后实际核验，准备信息不代表已发送。</p>
    {c && !changed && <><dl className="detail-list"><div><dt>渠道</dt><dd>小红书 · 评论</dd></div><div><dt>发送账号</dt><dd>{c.connection.accountPublicId}</dd></div><div><dt>收件对象</dt><dd>{c.target.authorPublicId}</dd></div><div><dt>关联来源</dt><dd>{c.source.url}</dd></div></dl><blockquote className="coach-quote">{c.source.excerpt}</blockquote><h3>发送内容预览</h3><pre className="draft-preview">{c.draft.content}</pre></>}
    {!prepared && !ledger.record && !ledger.error && !blocked && !changed && <Button loading={busy} onClick={()=>void inspect()}>核对发送信息</Button>}
    {!ledger.record && <label className="checkbox-label"><input type="checkbox" checked={checked&&!changed} disabled={!prepared||busy||changed||blocked} onChange={e=>setChecked(e.target.checked)}/>我已核对联系对象、发送账号和内容</label>}
    {changed?<Notice tone="warning">内容、连接或身份已变化，原操作已停止，请返回重新核对；未决记录仍保留。</Notice>:blocked?<Notice tone="warning">请先登录，保存完整草稿，并选择与商机匹配的已连接小红书账号。</Notice>:null}
    {ledger.record?.state==='SENT' && <Notice>此版本已确认发送；不能重复首联，修改草稿不会解除保护。</Notice>}
    {ledger.record?.state==='PENDING' && <><Notice tone="warning">原请求待核对。关闭或修改草稿不会解除发送保护。</Notice><p className="muted text-small">原请求编号：{ledger.record.binding.requestId}</p><div className="inline-actions"><Button disabled={busy||changed} onClick={()=>void recover('RECONCILE')}>核对原发送结果</Button><Button disabled={busy||changed} onClick={()=>void recover('RESUME_RESULT')}>补报原发送结果</Button>{queued&&<Button disabled={busy||changed} onClick={()=>void recover('CANCEL_QUEUED')}>取消原排队请求</Button>}</div></>}
    {message&&!changed&&<Notice>{message}</Notice>}{(error||ledger.error)&&<Notice tone="error">{error||ledger.error}</Notice>}
  </Modal>;
}
