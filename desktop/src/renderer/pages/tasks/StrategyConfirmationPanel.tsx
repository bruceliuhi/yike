import { Badge, Button, Notice } from "../../components/ui";
import type { useStrategyConfirmation } from "./useStrategyConfirmation";
import { StrategySnapshotDetails } from "./StrategySnapshotDetails";
import {researchSelectionScope as publicSourceScope,DYNAMIC_RESEARCH_SOURCE} from '../../../shared/dynamicResearch';

export function StrategyConfirmationPanel({ strategy, reviewed, onReviewedChange, disabled, preparationError }: {
  strategy: ReturnType<typeof useStrategyConfirmation>;
  reviewed: boolean;
  onReviewedChange: (checked: boolean) => void;
  disabled: boolean;
  preparationError: string | null;
}) {
  if (!strategy.available) return null;
  const locked = disabled || strategy.busy;
  const receipt = strategy.historyReceipt;
  const current = Boolean(strategy.prepared && strategy.view?.is_current && strategy.view.profile_current
    && strategy.view.state !== "REVOKED");
  return <section className="strategy-confirmation" aria-label="策略确认">
    <div className="section-heading">
      <h2>策略确认</h2>
      <Badge tone={strategy.confirmed ? "green" : "neutral"}>
        {strategy.confirmed ? "本次策略已确认" : strategy.pending ? "结果待确认" : "待确认"}
      </Badge>
    </div>
    <p className="field-hint">请确认本次搜索目标与设置。</p>
    {strategy.prepared?.snapshot.configuration.publicSource && <Notice>{strategy.prepared.snapshot.configuration.publicSource===DYNAMIC_RESEARCH_SOURCE
      ?'公开网页自主研究：依据本次业务与时效动态搜索并读取原文，不保证覆盖全网；登录后内容与动态评论需另行授权补证。'
      :publicSourceScope(strategy.prepared.snapshot.configuration.publicSource)+'；关键词仅筛选本次近期主题样本，非全站搜索。每次最多检查任务分配的近期主题，不补扫历史；请至少间隔1分钟再采样。'}</Notice>}
    {preparationError && <Notice tone="warning">{preparationError}</Notice>}
    {strategy.error && <Notice tone="warning">{strategy.error}</Notice>}
    {receipt && <>
      <p className="field-hint">
        {strategy.historyOnly ? "这是历史设置，请确认当前搜索条件。" : "修改设置后，需要重新确认。"}
        {strategy.view?.state === "REVOKED" ? " 此策略已撤销。" : ""}
        {strategy.view && (!strategy.view.is_current || !strategy.view.profile_current) ? " 策略或画像已不是当前版本。" : ""}
      </p>
      <StrategySnapshotDetails receipt={receipt} />
    </>}
    <label className="check-row">
      <input type="checkbox" checked={reviewed} disabled={locked || !current}
        onChange={event => onReviewedChange(event.target.checked)} />
      我已核对以上业务画像、搜索条件、账号与运行设置
    </label>
    <div className="strategy-actions">
      <Button disabled={locked || strategy.pending || !!preparationError} onClick={() => void strategy.prepare()}>
        预览搜索设置
      </Button>
      <Button variant="primary" disabled={locked || strategy.pending || !current || !reviewed || strategy.confirmed || !!preparationError}
        onClick={() => void strategy.confirm(reviewed)}>
        确认本次策略
      </Button>
      <Button disabled={locked} onClick={() => void strategy.reconcile()}>查看确认结果</Button>
      {strategy.pending && <Button disabled={locked} onClick={() => void strategy.retry()}>检查并继续确认</Button>}
      {receipt && <Button disabled={locked || strategy.pending || strategy.view?.state === "REVOKED"}
        onClick={() => void strategy.revoke()}>撤销本次策略</Button>}
    </div>
    {strategy.pending && <p className="field-hint">设置确认中，请先查看结果。</p>}
  </section>;
}
