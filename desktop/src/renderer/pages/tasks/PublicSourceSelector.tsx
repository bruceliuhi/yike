import type {TaskDraft,PlatformConnection} from '../../domain/models';
import {DEFAULT_PUBLIC_SOURCE,PUBLIC_SOURCES,publicSourceIdSchema,publicSourceScope,type PublicSourceId} from '../../../shared/publicSources';
import {hasPublicSourceBinding} from '../../domain/task';
export function PublicSourceSelector({draft,connections,onChange}:{draft:TaskDraft;connections:PlatformConnection[];onChange:(source:PublicSourceId)=>void}){
 const rows=connections.filter(hasPublicSourceBinding),binding=rows.length===1?rows[0].publicBinding:undefined;
 const choices=binding?(binding.sourceIds??[binding.sourceId]):[];
 const selected=draft.publicSource??DEFAULT_PUBLIC_SOURCE,available=choices.includes(selected);
 return <div>
  <label>公开来源板块
   <select aria-label="公开来源板块" value={selected} disabled={!choices.length} onChange={event=>{
    const source=publicSourceIdSchema.safeParse(event.target.value);
    if(source.success&&choices.includes(source.data))onChange(source.data);
   }}>
    {!available&&<option value={selected} disabled>{PUBLIC_SOURCES[selected].label}（当前不可用）</option>}
    {choices.map(source=><option key={source} value={source}>{PUBLIC_SOURCES[source].label}</option>)}
   </select>
  </label>
  <p className="field-hint">{publicSourceScope(selected)}；关键词仅筛选该板块本次返回的样本。</p>
  {!available&&<p className="field-hint">所选板块当前不可用，已保留原选择；不会自动切换或启动。</p>}
  {draft.research&&selected!==DEFAULT_PUBLIC_SOURCE&&<p className="field-hint">该板块只接普通采集/定时抽样，尚未接搜贝研究。</p>}
 </div>;
}
