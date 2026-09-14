import type {TaskDraft,Term} from '../../domain/models';
import {PLATFORMS} from '../../domain/models';
import {queryPlatforms,type QueryPlatform,type PlatformTerms,platformTermsError} from '../../domain/platformSearchTerms';
import {TermEditor} from '../../components/TermEditor';
import {Button,Field,Notice} from '../../components/ui';

export function PlatformSearchTerms({draft,onChange}:{draft:TaskDraft;onChange:(value:PlatformTerms|undefined)=>void}) {
  const enabled=draft.source==='search' && !draft.research;
  const error=platformTermsError(draft);
  const visible=PLATFORMS.filter(platform=>platform.id in queryPlatforms &&
    (draft.platforms.includes(platform.id) || Object.hasOwn(draft.platformTerms??{},platform.id)));
  function change(platform:QueryPlatform,terms:Term[]|undefined) {
    const next={...draft.platformTerms};
    if(terms===undefined)delete next[platform];else next[platform]=terms;
    onChange(Object.keys(next).length?next:undefined);
  }
  return <details className="strategy-snapshot">
    <summary>按平台设置搜索词</summary>
    <p>单独设置后替换该平台的通用词，其他平台不变；共用排除词和任务上限。AI重新生成通用建议不会覆盖这里的人工词。</p>
    {!enabled && <Notice tone="warning">当前模式不支持平台专用词，请使用通用搜索词。</Notice>}
    {!visible.length && <p>请先选择小红书、抖音、B站或知乎。</p>}
    {visible.map(platform=>{
      const key=platform.id as QueryPlatform,terms=draft.platformTerms?.[key];
      return <Field key={key} label={`${platform.name}搜索词`} className="horizontal-field"
        hint={!draft.platforms.includes(key)?'该平台已取消选择，人工词仍保留；请恢复通用词或重新选平台。':
          terms?'仅搜索下面这些词；不会额外运行通用词。':'沿用通用搜索词。'}>
        {terms!==undefined ? <>
          <TermEditor label={`${platform.name}搜索词`} terms={terms} onChange={value=>change(key,value)}
            onRemove={id=>change(key,terms.filter(term=>term.id!==id))}/>
          <Button variant="ghost" onClick={()=>change(key,undefined)}>{platform.name}恢复通用词</Button>
        </> : <Button variant="ghost" disabled={!enabled} onClick={()=>change(key,draft.terms.map(term=>({
          ...term,id:crypto.randomUUID(),origin:'manual',edited:true})))}>{platform.name}单独设置</Button>}
      </Field>;
    })}
    {error && <Notice tone="error">{error}</Notice>}
  </details>;
}
