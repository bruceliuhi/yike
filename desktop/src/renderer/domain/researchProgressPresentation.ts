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
  effect_unknown:'已有请求的结果尚未核实。',assessment_unknown:'已有请求的结果尚未核实。',
  effect_failed:'本轮读取或分析未完成。',assessment_failed:'本轮读取或分析未完成。',
  resource_limit_exceeded:'本轮已达到确认的研究用量上限。',task_unavailable:'当前任务暂时不能继续。',
  capability_unavailable:'当前服务暂不支持这项研究。',resource_unavailable:'研究服务暂时不可用。',
  lease_conflict:'执行状态发生变化，请查询原任务。',
  worker_lost:'研究执行进程已中断，已有结果保留，不会自动重跑。',
};

function stoppedNextStep(code:string|null):string {
  if(code==='effect_unknown'||code==='assessment_unknown'||code==='lease_conflict')return '请查询原研究状态，核实已有请求，不要重新发送。';
  if(code==='effect_failed'||code==='assessment_failed')return '请先查看已有结果和执行明细。';
  if(code==='resource_limit_exceeded')return '请先查看已有结果，再决定是否在新任务中调整策略。';
  if(code==='task_unavailable')return '请稍后查询原任务状态。';
  if(code==='capability_unavailable'||code==='resource_unavailable')return '请查看执行明细或联系服务支持。';
  return '请查看执行明细，并查询原研究状态。';
}

export function researchProgressPresentation(value:ResearchRuntimeStatus):ResearchProgressPresentation {
  let explanation:string;
  let nextStep:string;
  if(value.phase==='QUEUED'){
    explanation='研究尚未开始，不会自行在后台推进。';
    nextStep=value.contractVersion===4?'使用“开始研究”提交服务端执行，按已确认上限停止。':'使用“继续研究”按已确认的范围开始。';
  }else if(value.phase==='RUNNING'){
    explanation=value.acceptedOriginals===null
      ?'本轮正在逐步处理；入库原文数量尚未确认。'
      :`当前已确认 ${value.acceptedOriginals} 篇入库原文；页面只显示已返回的进度。`;
    nextStep=value.contractVersion===4?'服务端正在研究，本页自动查询进度；无需重复启动。':'可继续按已确认上限推进，或查询原研究状态。';
  }else if(value.phase==='CANCELED'){
    explanation='已停止新增研究；此前已发出的请求不会被撤回。';
    nextStep='请查询原任务，核实此前请求及已有结果。';
  }else if(value.phase==='COMPLETED'){
    if(value.acceptedOriginals===0){
      explanation='本轮没有取得可供分析的原文，不代表没有市场需求。';
      nextStep='请在新任务中调整来源或已确认策略后再研究。';
    }else if(value.acceptedOriginals===null){
      explanation='本轮原文数量尚未确认，不能判断是否取得可供分析的内容。';
      nextStep='请使用“查询原研究状态”核实原文状态。';
    }else{
      explanation='本轮已取得原文，分析结果仍需核对来源和购买意向。';
      nextStep='请“查看原文与分析”并逐条复核。';
    }
  }else{
    explanation=value.stopCode&&Object.hasOwn(stopExplanations,value.stopCode)
      ?stopExplanations[value.stopCode]
      :'研究已停止，请查看执行明细。';
    nextStep=stoppedNextStep(value.stopCode);
  }

  const effects=[value.usage.sourceReads,value.usage.modelCalls];
  const failed=effects.some(item=>item.failed>0)||value.sourceProgress?.some(item=>item.phase==='FAILED')===true;
  const closeout=value.usage.resourceCloseout;
  const uncertain=value.effectsPending||effects.some(item=>item.pending>0||item.unknown>0)
    ||value.sourceProgress?.some(item=>item.phase==='UNKNOWN')===true
    ||closeout?.state==='DRAINING'||closeout?.state==='UNCERTAIN'||(closeout?.overduePermits??0)>0;
  if(uncertain)nextStep='请先查询原研究状态，核实已有请求，不要重新发送或新建任务。';
  const warning=[
    failed?'本轮存在读取或分析失败记录；失败不代表没有结果。请查看执行明细。':null,
    uncertain?'尚有请求或执行记录待核实，不会自动重做；停止本页不代表撤回已发请求。':null,
  ].filter(Boolean).join(' ')||null;
  return {title:titles[value.phase],explanation,nextStep,warning};
}
