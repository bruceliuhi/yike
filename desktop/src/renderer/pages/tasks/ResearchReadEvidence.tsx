import {useEffect,useRef,useState} from 'react';
import {boundedRequest} from '../../app/boundedRequest';
import {Button,Notice,ResourceStatus,formatDate} from '../../components/ui';
import type {ResearchRuntimeReads} from '../../../shared/researchRuntime';
import type {ResearchRuntimeService} from '../../services/researchRuntime';

const LONG_TEXT_LENGTH=600;

export function ResearchReadEvidence({taskId,runId,reads,onOpen}:{
  taskId:string;runId:string;reads:NonNullable<ResearchRuntimeService['reads']>;onOpen:(url:string)=>Promise<void>;
}){
  const [items,setItems]=useState<ResearchRuntimeReads['items']>([]),[nextAfter,setNextAfter]=useState<number|null>(null);
  const [loaded,setLoaded]=useState(false),[loading,setLoading]=useState(false),[error,setError]=useState('');
  const [expanded,setExpanded]=useState<Set<number>>(()=>new Set()),controller=useRef<AbortController|null>(null);
  const identity=useRef(0);
  useEffect(()=>{identity.current+=1;controller.current?.abort();controller.current=null;
    setItems([]);setNextAfter(null);setLoaded(false);setLoading(false);setError('');setExpanded(new Set());
    return ()=>{identity.current+=1;controller.current?.abort();};
  },[taskId,runId,reads]);
  async function load(after:number,replace:boolean){
    controller.current?.abort();const abort=new AbortController(),scope=identity.current;controller.current=abort;
    setLoading(true);setError('');
    try{
      const page=await boundedRequest(signal=>reads(taskId,runId,after,signal),{
        signal:abort.signal,timeoutMessage:'已读原文查询超时。'});
      if(abort.signal.aborted||scope!==identity.current)return;
      setItems(current=>replace?page.items:[...current,...page.items]);setNextAfter(page.nextAfter);setLoaded(true);
    }catch{
      if(!abort.signal.aborted&&scope===identity.current)setError('已读原文未能核实；这不是空列表，请稍后手动刷新。');
    }finally{
      if(controller.current===abort)controller.current=null;
      if(!abort.signal.aborted&&scope===identity.current)setLoading(false);
    }
  }
  return <details onToggle={event=>{if(event.currentTarget.open&&!loaded&&!loading)void load(0,true);}}>
    <summary>已读原文</summary>
    <p className="muted">这里只展示已成功读取的公开原文；研究原文，尚非已确认商机。</p>
    <ResourceStatus loading={loading} error={error}/>
    {loaded&&items.length===0&&!error&&<p>本次尚无可回查的成功原文。</p>}
    {items.map(item=>{const long=item.text.length>LONG_TEXT_LENGTH,isExpanded=expanded.has(item.sequence);return <article
      className="fixed-source-evidence fixed-source-evidence--compact" aria-label="研究原文" key={item.sequence}>
      <h3>{item.title??'未提供标题'}</h3>
      <p className="field-hint" style={{overflowWrap:'anywhere'}}>{item.url}</p>
      <p className="muted">读取于 {formatDate(item.observedAt)} · 序号 {item.sequence}</p>
      <div className={`fixed-evidence-body${long&&!isExpanded?' fixed-evidence-body--collapsed':''}`}>{item.text}</div>
      {long&&<Button variant="ghost" aria-expanded={isExpanded} onClick={()=>setExpanded(current=>{
        const next=new Set(current);if(next.has(item.sequence))next.delete(item.sequence);else next.add(item.sequence);return next;
      })}>{isExpanded?'收起原文':'展开完整原文'}</Button>}
      <div className="task-footer"><Button onClick={()=>void onOpen(item.url).catch(()=>setError('来源链接未能安全打开，请稍后重试。'))}>打开公开来源</Button></div>
      <p className="field-hint">研究原文，尚非已确认商机</p>
    </article>;})}
    <div className="task-footer">
      <Button disabled={loading} onClick={()=>void load(0,true)}>刷新已读原文</Button>
      <Button disabled={loading||nextAfter===null} onClick={()=>{if(nextAfter!==null)void load(nextAfter,false);}}>下一页</Button>
    </div>
  </details>;
}
