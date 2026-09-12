import type {TaskDraft,PlatformConnection} from '../../domain/models';
import {DEFAULT_PUBLIC_SOURCE,PUBLIC_SOURCES,publicSourceIdSchema,publicSourceScope,type PublicSourceId} from '../../../shared/publicSources';
import {hasPublicSourceBinding} from '../../domain/task';
import {researchAllowsSource,researchSourceScope} from '../../../shared/researchRuntime';
export function PublicSourceSelector({draft,connections,onChange,researchCapability}:{draft:TaskDraft;connections:PlatformConnection[];onChange:(source:PublicSourceId)=>void;researchCapability?:unknown}){
 const rows=connections.filter(hasPublicSourceBinding),binding=rows.length===1?rows[0].publicBinding:undefined;
 const choices=(binding?(binding.sourceIds??[binding.sourceId]):[]).filter(source=>!draft.research||researchAllowsSource(researchCapability,source));
 const selected=draft.publicSource??DEFAULT_PUBLIC_SOURCE,available=choices.includes(selected);
 const label=(source:PublicSourceId)=>draft.research?researchSourceScope(source):PUBLIC_SOURCES[source].label;
 return <div>
  <label>公开来源板块
   <select aria-label="公开来源板块" value={selected} disabled={!choices.length} onChange={event=>{
    const source=publicSourceIdSchema.safeParse(event.target.value);
    if(source.success&&choices.includes(source.data))onChange(source.data);
   }}>
    {!available&&<option value={selected} disabled>{label(selected)}（当前不可用）</option>}
    {choices.map(source=><option key={source} value={source}>{label(source)}</option>)}
   </select>
  </label>
  <p className="field-hint">{draft.research?researchSourceScope(selected)+'；仅判断该索引返回的样本，不覆盖全站或历史':publicSourceScope(selected)+'；关键词仅筛选该板块本次返回的样本'}。</p>
  {!available&&<p className="field-hint">所选板块当前不可用，已保留原选择；不会自动切换或启动。</p>}
 </div>;
}
