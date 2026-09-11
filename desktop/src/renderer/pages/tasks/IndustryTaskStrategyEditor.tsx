import {Button,Field,Notice} from '../../components/ui';
import {industrySourceLabels,industrySourceTypes,industryTaskStrategySchema} from '../../../shared/industryTaskStrategy';
import type {IndustryStrategyDraft} from '../../domain/industryTaskStrategy';

export function IndustryTaskStrategyEditor({value,profileId,onChange}:{
  value?:IndustryStrategyDraft;profileId:string;onChange:(value:IndustryStrategyDraft|undefined)=>void;
}) {
  const config=value?.configuration;
  const change=(patch:Partial<IndustryStrategyDraft['configuration']>)=>{
    if(value)onChange({...value,configuration:{...value.configuration,...patch}});
  };
  return <section className="form-section" aria-label="本任务行业策略">
    <h2>本任务行业策略</h2>
    <p className="field-hint">保存研究方向，随最终任务快照确认；尚未用于自动评分或内容筛选。内容方向不代表平台权限或已发现需求。</p>
    {!config?<><p>可先生成建议并单独采用，也可以手动设置；留空不影响原搜索条件。</p>
      <Button disabled={!profileId} onClick={()=>onChange({profileId,configuration:{version:'industry-task-strategy-v1',
        sourceTypes:['SOCIAL_POST','COMMENT'],intentSignals:[''],counterSignals:[]}})}>手动设置行业策略</Button></>:<>
      {value.profileId!==profileId&&<Notice tone="warning">策略来自旧画像，核对当前业务后再继续。
        <Button disabled={!profileId} onClick={()=>onChange({...value,profileId})}>按当前画像确认</Button>
      </Notice>}
      <Field label="内容方向"><div className="platform-choices">{industrySourceTypes.map(type=><label key={type}>
        <input type="checkbox" checked={config.sourceTypes.includes(type)} onChange={event=>change({sourceTypes:event.target.checked?
          [...config.sourceTypes,type]:config.sourceTypes.filter(item=>item!==type)})}/>{industrySourceLabels[type]}
      </label>)}</div></Field>
      <Field label="购买信号" hint="每行一条，1–5条，每条最多160字。描述希望寻找的业务动作，不写成既有事实。">
        <textarea aria-label="任务购买信号" rows={4} maxLength={2000} value={config.intentSignals.join('\n')}
          onChange={event=>change({intentSignals:event.target.value.split('\n')})}/>
      </Field>
      <Field label="排除反例" hint="每行一条，最多5条；可以留空。不会自动覆盖搜索排除词。">
        <textarea aria-label="任务排除反例" rows={3} maxLength={2000} value={config.counterSignals.join('\n')}
          onChange={event=>change({counterSignals:event.target.value===''?[]:event.target.value.split('\n')})}/>
      </Field>
      {!industryTaskStrategySchema.safeParse(config).success&&<Notice tone="warning">内容方向至少选一种；信号1–5条、反例0–5条，每条1–160字，不能重复或含空行。未完成的编辑已保留，请修正后准备策略。</Notice>}
      <Button variant="ghost" onClick={()=>onChange(undefined)}>移除本任务策略</Button>
    </>}
  </section>;
}
