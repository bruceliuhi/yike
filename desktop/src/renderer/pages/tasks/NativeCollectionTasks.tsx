import { useEffect, useRef, useState } from "react";
import { useApp } from "../../app/context";
import { useResource } from "../../app/hooks";
import { PlatformLabel } from "../../components/Platform";
import { useTaskDraft, useTaskLibrary } from "../../app/taskDraft";
import { boundedRequest } from "../../app/boundedRequest";
import {
  Button,
  PageHeader,
  Notice,
  Confirm,
  ResourceStatus,
  formatDate,
} from "../../components/ui";
import { useTaskScope } from "./useTaskScope";
import { useDesktopExecution } from "./useDesktopExecution";
import { DesktopExecutionRequests } from "./DesktopExecutionRequests";
import { deviceIdentityStatusSchema } from "../../../shared/deviceIdentity";
import { foregroundCollectionResultSchema } from "../../../shared/foregroundCollection";
import { desktopExecutionResultSchema } from "../../../shared/desktopExecution";
import type { TaskFeedItem, TaskFeedPage } from "../../../shared/taskFeed";
import {SearchCoverage} from './SearchCoverage';
import {ResearchProgress} from './ResearchProgress';
import {newTaskDraft} from '../../domain/models';
const coveragePlatforms={XIAOHONGSHU:'xhs',DOUYIN:'douyin',BILIBILI:'bilibili',ZHIHU:'zhihu',PUBLIC_WEB:'web'} as const;
const statusLabels = {
  PENDING: "待执行",
  RUNNING: "运行中",
  CANCELLING: "取消中",
  CANCELED: "已取消",
  SUCCEEDED: "已完成",
};
const platformLabels = {
  XIAOHONGSHU: "小红书",
  DOUYIN: "抖音",
  BILIBILI: "B站",
  ZHIHU: "知乎",
  PUBLIC_WEB: "公开网站",
};
const platformLabel=(platform:string)=>({PUBLIC_WEB:'web',XIAOHONGSHU:'xhs',DOUYIN:'douyin',BILIBILI:'bilibili',ZHIHU:'zhihu'}[platform]||platform);
const localLabels = {
  COLLECTING: "采集中",
  INTERRUPTED: "已中断",
  UPLOAD_UNKNOWN: "上传待核对",
  FINISH_UNKNOWN: "完成登记待核对",
  COMPLETED: "已完成",
  STOPPED: "已停止",
  FAILED: "失败",
};

