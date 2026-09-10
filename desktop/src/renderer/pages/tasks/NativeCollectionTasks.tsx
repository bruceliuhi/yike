import { useState } from "react";
import { useApp } from "../../app/context";
import { useResource } from "../../app/hooks";
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
import type { TaskFeedItem, TaskFeedPage } from "../../../shared/taskFeed";
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
  const [library] = useTaskLibrary(),
    [, setDraft] = useTaskDraft();
  const [cursor, setCursor] = useState<string>();
  const [confirmation, setConfirmation] = useState<{
    identity: object;
    item: TaskFeedItem;
  } | null>(null);
  const [error, setError] = useState(""),
    [checking, setChecking] = useState(false),
    [checkLocal, setCheckLocal] = useState(false);
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
    if (!checkLocal || !item || !sameDevice || !service.foregroundCollection)
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
            <Button variant="primary" onClick={() => navigate("/tasks/new")}>
              新建采集
            </Button>
          </>
        }
      />
      <ResourceStatus loading={data.loading} error={data.error} />
      {error && <Notice tone="warning">{error}</Notice>}
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
                    <th>服务端状态</th>
                    <th>入库记录 / 上限</th>
                    <th>创建时间</th>
                  </tr>
                </thead>
                <tbody>
                  {page.items.map((row) => (
                    <tr key={row.task_id}>
                      <td>
                        <Button
                          variant="ghost"
                          onClick={() =>
                            navigate(`/collection?task=${row.task_id}`)
                          }
                        >
                          {row.name || `采集任务 ${row.task_id.slice(0, 8)}`}
                        </Button>
                      </td>
                      <td>
                        {row.mode === "monitor"
                          ? "监控轮次"
                          : row.mode === "once"
                            ? "单次采集"
                            : "历史任务"}{" "}
                        ·{" "}
                        {row.platform_runs
                          .map((p) => platformLabels[p.platform])
                          .join("、")}
                      </td>
                      <td>{statusLabels[row.status]}</td>
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
      {item && (
        <section className="panel" aria-label="真实采集详情">
          <h2>{item.name || "采集任务"}</h2>
          <p>任务编号：{item.task_id}</p>
          <p>
            服务端状态：{statusLabels[item.status]} · 入库记录：
            {item.records_used} / {item.max_records}
          </p>
          <p>
            创建时间：{formatDate(item.created_at)} · 执行期限：
            {formatDate(item.deadline_at)}
          </p>
          <p>
            服务端停止登记：{item.stop_confirmed ? "已确认" : "尚未确认"}
            ；本机来源是否停止需另行查询。
          </p>
          <table className="data-table">
            <thead>
              <tr>
                <th>平台</th>
                <th>状态</th>
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
            <Button
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
            </Button>
            <Button onClick={() => navigate("/candidates")}>
              前往待判断线索
            </Button>
            {item.mode === "monitor" && (
              <Button onClick={() => navigate("/monitors")}>
                管理监控计划
              </Button>
            )}
          </div>
          {checkLocal && (
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
            </>
          )}
          <details>
            <summary>原始绑定</summary>
            <p>画像版本：{item.profile_version_id}</p>
            <p>策略版本：{item.strategy_version_id}</p>
            <p>原启动请求：{item.start_request_id}</p>
          </details>
        </section>
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
            确认取消「{confirmation.item.name || confirmation.item.task_id}
            」？已入库记录保留；停止结果以原请求与本机状态核对为准。
          </p>
        </Confirm>
      )}
    </>
  );
}
