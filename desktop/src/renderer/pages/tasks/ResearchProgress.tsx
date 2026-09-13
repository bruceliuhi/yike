import {useEffect,useRef,useState} from 'react';
import {useApp} from '../../app/context';
import {useResource} from '../../app/hooks';
import {boundedRequest} from '../../app/boundedRequest';
import {Button,Notice,ResourceStatus} from '../../components/ui';
import {researchRuntimeStatusSchema,type ResearchRuntimeStatus} from '../../../shared/researchRuntime';
import {useTaskScope} from './useTaskScope';
import {researchIndexLabel} from '../../../shared/researchSourcePlan';
import {researchProgressPresentation} from '../../domain/researchProgressPresentation';
import {ResearchReadEvidence} from './ResearchReadEvidence';

const resourceStates={OPEN:'资源记录仍开放',DRAINING:'等待回执或执行者退出',UNCERTAIN:'资源结果仍待核实',RECORDED:'资源记录已收齐'};
const sourcePhases={NOT_STARTED:'未开始',PENDING:'等待回执',SUCCEEDED:'已入库',FAILED:'失败',UNKNOWN:'结果待核实'};
function progressKey(value:ResearchRuntimeStatus){
  const closeout=value.usage.resourceCloseout;
  return JSON.stringify({...value,usage:{...value.usage,
    resourceCloseout:closeout?{...closeout,asOf:undefined}:undefined}});
}
export function ResearchProgress({taskId,runId,taskStatus,onTerminal}:{taskId:string;runId:string;taskStatus:string;onTerminal?:()=>void}) {
  const {service,navigate}=useApp(),scope=useTaskScope(JSON.stringify([taskId,runId,taskStatus]));
  const controller=useRef<AbortController|null>(null),[busy,setBusy]=useState(false),[message,setMessage]=useState('');
  const callback=useRef(onTerminal);callback.current=onTerminal;
  function parse(raw:unknown) {
    const value=researchRuntimeStatusSchema.parse(raw);
    if(value.taskId!==taskId || value.runId!==runId)throw new Error('研究任务身份不一致');
    return value;
  }
  async function read(signal?:AbortSignal) {
    if(!service.researchRuntime)throw new Error('研究执行服务尚未接通。');
    return parse(await service.researchRuntime.status(taskId,signal));
  }
  const data=useResource(read,[scope.identity,service]);
  const dynamic=data.data?.contractVersion===4;
  // Observation only: never retry advance when a job already owns the server lease.
  useEffect(()=>{
    if(!dynamic||data.data?.phase!=='RUNNING')return;
    const abort=new AbortController();let timer:ReturnType<typeof setTimeout>;
    async function poll(){
      try{
        const next=await boundedRequest(read,{signal:abort.signal,timeoutMessage:'研究状态查询超时。'});
        if(abort.signal.aborted||!scope.current())return;
        data.setData(next);
        if(['COMPLETED','CANCELED'].includes(next.phase))callback.current?.();
        if(next.phase==='RUNNING')timer=setTimeout(poll,2000);
      }catch{
        if(!abort.signal.aborted&&scope.current())setMessage('自动查询暂时中断，请查询原研究状态；不会重新启动任务。');
      }
    }
    timer=setTimeout(poll,2000);
    return ()=>{abort.abort();clearTimeout(timer);};
  },[dynamic,data.data?.phase,scope.identity,service]);
  useEffect(()=>{controller.current=null;setBusy(false);setMessage('');
    return ()=>{controller.current?.abort();};},[scope.identity]);
  async function run() {
    if(controller.current || !data.data?.canAdvance || data.data.newActionsBlocked || !service.researchRuntime || !scope.current())return;
    const abort=new AbortController();controller.current=abort;setBusy(true);setMessage('');
    const current=()=>scope.current() && !abort.signal.aborted;
    try {
      let value=await boundedRequest(read,{signal:abort.signal,timeoutMessage:'研究状态未核实。'});
      if(!current())return;
      data.setData(value);
      if(value.contractVersion===4){
        if(value.canAdvance&&!value.newActionsBlocked){
          value=parse(await boundedRequest(signal=>service.researchRuntime!.advance(taskId,runId,signal),{
            signal:abort.signal,timeoutMessage:'研究启动回执尚未核实。'}));
          if(current())data.setData(value);
        }
        if(current()&&['COMPLETED','CANCELED'].includes(value.phase))callback.current?.();
        return;
      }
      // At most three sources plus 100 original analyses; no background/infinite retry loop.
      const maxSteps=100+(value.sourceProgress?.length??1);
      for(let step=0;step<maxSteps && value.canAdvance && !value.newActionsBlocked;step++){
        const previous=progressKey(value);
        value=parse(await boundedRequest(signal=>service.researchRuntime!.advance(taskId,runId,signal),{
          signal:abort.signal,timeoutMs:80_000,timeoutMessage:'研究推进等待超时。',
        }));
        if(!current())return;
        data.setData(value);
        if(progressKey(value)===previous){setMessage('暂未取得新进度，本轮已停下。请稍后查询原任务，不会循环重试。');break;}
      }
      if(current() && ['COMPLETED','CANCELED'].includes(value.phase))callback.current?.();
    } catch {
      if(!scope.current())return;
      setMessage('本轮推进未确认，已停止继续调用。查询原任务不会重发来源或模型请求。');
      data.setData(undefined);
      // A timeout is not a refund, cancellation, or proof that nothing happened.
      try {const value=await boundedRequest(read,{timeoutMessage:'原研究状态仍未核实。'});if(scope.current())data.setData(value);} catch { /* Retain last confirmed state; explicit refresh remains available. */ }
    } finally {
      if(controller.current===abort)controller.current=null;
      if(scope.current())setBusy(false);
    }
  }
  const value=data.data;
  const presentation=value?researchProgressPresentation(value):null;
  return <section className="panel" aria-label="研究进度">
    <h2>研究进度</h2>
    <ResourceStatus loading={data.loading} error={data.error}/>
    {value && <>
      <p>{value.sourceLabel}</p>
      <h3>{presentation!.title}</h3>
      <p>{presentation!.explanation}</p>
      {value.discovery&&<>
        <p>搜索完成：{value.discovery.searches.succeeded} · 原文读取完成：{value.discovery.reads.succeeded} · 未入候选原文：{value.discovery.unpublishedOriginals}</p>
        <p className="muted">搜索摘要不计原文；超长、超出上限或尚待入库的原文不计候选。需要登录或展开评论的来源需另行授权补查。</p>
      </>}
      {value.sourceProgress&&<table aria-label="逐来源研究进度">
        <thead><tr><th>来源</th><th>状态</th><th>入库 / 配额</th></tr></thead>
        <tbody>{value.sourceProgress.map(row=><tr key={row.sourceId}>
          <td>{researchIndexLabel(row.sourceId)}</td><td>{sourcePhases[row.phase]}</td>
          <td>{row.acceptedOriginals??'待确认'} / {row.recordLimit}</td>
        </tr>)}</tbody>
      </table>}
      <p>入库原文：{value.acceptedOriginals??'尚未确认'} · 已分析：{value.analyzedOriginals} · 已跳过：{value.skippedOriginals}</p>
      <p className="muted">这些是原文与分析进度，不是已确认的商机数量；请打开候选逐条核对出处与购买意向。</p>
      {presentation!.warning&&<Notice tone="warning">{presentation!.warning}</Notice>}
      <p>{presentation!.nextStep}</p>
      {dynamic&&service.researchRuntime?.reads&&<ResearchReadEvidence taskId={taskId} runId={runId}
        reads={service.researchRuntime.reads} onOpen={service.openExternal}/>}
      <details>
        <summary>执行明细</summary>
        {(['sourceReads','modelCalls'] as const).map(resource=>{
          const counts=value.usage[resource];
          return <p key={resource}>{resource==='sourceReads'?'来源许可':'模型许可'}：{counts.issued} · 成功 {counts.succeeded} · 失败 {counts.failed} · 待回执 {counts.pending} · 未知 {counts.unknown}</p>;
        })}
        {value.usage.resourceCloseout?<>
          <p>本次查询：{resourceStates[value.usage.resourceCloseout.state]} · 超期未核实：{value.usage.resourceCloseout.overduePermits}</p>
          <p className="muted">记录截至：{new Date(value.usage.resourceCloseout.asOf).toLocaleString('zh-CN')}。仅表示本次快照，不代表搜贝已结算或余额已释放。</p>
        </>:<p className="muted">服务尚未提供资源收口状态，不能判断记录是否收齐。</p>}
        <p className="muted">许可不等于实际外部调用或费用；实际搜贝待结算。</p>
        {value.stopCode&&<p>停止原因：{value.stopCode}</p>}
      </details>
    </>}
    {message && <Notice tone="warning">{message}</Notice>}
    <div className="task-footer">
      <Button variant="primary" disabled={busy || data.loading || !!data.error || !value?.canAdvance || value.newActionsBlocked}
        onClick={()=>void run()}>{dynamic?'开始研究':'继续研究'}</Button>
      {!dynamic&&<Button disabled={!busy} onClick={()=>{controller.current?.abort();setMessage('已停止本页后续推进，已发出的请求仍需查询结果。');}}>停止本页推进</Button>}
      <Button disabled={busy||data.loading} onClick={()=>void data.reload()}>查询原研究状态</Button>
      <Button onClick={()=>navigate(`/candidates?task=${taskId}`)}>查看原文与分析</Button>
    </div>
    <p className="field-hint">{dynamic?'离开页面不会停止服务端研究；页面仅查询进度。取消整个任务请使用下方取消按钮。':'点击继续后按已确认上限逐步处理；离开页面停止后续推进。取消整个任务请使用下方取消按钮。'}</p>
  </section>;
}
