import {useState} from 'react';
import {Button, Notice} from '../../components/ui';
import type {DesktopStartCommand, useDesktopExecution} from './useDesktopExecution';

export function DesktopExecutionRequests({execution, canRetryStart, validateStart}: {
  execution: ReturnType<typeof useDesktopExecution>;
  canRetryStart: boolean;
  validateStart: (requestId: string) => Promise<DesktopStartCommand>;
}) {
  const [retry, setRetry] = useState<Record<string, boolean>>({});
  const [cancel, setCancel] = useState<Record<string, boolean>>({});
  return <section className="strategy-confirmation" aria-label="本机原执行请求">
    <div className="section-heading"><h2>本机原执行请求</h2>
      <Button disabled={execution.busy} onClick={() => void execution.refresh()}>刷新本机原请求</Button></div>
    <p className="field-hint">先核对原请求，避免重复创建。查询不会重新提交执行；任务创建不表示采集成功。</p>
    {!execution.loaded && <Notice tone="warning">本机原请求尚未读取成功，暂不能创建新任务。</Notice>}
    {execution.error && <Notice tone="warning">{execution.error}</Notice>}
    {execution.loaded && !execution.entries.length && <p className="field-hint">当前工作空间暂无本机原执行请求。</p>}
    {execution.entries.map(entry => {
      const receipt = entry.receipt;
      const canRetry = entry.operation === 'CANCEL' || entry.operation === 'START' && canRetryStart;
      const retryChecked = canRetry && retry[entry.requestId] === true;
      const cancelExists = receipt?.operation === 'START' && execution.entries.some(value => value.operation === 'CANCEL' &&
        (value.request?.task_id === receipt.task_id || value.command?.action === 'CANCEL' && value.command.taskId === receipt.task_id));
      return <article key={entry.requestId} className="task-start-blockers">
        <h3>{{START: '启动任务', CANCEL: '取消任务', CLAIM: '领取任务', RENEW: '续期任务'}[entry.operation]} · 原执行请求</h3><p className="field-hint">{entry.requestId}</p>
        <p>{receipt?.operation === 'START' ? '原启动回执：任务已创建，当时待执行；不是当前任务状态，不代表采集成功。'
          : receipt?.operation === 'CANCEL' ? receipt.stop_confirmed ? '任务已确认停止。' : '取消已登记，等待停止确认。'
          : receipt ? '已核对历史租约回执，不代表当前仍有执行授权。'
          : `原请求待核对（${entry.state || '未查询'}）；未查到不表示请求失败。`}</p>
        {receipt && <p className="field-hint">任务：{receipt.task_id}</p>}
        {(entry.operation === 'START' || entry.operation === 'CANCEL') && <label className="check-row">
          <input type="checkbox" checked={retryChecked} disabled={execution.busy || !execution.loaded || !canRetry}
            onChange={event => setRetry(old => ({...old, [entry.requestId]: event.target.checked}))} />
          我确认核对后重试此原{entry.operation === 'START' ? '启动' : '取消'}请求（沿用原请求编号）
        </label>}
        {entry.operation === 'START' && !canRetryStart && <p className="field-hint">启动重试需当前草稿和已确认策略完全一致，且通过全部执行条件；现在仍可只查询。</p>}
        <Button disabled={execution.busy || !execution.loaded}
          onClick={() => void execution.recover(entry, retryChecked, () => validateStart(entry.requestId))}>
          {retryChecked ? '核对并重试原执行请求' : '查询原执行请求'}
        </Button>
        {receipt?.operation === 'START' && <>
          <label className="check-row"><input type="checkbox" checked={cancel[entry.requestId] === true}
            disabled={execution.busy || !!cancelExists} onChange={event => setCancel(old => ({...old, [entry.requestId]: event.target.checked}))} />
            我确认取消此任务（{receipt.task_id}）</label>
          <Button disabled={execution.busy || !execution.loaded || cancel[entry.requestId] !== true || !!cancelExists}
            onClick={() => void execution.cancel(entry, cancel[entry.requestId] === true)}>确认取消此任务</Button>
          {cancelExists && <p className="field-hint">此任务已有取消原请求，请核对原取消结果，不重复创建。</p>}
        </>}
      </article>;
    })}
  </section>;
}