export function NativeCollectionTasks() {
  const { route, session } = useApp();
  const id = route.query.get("task") || "";
  // Discard route-specific confirmations and pagination before rendering another user/task.
  return (
    <CollectionTaskView
      key={`${session.authenticated}:${session.userId}:${session.accountScope?.id}:${session.accountScope?.version}:${id}`}
      taskId={id}
    />
  );
}
function CollectionTaskView({ taskId }: { taskId: string }) {
  const { service, session, navigate } = useApp(),
    scope = useTaskScope(taskId),
    execution = useDesktopExecution(null);
  const [library] = useTaskLibrary(session.userId,session.accountScope),
    [, setDraft] = useTaskDraft(session.userId,'once',session.accountScope);
  const [cursor, setCursor] = useState<string>();
  const [confirmation, setConfirmation] = useState<{
    identity: object;
    item: TaskFeedItem;
  } | null>(null);
  const [error, setError] = useState(""),
    [checking, setChecking] = useState(false),
    [checkLocal, setCheckLocal] = useState(false);
  const [recovery, setRecovery] = useState<{kind:'upload'|'continue'; item:TaskFeedItem; identity:object; credentialVersion:number}|null>(null);
  const [recoveryNotice, setRecoveryNotice] = useState('');
  const data = useResource(
    async (signal) => {
      if (!session.authenticated) throw new Error("请先登录，再查看采集任务。");
      if (taskId)
        return {
          item: await service.taskFeed!.get(taskId, signal),
          page: null as TaskFeedPage | null,
        };
      return {
        item: null as TaskFeedItem | null,
        page: await service.taskFeed!.list(
          { limit: 20, ...(cursor ? { cursor } : {}) },
          signal,
        ),
      };
    },
    [scope.identity, cursor],
  );
  const device = useResource(
    async () =>
      service.deviceIdentity
        ? deviceIdentityStatusSchema.parse(
            await service.deviceIdentity.getStatus(),
          )
        : null,
    [scope.identity],
  );
  const item = data.data?.item,
    page = data.data?.page;
  const [staleObservation, setStaleObservation] = useState<typeof data.data>();
  const latestObservation = useRef(data.data);
  latestObservation.current = data.data;
  const statusStale = !!data.data && staleObservation === data.data;
  useEffect(() => {
    const observed = data.data;
    if (!session.authenticated || !item || item.research || item.task_id !== taskId ||
      data.loading || data.error || statusStale ||
      !['PENDING', 'RUNNING', 'CANCELLING'].includes(item.status)) return;
    const controller = new AbortController();
    const current = () => !controller.signal.aborted && scope.current() &&
      latestObservation.current === observed;
    const timer = setTimeout(async () => {
      try {
        const fresh = await boundedRequest(signal => service.taskFeed!.get(taskId, signal), {
          signal: controller.signal, timeoutMessage: '状态更新超时，请刷新任务。',
        });
        if (!current()) return;
        if (fresh.task_id !== item.task_id || fresh.run_id !== item.run_id ||
          fresh.device_id !== item.device_id || fresh.start_request_id !== item.start_request_id || fresh.research)
          throw new Error('Task observation mismatch');
        data.setData({ item: fresh, page: null });
      } catch {
        if (current()) setStaleObservation(observed);
      }
    }, 3000);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [data.data, data.loading, data.error, data.setData, scope.identity, statusStale, taskId]);
  const sameDevice =
    !!item &&
    device.data?.state === "READY" &&
    device.data.deviceId === item.device_id;
  const cancels = execution.entries.filter(
    (entry) =>
      entry.operation === "CANCEL" &&
      (!taskId ||
        entry.request?.task_id === taskId ||
        (entry.command?.action === "CANCEL" &&
          entry.command.taskId === taskId)),
  );
  const local = useResource(async () => {
    if (!checkLocal || !item || item.research || !sameDevice || !service.foregroundCollection)
      return null;
    const result = foregroundCollectionResultSchema.parse(
      await service.foregroundCollection.execute({
        action: "STATUS",
        taskId: item.task_id,
      }),
    );
    if (result.state === "STATUS" && result.taskId !== item.task_id)
      throw new Error("采集状态与当前任务不一致。");
    return result;
  }, [scope.identity, checkLocal, item?.task_id, sameDevice]);
  const canCancel =
    sameDevice &&
    !!service.execution &&
    execution.loaded &&
    !execution.busy &&
    !checking &&
    !cancels.length &&
    (item?.status === "PENDING" || item?.status === "RUNNING");
  const canRecover = !item?.research && sameDevice && !!service.foregroundCollection && !checking && !execution.busy &&
    !data.loading && !data.error && !local.loading && !local.error && local.data?.state==='STATUS' &&
    local.data.localState!=='COLLECTING' && ['PENDING','RUNNING'].includes(item!.status) &&
    ['PENDING','RUNNING'].includes(local.data.serverStatus);
  function chooseRecovery(kind:'upload'|'continue') {
    if(canRecover && item && device.data?.state==='READY')
      setRecovery({kind,item:structuredClone(item),identity:scope.identity,credentialVersion:device.data.credentialVersion});
  }
  async function confirmRecovery() {
    const selected=recovery;
    if(!canRecover || !selected || selected.identity!==scope.identity || selected.item.task_id!==item?.task_id)return;
    setChecking(true);setError('');setRecoveryNotice('');
    const wait = <T,>(operation:()=>Promise<T>) => boundedRequest(operation,{timeoutMessage:'恢复请求等待超时，请核对原请求，不要重新采集。'});
    try {
      const current=deviceIdentityStatusSchema.parse(await wait(()=>service.deviceIdentity!.getStatus()));
      if(!scope.current())return;
      if(current.state!=='READY'||current.deviceId!==selected.item.device_id||current.credentialVersion!==selected.credentialVersion)
        throw new Error('设备身份已变化，请刷新后重新确认。');
      const fresh=await wait(()=>service.taskFeed!.get(selected.item.task_id));
      if(!scope.current())return;
      if(fresh.task_id!==selected.item.task_id||fresh.run_id!==selected.item.run_id||fresh.device_id!==current.deviceId||
        fresh.start_request_id!==selected.item.start_request_id||!['PENDING','RUNNING'].includes(fresh.status))
        throw new Error('任务状态已变化，请刷新后重新确认。');
      if(selected.kind==='upload') {
        const result=foregroundCollectionResultSchema.parse(await wait(()=>service.foregroundCollection!.execute({action:'RECOVER',taskId:fresh.task_id,humanConfirmed:true,retry:true})));
        if(!scope.current())return;
        if(result.state!=='STATUS'||result.taskId!==fresh.task_id)throw new Error('原上传结果尚未核实，请查询本机状态。');
        setRecoveryNotice('已核对原上传；没有重新采集，整项任务是否完成以最新状态为准。');
      } else {
        if(fresh.mode!=='once'||!service.execution)throw new Error('当前任务不支持手工续接。');
        const original=desktopExecutionResultSchema.parse(await wait(()=>service.execution!.execute({action:'RECOVER',requestId:fresh.start_request_id,retry:false})));
        if(!scope.current())return;
        if(original.state!=='RECORDED'||original.receipt.operation!=='START'||original.receipt.request_id!==fresh.start_request_id||
          original.receipt.task_id!==fresh.task_id||original.receipt.run_id!==fresh.run_id||
          original.receipt.platform_runs.length!==fresh.platform_runs.length||original.receipt.platform_runs.some((p,i)=>
            p.platform_run_id!==fresh.platform_runs[i].platform_run_id||p.platform!==fresh.platform_runs[i].platform))
          throw new Error('原启动回执尚未核实，不会创建新的采集请求。');
        const result=desktopExecutionResultSchema.parse(await wait(()=>service.execution!.execute({action:'RECOVER',requestId:fresh.start_request_id,retry:true,humanConfirmed:true})));
        if(!scope.current())return;
        if(result.state!=='RECORDED'||result.receipt.operation!=='START'||JSON.stringify(result.receipt)!==JSON.stringify(original.receipt))
          throw new Error('续接结果尚未核实，请查询本机状态，不要创建替代任务。');
        setRecoveryNotice('已核对原启动请求；本机仅在原记录证明尚未执行时继续，不会重采已执行平台。请查看最新本机状态。');
      }
      setRecovery(null);void data.reload();void local.reload();
    } catch(e) {if(scope.current())setError(e instanceof Error?e.message:'恢复尚未核实，请查询原请求。');}
    finally {if(scope.current())setChecking(false);}
  }
  async function confirmCancel() {
    const selected = confirmation;
    if (
      !canCancel ||
      !selected ||
      selected.identity !== scope.identity ||
      selected.item.task_id !== item?.task_id
    )
      return;
    setChecking(true);
    setError("");
    try {
      const current = deviceIdentityStatusSchema.parse(
        await boundedRequest(() => service.deviceIdentity!.getStatus(), {
          timeoutMessage: "设备核对超时，未提交取消。",
        }),
      );
      if (!scope.current()) return;
      if (
        current.state !== "READY" ||
        current.deviceId !== selected.item.device_id
      )
        throw new Error("设备身份已变化，请刷新后重新确认。");
      await execution.cancelTask(selected.item.task_id, true);
      if (scope.current()) {
        setConfirmation(null);
        void data.reload();
        if (checkLocal) void local.reload();
      }
    } catch (e) {
      if (scope.current())
        setError(e instanceof Error ? e.message : "取消未核实，请查询原请求。");
    } finally {
      if (scope.current()) setChecking(false);
    }
  }
  return (
    <>
      <PageHeader
        title={taskId ? "采集任务详情" : "线索采集"}
        description="查看已启动任务和实际入库进度；采集记录仍需判断，不等于有效商机。"
        back={taskId ? () => navigate("/collection") : undefined}
        extra={
          <>
            <Button
              disabled={data.loading}
              onClick={() => {
                void data.reload();
                void device.reload();
              }}
            >
              刷新任务
            </Button>
            <Button onClick={()=>{setDraft(newTaskDraft('once'));navigate('/tasks/new');}}>
              新建普通采集
            </Button>
            <Button variant="primary" onClick={() => navigate("/tasks/new")}>
              新建采集
            </Button>
          </>
        }
      />
      <ResourceStatus loading={data.loading} error={data.error} />
      {statusStale && <Notice tone="warning">状态更新失败，当前显示上次结果，请刷新任务。</Notice>}
      {error && <Notice tone="warning">{error}</Notice>}
      {recoveryNotice && <Notice>{recoveryNotice}</Notice>}
      {page && (
        <section className="panel" aria-label="真实采集任务">
          {!page.items.length ? (
            <p>本页没有采集任务。</p>
          ) : (
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>任务</th>
                    <th>类型 / 平台</th>
                    <th>进度</th>
                    <th>入库记录 / 上限</th>
                    <th>创建时间</th>
                  </tr>
                </thead>
                <tbody>
                  {page.items.map((row, index) => (
                    <tr key={row.task_id}>
                      <td>
                        <Button
                          variant="ghost"
                          onClick={() =>
                            navigate(`/collection?task=${row.task_id}`)
                          }
                        >
                          {row.name || `采集任务 ${index + 1}`}
                        </Button>
                      </td>
                      <td>
                        {row.research ? '公开研究' : row.mode === "monitor"
                          ? "监控轮次"
                          : row.mode === "once"
                            ? "单次采集"
                            : "历史任务"}{" "}
                        ·{" "}
                        <span className="platform-list">
                          {row.platform_runs.map((p) => (
                            <PlatformLabel key={p.platform_run_id} platform={platformLabel(p.platform)} size={16} />
                          ))}
                        </span>
                      </td>
                      <td>{row.research
                        ? <Button variant="ghost" onClick={() => navigate(`/collection?task=${row.task_id}`)}>查看研究进度</Button>
                        : statusLabels[row.status]}</td>
                      <td>
                        {row.records_used} / {row.max_records}
                      </td>
                      <td>{formatDate(row.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="task-footer">
            <Button disabled={!cursor} onClick={() => setCursor(undefined)}>
              返回首页
            </Button>
            <Button
              disabled={!page.next_cursor}
              onClick={() => setCursor(page.next_cursor!)}
            >
              下一页
            </Button>
          </div>
        </section>
      )}
      {item?.research && <ResearchProgress key={item.task_id} taskId={item.task_id} runId={item.run_id}
        taskStatus={item.status} onTerminal={()=>void data.reload()}/>}
      {item && (
        <section className="panel" aria-label="真实采集详情">
          <h2>{item.name || "采集任务"}</h2>
          {!item.research && <p>
            当前状态：{statusLabels[item.status]}
          </p>}
          {['CANCELLING','CANCELED'].includes(item.status) && !item.stop_confirmed && <Notice tone="warning">停止结果尚未确认，请刷新当前任务，不要重复启动。</Notice>}
          <details className="usage-advanced">
          <summary>查看运行详情</summary>
          <p>已保存记录：{item.records_used} / {item.max_records}（不是已确认商机数量）</p>
          <p>
            创建时间：{formatDate(item.created_at)} · 执行期限：
            {formatDate(item.deadline_at)}
          </p>
          <p>
            服务端停止登记：{item.stop_confirmed ? "已确认" : "尚未确认"}
            {item.research ? '；已发出研究请求是否结束以研究状态为准。' : '；本机来源是否停止需另行查询。'}
          </p>
          <table className="data-table">
            <thead>
              <tr>
                <th>平台</th>
                <th>{item.research ? '入库状态' : '状态'}</th>
                <th>入库记录</th>
              </tr>
            </thead>
            <tbody>
              {item.platform_runs.map((row) => (
                <tr key={row.platform_run_id}>
                  <td>{platformLabels[row.platform]}</td>
                  <td>{statusLabels[row.status]}</td>
                  <td>{row.records_used}</td>
                </tr>
              ))}
            </tbody>
          </table>
          </details>
          {item.mode === "monitor" && (
            <Notice>
              这是一次监控轮次；取消本次采集不会暂停后续计划。可前往监控任务管理计划。
            </Notice>
          )}
          {!sameDevice && (
            <Notice>
              请在创建任务的设备完成身份核对后取消或查询本机来源；历史任务仍可查看。
            </Notice>
          )}
          <div className="task-footer">
            <Button
              variant="danger"
              disabled={!canCancel}
              onClick={() =>
                setConfirmation({ identity: scope.identity, item })
              }
            >
              取消本次采集
            </Button>
            {!item.research && <Button
              disabled={
                !sameDevice ||
                !service.foregroundCollection ||
                (local.loading && checkLocal)
              }
              onClick={() => {
                if (checkLocal) void local.reload();
                else setCheckLocal(true);
              }}
            >
              查询本机采集状态
            </Button>}
            <Button onClick={() => navigate(`/candidates?task=${item.task_id}`)}>
              查看本次发现线索
            </Button>
            {item.mode === "monitor" && (
              <Button onClick={() => navigate("/monitors")}>
                管理监控计划
              </Button>
            )}
          </div>
          {checkLocal && !item.research && (
            <>
              <ResourceStatus loading={local.loading} error={local.error} />
              {local.data?.state === "STATUS" ? (
                <p>
                  本机执行记录：{localLabels[local.data.localState]}
                  ；服务端停止登记：
                  {local.data.stopConfirmed ? "已确认" : "尚未确认"}
                  。这不是对平台页面实际停止的独立确认。
                </p>
              ) : (
                local.data && (
                  <Notice tone="warning">
                    本机来源状态未核实，不表示任务已停止或没有采集结果。
                  </Notice>
                )
              )}
              {local.data?.state==='STATUS' && (
                <div className="task-footer">
                  <Button disabled={!canRecover||!local.data.recoverable} onClick={()=>chooseRecovery('upload')}>核对原上传</Button>
                  {item.mode==='once' && service.execution && <Button disabled={!canRecover} onClick={()=>chooseRecovery('continue')}>继续未执行平台</Button>}
                </div>
              )}
            </>
          )}
        </section>
      )}
      {item && !item.research && (
        <details className="usage-advanced">
          <summary>查看搜索详情</summary>
          <SearchCoverage run={{id:item.task_id,profileId:item.profile_version_id,
            profileVersion:item.profile_version,platforms:item.platform_runs.map(row=>coveragePlatforms[row.platform])}}
            refreshKey={JSON.stringify([item.status,item.records_used,item.platform_runs])}
            returnPath={`/collection?task=${encodeURIComponent(item.task_id)}`}/>
        </details>
      )}
      {service.execution && cancels.length > 0 && (
        <DesktopExecutionRequests
          execution={{ ...execution, entries: cancels }}
          canRetryStart={false}
          canRetryCancel={sameDevice}
          validateStart={async () => {
            throw new Error("请在原配置页核对启动。");
          }}
        />
      )}
      {taskId && execution.error && (
        <Notice tone="warning">{execution.error}</Notice>
      )}
      {!taskId && library.some((draft) => draft.mode === "once") && (
        <section className="panel" aria-label="本机采集草稿">
          <h2>本机草稿</h2>
          {library
            .filter((draft) => draft.mode === "once")
            .map((draft) => (
              <div className="task-footer" key={draft.id}>
                <span>{draft.name}</span>
                <Button
                  onClick={() => {
                    setDraft(structuredClone(draft));
                    navigate("/tasks/new");
                  }}
                >
                  继续配置
                </Button>
              </div>
            ))}
        </section>
      )}
      {confirmation?.identity === scope.identity && (
        <Confirm
          title="取消本次采集"
          confirmText="确认取消"
          loading={checking || execution.busy}
          onCancel={() => setConfirmation(null)}
          onConfirm={() => void confirmCancel()}
        >
          <p>
            确认取消「{confirmation.item.name || "采集任务"}
            」？已入库记录保留；停止结果以原请求与本机状态核对为准。
          </p>
        </Confirm>
      )}
      {recovery?.identity===scope.identity && <Confirm title={recovery.kind==='upload'?'核对原上传':'继续未执行平台'}
        confirmText={recovery.kind==='upload'?'确认核对':'确认继续'} loading={checking}
        onCancel={()=>setRecovery(null)} onConfirm={()=>void confirmRecovery()}>
        <p>{recovery.kind==='upload'?'仅核对原上传及完成记录，不打开平台重新采集。':'重新核对原任务与账号，仅继续有证据证明从未执行的平台；未知或已执行的平台不会重采。'}</p>
      </Confirm>}
    </>
  );
}
