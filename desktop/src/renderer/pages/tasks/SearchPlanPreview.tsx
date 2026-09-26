import { useState } from 'react';
import { useApp } from '../../app/context';
import { useResource } from '../../app/hooks';
import { Button, Notice } from '../../components/ui';
import type { TaskDraft } from '../../domain/models';
import { industryStrategyError } from '../../domain/industryTaskStrategy';
import { radarPlanInputSchema, type RadarPlanInput } from '../../../shared/radarPlan';
import './search-plan.css';

export function SearchPlanPreview({ draft }: { draft: TaskDraft }) {
  const { session, service } = useApp();
  const [open, setOpen] = useState(false);
  const strategyError = industryStrategyError(draft);
  const strategy = draft.industryStrategy?.profileId === draft.profileId
    ? draft.industryStrategy.configuration : undefined;
  const parsed = radarPlanInputSchema.safeParse({
    querySeeds: draft.terms.map(term => term.value),
    intentSignals: strategy?.intentSignals ?? [],
    exclusions: [...draft.exclusions.map(term => term.value), ...(strategy?.counterSignals ?? [])],
    region: '', demandTypes: draft.research?.demandTypes ?? [],
  });
  const binding = JSON.stringify([session.userId, session.authenticated, session.accountScope,
    draft.id, draft.profileId, draft.profileVersion, parsed.success ? parsed.data : null]);
  return <details className="search-plan-preview" onToggle={event => setOpen(event.currentTarget.open)}>
    <summary><strong>搜索计划</strong><span>找需求 · 核验条件 · 扩展线索</span></summary>
    {open && (!session.authenticated ? <p className="muted">登录后查看搜索计划</p>
      : strategyError ? <p className="muted">{strategyError}</p>
      : !parsed.success ? <p className="muted">先完善上方搜索条件，再查看计划</p>
      : !service.researchPlan ? <p className="muted">当前服务暂不支持计划预览，已填写的条件仍会保留</p>
      : <PlanDetails key={binding} input={parsed.data} />)}
  </details>;
}

function PlanDetails({ input }: { input: RadarPlanInput }) {
  const { service, session } = useApp();
  const result = useResource(signal => service.researchPlan!.preview(input, session, signal),
    [service, session.userId, session.accountScope?.id, session.accountScope?.version, JSON.stringify(input)]);
  if (result.loading) return <p className="muted" role="status">正在整理搜索计划…</p>;
  if (result.error) return <Notice tone="warning" action={<Button variant="ghost" onClick={result.reload}>重新查看</Button>}>{result.error}</Notice>;
  if (!result.data) return null;
  return <div className="search-plan-content">
    <p className="field-hint">根据当前条件整理，修改关键词后会更新；开始研究后按来源可用性和用量上限执行</p>
    <ol className="search-plan-directions">
      {result.data.strategies.map(direction => <li key={direction.id}>
        <div><strong>{direction.name}</strong><span>{direction.purpose}</span></div>
        {direction.queries.length ? <ul>{direction.queries.slice(0, 2).map(query => <li key={query}>{query}</li>)}</ul>
          : <p className="muted">当前条件没有额外检索式</p>}
      </li>)}
    </ol>
    <details className="search-plan-queries"><summary>查看全部 {result.data.queries.length} 条检索式</summary>
      <ul>{result.data.queries.map(query => <li key={query}>{query}</li>)}</ul>
    </details>
    <p className="field-hint">预览不启动搜索，不消耗搜贝；实际结果先进入任务线索，复核后进入商机库</p>
  </div>;
}
