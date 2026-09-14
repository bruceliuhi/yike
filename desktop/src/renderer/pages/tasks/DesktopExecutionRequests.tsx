import {useState} from 'react';
import {Button, Notice} from '../../components/ui';
import type {DesktopStartCommand, useDesktopExecution} from './useDesktopExecution';

const requestStateLabels: Record<string, string> = {
  UNKNOWN:'结果尚未确认', NOT_FOUND:'暂未查到记录', SERVICE_UNAVAILABLE:'服务暂不可用',
  SESSION_CHANGED:'登录身份已变化', BUSY:'正在处理', KEY_MISSING:'本机验证信息不可用',
  SIGNED_OUT:'请先登录', DEVICE_NOT_READY:'本机尚未就绪', INVALID_REQUEST:'请求信息无法核实',
  FAILED:'查询未完成', RECORDED:'已登记', RESEARCH_RECORDED:'已登记',
};

export function DesktopExecutionRequests({execution, canRetryStart, canRetryCancel = true, validateStart}: {
  execution: ReturnType<typeof useDesktopExecution>;
  canRetryStart: boolean;
  canRetryCancel?: boolean;
  validateStart: (requestId: string) => Promise<DesktopStartCommand>;
}) {
  const [retry, setRetry] = useState<Record<string, boolean>>({});
  const [cancel, setCancel] = useState<Record<string, boolean>>({});
  const [recovery, setRecovery] = useState<{identity:object; checked:Record<string,boolean>}>(
    {identity:execution.identity, checked:{}});
  return <section className="strategy-confirmation" aria-label="本机原执行请求">
    {!execution.loaded && <Notice tone="warning">本机原请求尚未读取成功，暂不能创建新任务。</Notice>}
    {execution.error && <Notice tone="warning">{execution.error}</Notice>}
    {execution.entries.length > 0 && <p className="field-hint">有任务记录可核对，请展开查看处理状态。</p>}
    {execution.loaded && execution.blocksStart && <Notice tone="warning">当前任务已有请求，请展开核对后继续。</Notice>}
    <details>
    <summary>历史任务处理</summary>
    <div className="section-heading"><h2>本机原执行请求</h2>
      <Button disabled={execution.busy} onClick={() => void execution.refresh()}>刷新本机原请求</Button></div>
    <p className="field-hint">先核对原请求，避免重复创建。查询不会重新提交执行；任务创建不表示采集成功。</p>
    {execution.loaded && !execution.entries.length && <p className="field-hint">当前工作空间暂无本机原执行请求。</p>}
    {[...execution.entries].sort((a,b)=>a.requestId.localeCompare(b.requestId)).map((entry,index) => {
      const label = execution.entries.length > 1 ? '记录 ' + (index + 1) : '原执行请求';
      const cancelLabel = execution.entries.length > 1 ? label + ' 对应的任务' : '此任务';
      const receipt = entry.receipt;
      const collection = entry.collection;
      const recoveryChecked = recovery.identity === execution.identity && recovery.checked[entry.requestId] === true;
      const canRecover = collection?.state === 'STATUS' && collection.recoverable;
      const research=entry.kind==='RESEARCH';
      const canRetry = !research&&(entry.operation === 'CANCEL' && canRetryCancel || entry.operation === 'START' && canRetryStart);
      const retryChecked = canRetry && retry[entry.requestId] === true;
      const cancelExists = receipt?.operation === 'START' && execution.entries.some(value => value.operation === 'CANCEL' &&
        (value.request?.task_id === receipt.task_id || value.command?.action === 'CANCEL' && value.command.taskId === receipt.task_id));
      return <article key={entry.requestId} className="task-start-blockers">
        <h3>{research?'公开单源研究启动':{START: '启动任务', CANCEL: '取消任务', CLAIM: '领取任务', RENEW: '续期任务', FINISH:'完成登记',STOP:'停止登记'}[entry.operation]} · {label}</h3>
        {research&&<p className="field-hint">查询仅核对原研究进度，不会重复启动研究。</p>}
        <p>{receipt?.operation === 'START' ? '原启动回执：任务已创建，当时待执行；不是当前任务状态，不代表采集成功。'
          : receipt?.operation === 'CANCEL'||receipt?.operation==='STOP' ? receipt.stop_confirmed ? '服务端已登记停止；本机来源请另行核对。' : '取消已登记，等待停止确认。'
          : receipt?.operation === 'FINISH' ? '已核对历史完成回执；它记录当时结果，不是当前执行授权。'
          : receipt ? '已核对历史租约回执，不代表当前仍有执行授权。'
          : `原请求待核对（${entry.state ? requestStateLabels[entry.state] || '结果尚未确认' : '未查询'}）；未查到不表示请求失败。`}</p>
        {!research&&(entry.operation === 'START' || entry.operation === 'CANCEL') && <label className="check-row">
          <input type="checkbox" checked={retryChecked} disabled={execution.busy || !execution.loaded || !canRetry}
            onChange={event => setRetry(old => ({...old, [entry.requestId]: event.target.checked}))} />
          我确认核对后重试此原{entry.operation === 'START' ? '启动' : '取消'}请求
        </label>}
        {!research&&entry.operation === 'START' && !canRetryStart && <p className="field-hint">启动重试需当前草稿和已确认策略完全一致，且通过全部执行条件；现在仍可只查询。</p>}
        <Button disabled={execution.busy || !execution.loaded}
          onClick={() => void execution.recover(entry, retryChecked, () => validateStart(entry.requestId))}>
          {retryChecked ? '核对并重试原执行请求' : research?'恢复原研究请求':'查询原执行请求'}
        </Button>
        {receipt?.operation === 'START' && <>
          {!research&&execution.collectionAvailable && <>
            <Button disabled={execution.busy || !execution.loaded}
              onClick={() => void execution.collectionStatus(entry)}>读取当前采集状态</Button>
            {collection?.state === 'STATUS' ? <>
              <p>本机采集状态：{{COLLECTING:'采集中', INTERRUPTED:'已中断', UPLOAD_UNKNOWN:'上传结果待核对',
                FINISH_UNKNOWN:'完成登记待核对', COMPLETED:'已完成', STOPPED:'已停止', FAILED:'失败'}[collection.localState]}</p>
              <p>服务端任务状态：{{PENDING:'待执行',RUNNING:'运行中',CANCELLING:'取消中',CANCELED:'已取消',SUCCEEDED:'已完成'}[collection.serverStatus]}</p>
              <p>停止确认：{collection.stopConfirmed ? '已确认' : '尚未确认'} · 已计入记录：{collection.recordsUsed}</p>
            </> : collection ? <p className="field-hint">当前采集状态尚未核实，请稍后重新读取；未将其视为完成或没有原批次。</p> : null}
            <label className="check-row"><input type="checkbox" checked={recoveryChecked}
              disabled={execution.busy || !canRecover} onChange={event => setRecovery({identity:execution.identity,
                checked:{...(recovery.identity === execution.identity ? recovery.checked : {}), [entry.requestId]:event.target.checked}})} />
              我确认仅恢复原批次与原完成请求，不重新采集</label>
            <Button disabled={execution.busy || !execution.loaded || !canRecover || !recoveryChecked}
              onClick={() => {setRecovery({identity:execution.identity,checked:{}}); void execution.recoverCollection(entry, recoveryChecked);}}>
              核对并恢复原批次</Button>
          </>}
          <label className="check-row"><input type="checkbox" checked={cancel[entry.requestId] === true}
            disabled={execution.busy || !!cancelExists} onChange={event => setCancel(old => ({...old, [entry.requestId]: event.target.checked}))} />
            我确认取消{cancelLabel}</label>
          <Button disabled={execution.busy || !execution.loaded || cancel[entry.requestId] !== true || !!cancelExists}
            onClick={() => void execution.cancel(entry, cancel[entry.requestId] === true)}>确认取消{cancelLabel}</Button>
          {cancelExists && <p className="field-hint">此任务已有取消原请求，请核对原取消结果，不重复创建。</p>}
        </>}
      </article>;
    })}
    </details>
  </section>;
}
