import {useEffect,useState} from 'react';
import {useApp} from '../../app/context';
import {useResource} from '../../app/hooks';
import {Button,PageHeader,Notice,Confirm,ResourceStatus,formatDate} from '../../components/ui';
import {useMonitorCollection} from './useMonitorCollection';
import {useTaskScope} from './useTaskScope';
import {monitorTargets} from '../../domain/monitorCollection';
import {schedulePolicyDescription} from '../../domain/schedule';
import {strategyViewSchema} from '../../../shared/researchStrategies';
import type {MonitorCollectionCommand,MonitorCollectionPlan} from '../../../shared/monitorCollection';
import {boundedRequest} from '../../app/boundedRequest';
import {useTaskDraft,useTaskLibrary} from '../../app/taskDraft';
import {newTaskDraft} from '../../domain/models';
import {researchSelectionScope as publicSourceScope} from '../../../shared/dynamicResearch';

const localLabels={DETACHED:'本机未接管',ATTACHED:'已接管，等待到期',RUNNING:'轮次处理中',STOPPING:'正在停止',STOP_UNCONFIRMED:'来源停止待核实'};
const hints:Record<string,string>={SKIPPED_BUSY:'采集器忙碌，本次到期已跳过，不补跑。',SKIPPED_OFFLINE:'离线错过的时段已跳过。',
 SKIPPED_MISSED:'错过的执行时段已跳过。',RECOVERY_REQUIRED:'旧轮次待核对，不会重新打开来源。',START_UNKNOWN:'启动结果待核对，不会重复启动。'};
