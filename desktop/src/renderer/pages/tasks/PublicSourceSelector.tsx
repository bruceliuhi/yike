import type {TaskDraft,PlatformConnection} from '../../domain/models';
import {DEFAULT_PUBLIC_SOURCE,PUBLIC_SOURCES,publicSourceIdSchema,publicSourceScope,type PublicSourceId} from '../../../shared/publicSources';
import {hasPublicSourceBinding} from '../../domain/task';
import {researchAllowsSource,researchSourceScope,researchRuntimeCapabilitySchema} from '../../../shared/researchRuntime';
import {researchIndexLabel,type ResearchSourcePlan} from '../../../shared/researchSourcePlan';
import {DYNAMIC_RESEARCH_SOURCE,researchSelectionSchema,type ResearchSelection} from '../../../shared/dynamicResearch';
export function PublicSourceSelector({draft,connections,onChange,onPlanChange,researchCapability}:{draft:TaskDraft;connections:PlatformConnection[];
 onChange:(source:ResearchSelection)=>void;onPlanChange?:(source:PublicSourceId,plan:ResearchSourcePlan|undefined)=>void;researchCapability?:unknown}){
 const rows=connections.filter(hasPublicSourceBinding),binding=rows.length===1?rows[0].publicBinding:undefined;
 const choices:ResearchSelection[]=(binding?(binding.sourceIds??[binding.sourceId]):[]).filter(source=>!draft.research||researchAllowsSource(researchCapability,source));
 if(draft.research&&researchAllowsSource(researchCapability,DYNAMIC_RESEARCH_SOURCE))choices.push(DYNAMIC_RESEARCH_SOURCE);
 const selected=draft.publicSource??DEFAULT_PUBLIC_SOURCE,available=choices.includes(selected);
 const dynamic=selected===DYNAMIC_RESEARCH_SOURCE;
 const label=(source:ResearchSelection)=>draft.research||source===DYNAMIC_RESEARCH_SOURCE?researchSourceScope(source):PUBLIC_SOURCES[source].label;
 const capability=researchRuntimeCapabilitySchema.safeParse(researchCapability);
 const multi=!!draft.research&&!dynamic&&capability.success&&[3,4].includes(capability.data.contractVersion);
 const planned:PublicSourceId[]=draft.research?.sourcePlan?.sources??(dynamic?[]:[selected]);
 const catalog=Object.keys(PUBLIC_SOURCES) as PublicSourceId[];
 function changePlan(primary:PublicSourceId,sources:PublicSourceId[]){
  const ordered=[primary,...catalog.filter(id=>id!==primary&&sources.includes(id))];
  onPlanChange?.(primary,ordered.length>1?{version:1,sources:ordered}:undefined);
 }
 return <div>
  <label>公开来源板块
   <select aria-label="公开来源板块" value={selected} disabled={!choices.length} onChange={event=>{
    const source=researchSelectionSchema.safeParse(event.target.value);
    if(source.success&&choices.includes(source.data)){
     if(source.data!==DYNAMIC_RESEARCH_SOURCE&&draft.research?.sourcePlan&&onPlanChange)changePlan(source.data,planned);
     else onChange(source.data);
    }
   }}>
    {!available&&<option value={selected} disabled>{label(selected)}（当前不可用）</option>}
    {choices.map(source=><option key={source} value={source}>{label(source)}</option>)}
   </select>
  </label>
  <p className="field-hint">{dynamic?'从已确认业务生成查询、打开公开原文并形成待复核候选；不保证覆盖全网，不读取登录后评论':draft.research?researchSourceScope(selected)+'；仅判断该索引返回的样本，不覆盖全站或历史':publicSourceScope(selected)+'；关键词仅筛选该板块本次返回的样本'}。</p>
  {!available&&<p className="field-hint">所选板块当前不可用，已保留原选择；不会自动切换或启动。</p>}
  {draft.research&&!dynamic&&(multi||draft.research.sourcePlan)&&<fieldset>
   <legend>同时研究其他已支持板块</legend>
   {catalog.filter(id=>id!==selected&&(choices.includes(id)||planned.includes(id))).map(id=><label key={id}>
    <input type="checkbox" aria-label={'同时研究 '+researchIndexLabel(id)} checked={planned.includes(id)}
     disabled={!multi||!onPlanChange||!choices.includes(id)} onChange={event=>changePlan(selected,
      event.target.checked?[...planned,id]:planned.filter(source=>source!==id))}/>{researchIndexLabel(id)}
   </label>)}
   <p className="field-hint">按确认顺序读取，各板块均分总记录上限；空板块的配额不转移。仅索引主题，未读评论或作者回复，不代表全站覆盖。</p>
   {!multi&&<p className="field-hint">当前服务不支持已保存的多来源计划，原选择保留，暂不能启动。</p>}
  </fieldset>}
 </div>;
}
