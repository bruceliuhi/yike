import type {ResearchRuntimeStatus} from '../../shared/researchRuntime';

export interface ResearchProgressPresentation {
  title:string;
  explanation:string;
  nextStep:string;
  warning:string|null;
}

const titles:Record<ResearchRuntimeStatus['phase'],string>={
  QUEUED:'已准备好，等待开始',RUNNING:'研究进行中',STOPPED:'研究已暂停',
  CANCELED:'已停止新增研究',COMPLETED:'本轮研究已完成',
};

const stopExplanations:Record<string,string>={
  no_verified_reads:'本轮未找到可核对的原文。',
  effect_unknown:'研究结果仍待确认。',assessment_unknown:'研究结果仍待确认。',
  effect_failed:'本轮读取或分析未完成。',assessment_failed:'本轮读取或分析未完成。',
  resource_limit_exceeded:'本轮已达到确认的研究用量上限。',task_unavailable:'当前任务暂时不能继续。',
  capability_unavailable:'当前服务暂不支持这项研究。',resource_unavailable:'研究服务暂时不可用。',
  lease_conflict:'任务状态已变化，请刷新进度。',
  worker_lost:'研究意外中断，已有结果已保留。',
  research_selection_invalid:'部分原文尚未完成分析。',
  broker_stop_unknown:'任务是否已停止仍待确认，请刷新进度。',
  broker_stream_unknown:'部分研究结果仍待确认。',
};

function stoppedNextStep(code:string|null):string {
  if(code==='no_verified_reads')return '可在新任务中调整搜索词或来源后再试。';
  if(code==='effect_unknown'||code==='assessment_unknown'||code==='lease_conflict')return '请先刷新进度，确认结果后再继续。';
  if(code==='effect_failed'||code==='assessment_failed')return '请先查看原文与分析，核对已有结果。';
  if(code==='resource_limit_exceeded')return '请先查看已有结果，再决定是否在新任务中调整策略。';
  if(code==='task_unavailable')return '请稍后刷新进度。';
  if(code==='capability_unavailable'||code==='resource_unavailable')return '请稍后刷新进度，或联系客服。';
  return '请刷新进度，或查看已有结果。';
}

export function researchProgressPresentation(value:ResearchRuntimeStatus):ResearchProgressPresentation {
  let explanation:string;
  let nextStep:string;
  if(value.phase==='QUEUED'){
    explanation='搜索目标已准备好。';
    nextStep=value.contractVersion===4?'使用“开始研究”，达到已确认上限即停止。':'使用“继续研究”按已确认的范围开始。';
  }else if(value.phase==='RUNNING'){
    explanation=value.acceptedOriginals===null
      ?'正在查找并分析相关内容。'
      :`已取得 ${value.acceptedOriginals} 篇原文。`;
    nextStep=value.contractVersion===4?'正在研究，请稍候。':'可继续研究，或刷新进度。';
  }else if(value.phase==='CANCELED'){
    explanation='不再新增研究，已有结果保留。';
    nextStep='可查看已有结果。';
  }else if(value.phase==='COMPLETED'){
    if(value.acceptedOriginals===0){
      const pagesRead=value.contractVersion===4?(value.discovery?.reads.succeeded??0):0;
      explanation=pagesRead>0
        ?`已读取 ${pagesRead} 篇公开页面，暂未选出合适线索。`
        :'本轮未找到可分析的原文。';
      nextStep='请在新任务中调整来源或已确认策略后再研究。';
    }else if(value.acceptedOriginals===null){
      explanation='本轮原文数量尚未确认。';
      nextStep='请刷新进度查看结果。';
    }else{
      explanation='本轮已取得原文，分析结果仍需核对来源和购买意向。';
      nextStep='请“查看原文与分析”并逐条复核。';
    }
  }else{
    explanation=value.stopCode&&Object.hasOwn(stopExplanations,value.stopCode)
      ?stopExplanations[value.stopCode]
      :'研究已停止，请刷新进度。';
    nextStep=stoppedNextStep(value.stopCode);
  }

  const effects=[value.usage.sourceReads,value.usage.modelCalls];
  const failed=effects.some(item=>item.failed>0)||value.sourceProgress?.some(item=>item.phase==='FAILED')===true;
  const closeout=value.usage.resourceCloseout;
  const backgroundRunning=value.contractVersion===4&&value.phase==='RUNNING';
  const pending=value.effectsPending||effects.some(item=>item.pending>0)||closeout?.state==='DRAINING';
  const uncertain=(!backgroundRunning&&pending)||effects.some(item=>item.unknown>0)
    ||['effect_unknown','assessment_unknown','broker_stop_unknown','broker_stream_unknown'].includes(value.stopCode??'')
    ||[value.discovery?.searches,value.discovery?.reads].some(item=>(item?.unknown??0)>0)
    ||value.sourceProgress?.some(item=>item.phase==='UNKNOWN')===true
    ||closeout?.state==='UNCERTAIN'||(closeout?.overduePermits??0)>0;
  if(uncertain)nextStep='请先刷新进度，确认结果后再继续。';
  const warning=uncertain
    ?failed?'部分内容未完成，另有结果待确认。':'部分结果仍待确认。'
    :failed?'部分内容未能完成分析，可查看已有结果。':null;
  return {title:titles[value.phase],explanation,nextStep,warning};
}