export function NativeMonitorPlans(){
 const {service,session,route,navigate}=useApp(),scope=useTaskScope(route.path),monitor=useMonitorCollection();
 const [library]=useTaskLibrary(session.userId,session.accountScope);
 const [,setDraft]=useTaskDraft(session.userId,'monitor',session.accountScope);
 const id=route.path.startsWith('/monitors/')?route.path.slice('/monitors/'.length):null;
 const selected=monitor.list?.plans.find(p=>p.planId===id);
 const profiles=useResource(()=>service.profiles(),[service,session.userId,session.accountScope?.id,session.accountScope?.version]);
 const details=useResource(async()=>selected&&service.researchStrategies?strategyViewSchema.parse(await service.researchStrategies.getStrategy(selected.strategyVersionId)):null,
  [service,selected?.strategyVersionId,session.userId,session.accountScope?.id,session.accountScope?.version]);
 const [confirmation,setConfirmation]=useState<{command:Extract<MonitorCollectionCommand,{action:'ATTACH'|'SET_STATE'}>;accounts:string[]}|null>(null);
 const [preparing,setPreparing]=useState(false),[error,setError]=useState('');
 const [runState,setRunState]=useState('');
 useEffect(()=>{setConfirmation(null);setError('');setRunState('');setPreparing(false);},[scope.identity,id]);
 const name=(p:MonitorCollectionPlan)=>profiles.data?.find(row=>row.id===p.profileVersionId)?.fields.service || '业务监控';
 async function prepare(plan:MonitorCollectionPlan,action:'pause'|'resume'|'attach'){
  if(preparing||monitor.busy)return;
  setPreparing(true);setError('');
  try{
   if(action==='pause')setConfirmation({command:{action:'SET_STATE',requestId:crypto.randomUUID(),planId:plan.planId,
    expectedRevision:plan.revision,state:'PAUSED',humanConfirmed:true},accounts:[]});
   else{
    if(!service.researchStrategies)throw new Error('策略服务尚未接通。');
    const [raw,connections]=await boundedRequest(()=>Promise.all([service.researchStrategies!.getStrategy(plan.strategyVersionId),service.connections()]),{timeoutMessage:'账号检查超时，请重试。'});
    if(!scope.current())return;
    const view=strategyViewSchema.parse(raw);
    if(view.configuration_sha256!==plan.configurationSha256 || view.profile_version_id!==plan.profileVersionId)throw new Error('计划策略已变化，请刷新。');
    const targets=monitorTargets(view,connections);
    const accounts=targets.map(target=>{
     if(target.platform==='PUBLIC_WEB')return `公开社区：${publicSourceScope(view.snapshot.configuration.publicSource)}；按已确认周期抽样`;
     const row=connections.find(c=>c.registration?.connectionId===target.connection_id)!;
     return `${row.platform}：${row.accountId}`;
    });
    setConfirmation({command:action==='attach'?{action:'ATTACH',planId:plan.planId,expectedRevision:plan.revision,targets,humanConfirmed:true}:
     {action:'SET_STATE',requestId:crypto.randomUUID(),planId:plan.planId,expectedRevision:plan.revision,state:'ACTIVE',targets,humanConfirmed:true},accounts});
   }
  }catch(e){if(scope.current())setError(e instanceof Error?e.message:'检查未完成，请刷新重试。');}
  finally{if(scope.current())setPreparing(false);}
 }
 const pendingFor=(p:MonitorCollectionPlan)=>monitor.pending.some(c=>c.action==='SET_STATE'&&c.planId===p.planId || c.action==='CREATE'&&c.strategyVersionId===p.strategyVersionId);
 function actions(p:MonitorCollectionPlan){
  const disabled=monitor.busy||preparing||pendingFor(p);
  return <>
   {p.state==='ACTIVE'?<>
    {p.localState==='DETACHED'&&<Button disabled={disabled||!monitor.list?.supported} onClick={()=>void prepare(p,'attach')}>在本机运行</Button>}
    <Button disabled={disabled} onClick={()=>void prepare(p,'pause')}>暂停计划</Button>
   </>:<Button disabled={disabled||!monitor.list?.supported} onClick={()=>void prepare(p,'resume')}>恢复并在本机运行</Button>}
  </>;
 }
 return <>
  <PageHeader title={selected?(details.data?.snapshot.configuration.name||'监控详情'):'监控任务'}
   description="按已确认周期发现需求。客户端关闭不采集，重新打开后请确认本机账号再接管；不会补跑历史。"
   back={id?()=>navigate('/monitors'):undefined}
   extra={<><Button onClick={()=>void monitor.refresh()}>刷新监控</Button>
    <Button onClick={()=>{setDraft(newTaskDraft('monitor'));navigate('/tasks/new?mode=monitor');}}>新建普通监控</Button>
    <Button variant="primary" onClick={()=>navigate('/tasks/new?mode=monitor')}>新建监控</Button></>}/>
  {(monitor.error||error)&&<Notice tone="warning">{error||monitor.error}</Notice>}
  {monitor.list&&!monitor.list.supported&&<Notice tone="warning">当前服务或本机执行环境尚未开放持续监控，已保存计划仍可查看。</Notice>}
  {!monitor.list&&!monitor.error&&<Notice>正在读取监控计划…</Notice>}
  {monitor.pending.length>0&&<section className="panel" aria-label="监控原请求">
   <h2>原请求待核对</h2><p>这里只查询原操作回执，不重新创建或重复变更。</p>
   {monitor.pending.map(command=><div className="task-footer" key={command.requestId}>
    <span>{command.action==='CREATE'?'创建计划':'变更计划'} · {command.requestId}</span>
    <Button disabled={monitor.busy} onClick={()=>void monitor.execute({action:'RECEIPT',command})}>核对原请求</Button>
   </div>)}
  </section>}
  {id&&!selected&&monitor.list&&<Notice>未找到当前工作空间内的监控计划，请返回列表。</Notice>}
  {!id&&monitor.list&&<section className="panel" aria-label="已保存监控计划">
   {!monitor.list.plans.length?<p>还没有监控计划。先创建并确认策略，再开始持续发现。</p>:
    <table className="data-table"><thead><tr><th>业务与计划</th><th>计划状态</th><th>本机状态</th><th>下次到期</th><th>操作</th></tr></thead>
     <tbody>{monitor.list.plans.map(p=><tr key={p.planId}>
      <td><Button variant="ghost" onClick={()=>navigate(`/monitors/${p.planId}`)}>{name(p)} · {p.planId.slice(0,8)}</Button></td>
      <td>{p.state==='ACTIVE'?'计划启用':'已暂停'}</td><td>{localLabels[p.localState]}</td><td>{p.nextDueAt?formatDate(p.nextDueAt):'—'}</td><td>{actions(p)}</td>
     </tr>)}</tbody></table>}
  </section>}
  {!id&&library.some(draft=>draft.mode==='monitor')&&<section className="panel" aria-label="本机监控草稿">
   <h2>本机草稿</h2><p>保存草稿不会启动监控。</p>
   {library.filter(draft=>draft.mode==='monitor').map(draft=><div className="task-footer" key={draft.id}>
    <span>{draft.name}</span><Button onClick={()=>{setDraft(structuredClone(draft));navigate('/tasks/new?mode=monitor');}}>继续配置</Button>
   </div>)}
  </section>}
  {selected&&<section className="panel" aria-label="真实监控详情">
   <h2>{name(selected)}</h2>
   <p>计划：{selected.state==='ACTIVE'?'启用':'已暂停'} · 本机：{localLabels[selected.localState]} · 版本 {selected.revision}</p>
   <p>{selected.schedule.kind==='daily'?`每天 ${selected.schedule.times.join('、')}`:`每 ${selected.schedule.interval} 小时 · ${selected.schedule.start}–${selected.schedule.end}`} · 时区 {selected.schedule.timezone}</p>
   <p className="field-hint">{schedulePolicyDescription(selected.schedule).slice(0,2).join(' ')}</p>
   <p>下次到期：{selected.nextDueAt?formatDate(selected.nextDueAt):'暂停期间不安排'}</p>
   {details.data&&<><p>平台：{details.data.snapshot.platforms.join('、')}；搜索词：{details.data.snapshot.configuration.keywords.join('、')}</p>
    {details.data.snapshot.platforms.includes('PUBLIC_WEB')&&<p className="field-hint">{publicSourceScope(details.data.snapshot.configuration.publicSource)}；按已确认周期抽样，列表消失不表示需求关闭。</p>}</>}
   <ResourceStatus loading={details.loading} error={details.error}/>
   {selected.lastError&&<Notice tone="warning">{hints[selected.lastError]||`本机需要处理：${selected.lastError}，请核对账号与原执行记录。`}</Notice>}
   <div className="task-footer">{actions(selected)}<Button onClick={()=>navigate('/opportunities')}>查看商机库</Button></div>
   {selected.taskId&&<><p>当前或最近轮次：{selected.taskId}</p>
    <Button disabled={!service.foregroundCollection} onClick={()=>void(async()=>{
     try{const result=await service.foregroundCollection!.execute({action:'STATUS',taskId:selected.taskId!});
      if(scope.current())setRunState(result.state==='STATUS'?`本机：${result.localState}；服务端：${result.serverStatus}；已记录 ${result.recordsUsed} 条；停止${result.stopConfirmed?'已确认':'尚未确认'}`:'轮次状态未核实，请稍后刷新。');
     }catch{if(scope.current())setRunState('轮次状态未核实，请稍后刷新。');}
    })()}>查询实际轮次结果</Button><p>{runState}</p></>}
   <p className="field-hint">计划已启用、下次到期和本机接管均不是采集成功证明。真实结果以原轮次与商机证据为准。</p>
  </section>}
  {confirmation&&<Confirm title={confirmation.command.action==='SET_STATE'&&confirmation.command.state==='PAUSED'?'暂停监控计划':'确认本机监控账号'}
   onCancel={()=>setConfirmation(null)} loading={monitor.busy} confirmText="确认执行" onConfirm={()=>void(async()=>{
    await monitor.execute(confirmation.command);if(scope.current())setConfirmation(null);
   })()}>
   <p>{confirmation.command.action==='SET_STATE'&&confirmation.command.state==='PAUSED'?'先停止本机采集，再提交计划暂停；最终状态以服务端确认结果为准。':'将按已确认策略，在当前客户端在线期间周期采集。不会发送评论或私信。'}</p>
   {confirmation.accounts.map(account=><p key={account}>{account}</p>)}
  </Confirm>}
 </>;
}
