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
      if(scenario==='UNKNOWN')Object.assign(value,{phase:'STOPPED',canAdvance:false,newActionsBlocked:true,stopCode:'effect_unknown',
        usage:{...value.usage,modelCalls:{...counts(),issued:1,unknown:1}}});
      return researchRuntimeStatusSchema.parse(value);
    };
    h.service.researchRuntime={capability:async()=>researchRuntimeCapabilitySchema.parse(dynamicCapability),status:async()=>status(),
      advance:async()=>{throw new Error('TEST no launch');}};
    return h.service;
  },[scenario]);
  return <AppProvider service={service}><main style={{maxWidth:1100,margin:'24px auto',padding:20}}>
    <h1>TEST 组件验收 · 合成状态，不是真实商机</h1>
    <label>测试状态 <select aria-label="测试状态" value={scenario} onChange={event=>setScenario(event.target.value)}>
      <option value="RUNNING">执行中</option><option value="EMPTY">无原文</option><option value="UNKNOWN">结果未知</option></select></label>
    <ResearchProgress key={scenario} taskId={id(1)} runId={id(2)} taskStatus="PENDING"/>
    <PublicSourceSelector draft={draft} connections={[]} researchCapability={dynamicCapability} onChange={()=>{}}/>
    <ResearchSettingsPanel value={draft.research} onChange={research=>setDraft({...draft,research})} quote={null} busy={false}
      error="" onEstimate={()=>{}} onCancel={()=>{}}/>
  </main></AppProvider>;
}
createRoot(document.getElementById('root')!).render(<Preview/>);
