import '../../src/renderer/app/validationRuntime';
import {useMemo,useState} from 'react';
import {createRoot} from 'react-dom/client';
import {AppProvider} from '../../src/renderer/app/context';
import {ResearchProgress} from '../../src/renderer/pages/tasks/ResearchProgress';
import {ResearchSettingsPanel} from '../../src/renderer/pages/tasks/ResearchSettings';
import {PublicSourceSelector} from '../../src/renderer/pages/tasks/PublicSourceSelector';
import {newTaskDraft,type TaskDraft} from '../../src/renderer/domain/models';
import {defaultResearchSettings} from '../../src/renderer/domain/researchUsage';
import {researchRuntimeCapabilitySchema,researchRuntimeStatusSchema} from '../../src/shared/researchRuntime';
import {dynamicCapability,dynamicStatus,counts,id} from '../fixtures/dynamicResearch';
import {createVisualService} from './service';
import {isolateBrowser} from './isolation';
import '../../src/renderer/styles.css';

isolateBrowser(()=>{});
function Preview(){
  const [scenario,setScenario]=useState('RUNNING');
  const [draft,setDraft]=useState<TaskDraft>({...newTaskDraft(),platforms:['web'],publicSource:'public-web-agent-v1',
    research:{...defaultResearchSettings(),maxSoubei:20,limits:{sources:20,minutes:15,modelCalls:20},
      dynamicScope:{version:1,maxAgeDays:60,timezone:'Asia/Shanghai'}}});
  const service=useMemo(()=>{
    const h=createVisualService();
    const status=()=>{
      const value=dynamicStatus();
      if(scenario==='RUNNING')Object.assign(value,{phase:'RUNNING',canAdvance:false,newActionsBlocked:true,
        acceptedOriginals:1,candidateIds:[id(3)],discovery:{searches:counts(2),reads:counts(1),unpublishedOriginals:0},
        usage:{...value.usage,sourceReads:counts(3),modelCalls:counts(2)}});
      if(scenario==='EMPTY')Object.assign(value,{phase:'COMPLETED',canAdvance:false,newActionsBlocked:true});
      if(scenario==='READS')Object.assign(value,{phase:'STOPPED',canAdvance:false,newActionsBlocked:true,
        stopCode:'research_selection_invalid',discovery:{searches:counts(1),reads:counts(2),unpublishedOriginals:2},
        usage:{...value.usage,sourceReads:counts(3),modelCalls:counts(3)}});
      if(scenario==='UNKNOWN')Object.assign(value,{phase:'STOPPED',canAdvance:false,newActionsBlocked:true,stopCode:'effect_unknown',
        usage:{...value.usage,modelCalls:{...counts(),issued:1,unknown:1}}});
      return researchRuntimeStatusSchema.parse(value);
    };
    h.service.researchRuntime={capability:async()=>researchRuntimeCapabilitySchema.parse(dynamicCapability),status:async()=>status(),
      reads:async(taskId,runId)=>({contractVersion:1,taskId,runId,nextAfter:null,items:scenario==='READS'?[
        {sequence:2,url:'https://www.v2ex.com/t/100001',title:'TEST 公开原文，尚未形成候选',
          text:'这是仅用于界面验证的合成原文，不是真实商机。\n'.repeat(35),
          observedAt:'2026-09-13T08:00:00Z',contentSha256:'a'.repeat(64)},
        {sequence:4,url:'https://www.zhihu.com/question/100002',title:'TEST 另一来源的待判断材料',
          text:'模型分析未完成，已成功读取的原文仍可回查。不据此声称需求成立，也不开放自动联系。',
          observedAt:'2026-09-13T08:01:00Z',contentSha256:'b'.repeat(64)},
      ]:[]}),
      advance:async()=>{throw new Error('TEST no launch');}};
    return h.service;
  },[scenario]);
  return <AppProvider service={service}><main style={{maxWidth:1100,margin:'24px auto',padding:20}}>
    <h1>TEST 组件验收 · 合成状态，不是真实商机</h1>
    <label>测试状态 <select aria-label="测试状态" value={scenario} onChange={event=>setScenario(event.target.value)}>
      <option value="RUNNING">执行中</option><option value="EMPTY">无原文</option><option value="UNKNOWN">结果未知</option>
      <option value="READS">有原文，筛选未完成</option></select></label>
    <ResearchProgress key={scenario} taskId={id(1)} runId={id(2)} taskStatus="PENDING"/>
    <PublicSourceSelector draft={draft} connections={[]} researchCapability={dynamicCapability} onChange={()=>{}}/>
    <ResearchSettingsPanel value={draft.research} onChange={research=>setDraft({...draft,research})} quote={null} busy={false}
      error="" onEstimate={()=>{}} onCancel={()=>{}}/>
  </main></AppProvider>;
}
createRoot(document.getElementById('root')!).render(<Preview/>);
