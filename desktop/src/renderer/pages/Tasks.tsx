import { useState } from "react";
import {
  Plus,
  MagnifyingGlass,
  ArrowRight,
  Globe,
  ArrowClockwise,
} from "@phosphor-icons/react";
import { useApp } from "../app/context";
import { useAction, useResource } from "../app/hooks";
import { useTaskDraft, useTaskLibrary } from "../app/taskDraft";
import {
  Badge,
  Button,
  Confirm,
  Empty,
  Notice,
  PageHeader,
  ResourceStatus,
  Tabs,
  formatDate,
} from "../components/ui";
import {
  PLATFORMS,
  newTaskDraft,
  type TaskAction,
  type TaskDraft,
  type TaskRun,
  type TaskPlatformStage,
  type PlatformId,
} from "../domain/models";

const statuses: Record<string, string> = {
  PENDING: "排队中",
  RUNNING: "运行中",
  PAUSED: "已暂停",
  COMPLETED: "已完成",
  FAILED: "运行失败",
  CANCELED: "已取消",
  BLOCKED: "需要处理",
  PARTIAL: "部分完成",
  OFFLINE: "设备离线",
  RETRYING: "正在重试",
  CANCELLING: "正在取消",
};
const platformStatuses: Record<string, string> = {
  PENDING: "等待执行",
  WAITING: "等待执行",
  RUNNING: "运行中",
  COMPLETED: "执行完成",
  SUCCESS: "执行完成",
  NO_NEW: "暂无新增",
  LOGIN_EXPIRED: "登录失效",
  EXPIRED: "登录失效",
  RATE_LIMITED: "暂时受限",
  LIMITED: "暂时受限",
  FAILED: "执行失败",
  OFFLINE: "设备离线",
  PAUSED: "已暂停",
  CANCELED: "已取消",
  BLOCKED: "需要处理",
  RETRYING: "正在重试",
};
const actionLabels: Record<TaskAction, string> = {
  pause: "暂停",
  resume: "恢复",
  retry: "重试",
  cancel: "取消",
};
const actionHints: Record<TaskAction, string> = {
  pause: "提交暂停请求；实际停止时间以执行服务返回为准。",
  resume: "恢复前由执行服务重新检查账号、设备与调度条件。",
  retry: "提交重试请求；失败阶段与重试范围由执行服务确认。",
  cancel: "提交取消请求；已经采集的记录不会在此操作中删除。",
};
function platformName(id: PlatformId) {
  return PLATFORMS.find((p) => p.id === id)?.name || id;
}
function decodeTaskId(value: string) {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}
function stateTone(
  status: string,
): "neutral" | "blue" | "green" | "orange" | "red" {
  if (["RUNNING", "RETRYING"].includes(status)) return "blue";
  if (["COMPLETED", "SUCCESS", "NO_NEW"].includes(status)) return "green";
  if (status === "FAILED") return "red";
  if (
    [
      "BLOCKED",
      "PARTIAL",
      "OFFLINE",
      "LOGIN_EXPIRED",
      "EXPIRED",
      "RATE_LIMITED",
      "LIMITED",
    ].includes(status)
  )
    return "orange";
  return "neutral";
}
function taskActions(status: string): TaskAction[] {
  if (status === "RUNNING" || status === "RETRYING") return ["pause", "cancel"];
  if (status === "PAUSED") return ["resume", "cancel"];
  if (status === "FAILED") return ["retry"];
  if (status === "PARTIAL" || status === "BLOCKED") return ["retry", "cancel"];
  if (status === "PENDING" || status === "OFFLINE") return ["cancel"];
  return [];
}
function RunActions({
  run,
  onAction,
  disabled = false,
  detail = false,
}: {
  run: TaskRun;
  onAction: (run: TaskRun, action: TaskAction) => void;
  disabled?: boolean;
  detail?: boolean;
}) {
  return (
    <>
      {taskActions(run.status).map((action) => (
        <Button
          key={action}
          variant={
            action === "cancel" ? "ghost" : detail ? "primary" : "secondary"
          }
          disabled={disabled}
          onClick={() => onAction(run, action)}
        >
          {actionLabels[action]}
          {detail ? "任务" : ""}
        </Button>
      ))}
    </>
  );
}
function count(value: number | undefined) {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0
    ? value
    : "—";
}
function stageDescription(stage: TaskPlatformStage | undefined): string {
  if (stage?.reason) return stage.reason;
  if (!stage) return "尚未收到该平台的执行状态。";
  switch (stage.status) {
    case "LOGIN_EXPIRED":
    case "EXPIRED":
      return "请重新连接账号，再检查当前任务状态。";
    case "RATE_LIMITED":
    case "LIMITED":
      return "平台当前限制访问，请等待可执行时间或检查平台提示。";
    case "RUNNING":
    case "RETRYING":
      return "正在执行，新增结果以服务返回为准。";
    case "NO_NEW":
      return "本次执行未发现新增线索。";
    case "OFFLINE":
      return "执行设备离线，请检查设备连接。";
    case "FAILED":
      return "本次执行失败，详细原因暂未返回。";
    case "COMPLETED":
    case "SUCCESS":
      return "本次平台执行已完成。";
    case "PAUSED":
      return "平台执行已暂停。";
    case "CANCELED":
      return "平台执行已取消。";
    case "PENDING":
    case "WAITING":
      return "等待执行服务安排本次运行。";
    default:
      return "请刷新状态，或查看执行记录中的具体原因。";
  }
}
function MonitorDetail({
  run,
  onAction,
  disabled,
}: {
  run: TaskRun;
  onAction: (run: TaskRun, action: TaskAction) => void;
  disabled: boolean;
}) {
  const { navigate } = useApp();
  const [tab, setTab] = useState("platforms");
  const [chosen, setChosen] = useState<PlatformId | null>(null);
  const platform =
    chosen && run.platforms.includes(chosen) ? chosen : run.platforms[0];
  const stage = run.platformStages?.find((item) => item.platform === platform);
  const schedule = run.schedule;
  const reconnect = () => {
    if (platform)
      navigate(
        "/connections?" +
          new URLSearchParams({
            connect: platform,
            returnTo: `/monitors/${encodeURIComponent(run.id)}`,
          }),
      );
  };
  return (
    <>
      <dl className="fact-strip monitor-facts">
        <div>
          <dt>监控任务</dt>
          <dd>{run.name}</dd>
        </div>
        <div>
          <dt>监控关键词</dt>
          <dd>{run.keywords?.length ? run.keywords.join("、") : "待读取"}</dd>
        </div>
        <div>
          <dt>监控区域</dt>
          <dd>{run.regions || "待读取"}</dd>
        </div>
        <div>
          <dt>创建时间</dt>
          <dd>{formatDate(run.createdAt || "")}</dd>
        </div>
        <div>
          <dt>任务状态</dt>
          <dd>
            <Badge tone={stateTone(run.status)}>
              {statuses[run.status] || "状态待确认"}
            </Badge>
          </dd>
        </div>
      </dl>
      {run.failureReason && <Notice tone="warning">{run.failureReason}</Notice>}
      <Tabs
        active={tab}
        onChange={setTab}
        items={[
          { key: "platforms", label: "平台状态" },
          { key: "events", label: "执行记录" },
          { key: "config", label: "任务配置" },
        ]}
      />
      {tab === "platforms" && (
        <>
          <div className="task-layout">
            <section aria-label="平台运行状态">
              <div className="section-heading">
                <h2>平台运行状态</h2>
                <span className="muted text-small">
                  最近更新 {formatDate(run.updatedAt || "")}
                </span>
              </div>
              {run.platforms.length ? (
                <div className="table-scroll">
                  <table className="monitor-platform-table">
                    <thead>
                      <tr>
                        <th>平台</th>
                        <th>运行状态</th>
                        <th>本次执行新增</th>
                      </tr>
                    </thead>
                    <tbody>
                      {run.platforms.map((id) => {
                        const item = run.platformStages?.find(
                          (value) => value.platform === id,
                        );
                        return (
                          <tr
                            key={id}
                            className={id === platform ? "selected" : ""}
                          >
                            <td>
                              <button
                                className="platform-status-select"
                                aria-label={`查看${platformName(id)}状态`}
                                aria-pressed={id === platform}
                                onClick={() => setChosen(id)}
                              >
                                <Globe size={18} aria-hidden />
                                {platformName(id)}
                              </button>
                            </td>
                            <td>
                              <Badge tone={stateTone(item?.status || "")}>
                                {item
                                  ? platformStatuses[item.status] ||
                                    "状态待确认"
                                  : "待读取"}
                              </Badge>
                              {item?.phase && (
                                <p className="field-hint">{item.phase}</p>
                              )}
                            </td>
                            <td>{count(item?.newCount)}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              ) : (
                <Empty
                  title="暂无平台范围"
                  description="执行服务返回平台范围后，会在这里展示。"
                />
              )}
            </section>
            <aside className="task-aside" aria-label="平台状态详情">
              {platform ? (
                <>
                  <div className="section-heading">
                    <h2 className="platform-label">
                      <Globe size={24} aria-hidden />
                      {platformName(platform)}
                    </h2>
                    <Badge tone={stateTone(stage?.status || "")}>
                      {stage
                        ? platformStatuses[stage.status] || "状态待确认"
                        : "待读取"}
                    </Badge>
                  </div>
                  <p>{stageDescription(stage)}</p>
                  <dl className="detail-list">
                    <div>
                      <dt>执行账号</dt>
                      <dd>{stage?.accountName || "待读取"}</dd>
                    </div>
                    {stage?.phase && (
                      <div>
                        <dt>当前阶段</dt>
                        <dd>{stage.phase}</dd>
                      </div>
                    )}
                    <div>
                      <dt>状态更新时间</dt>
                      <dd>{formatDate(stage?.updatedAt || "")}</dd>
                    </div>
                    {stage?.nextRetryAt && (
                      <div>
                        <dt>最早重试时间</dt>
                        <dd>{formatDate(stage.nextRetryAt)}</dd>
                      </div>
                    )}
                  </dl>
                  {stage &&
                    ["LOGIN_EXPIRED", "EXPIRED"].includes(stage.status) &&
                    platform !== "web" && (
                      <Button variant="primary" onClick={reconnect}>
                        重新连接
                      </Button>
                    )}
                  {stage?.status === "OFFLINE" && (
                    <Button onClick={() => navigate("/settings")}>
                      检查执行设备
                    </Button>
                  )}
                  {stage?.status === "FAILED" &&
                    taskActions(run.status).includes("retry") && (
                      <Button
                        disabled={disabled}
                        onClick={() => onAction(run, "retry")}
                      >
                        <ArrowClockwise />
                        重试任务
                      </Button>
                    )}
                </>
              ) : (
                <Empty title="选择平台查看状态" />
              )}
            </aside>
          </div>
          <section className="sample-section" aria-label="执行统计">
            <div className="section-heading">
              <h2>执行统计</h2>
              <span className="muted text-small">以实际返回结果为准</span>
            </div>
            <dl className="fact-strip">
              <div>
                <dt>今日新增</dt>
                <dd>{count(run.statistics?.today)}</dd>
              </div>
              <div>
                <dt>本周新增</dt>
                <dd>{count(run.statistics?.week)}</dd>
              </div>
              <div>
                <dt>本月新增</dt>
                <dd>{count(run.statistics?.month)}</dd>
              </div>
              <div>
                <dt>累计新增</dt>
                <dd>{count(run.statistics?.total)}</dd>
              </div>
            </dl>
          </section>
        </>
      )}
      {tab === "events" && (
        <section aria-label="执行记录">
          <div className="section-heading">
            <h2>执行记录</h2>
            <span className="muted text-small">
              最近运行 {formatDate(run.lastRunAt || "")}
            </span>
          </div>
          {run.events?.length ? (
            <div className="table-scroll">
              <table className="monitor-events-table">
                <thead>
                  <tr>
                    <th>时间</th>
                    <th>平台</th>
                    <th>事件</th>
                    <th>级别</th>
                  </tr>
                </thead>
                <tbody>
                  {run.events.map((event, index) => (
                    <tr key={`${event.id}:${index}`}>
                      <td>{formatDate(event.occurredAt || "")}</td>
                      <td>
                        {event.platform ? platformName(event.platform) : "任务"}
                      </td>
                      <td>{event.message}</td>
                      <td>
                        {event.level ? (
                          <Badge
                            tone={
                              event.level === "error"
                                ? "red"
                                : event.level === "warning"
                                  ? "orange"
                                  : "neutral"
                            }
                          >
                            {event.level === "error"
                              ? "错误"
                              : event.level === "warning"
                                ? "提醒"
                                : "信息"}
                          </Badge>
                        ) : (
                          "—"
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Empty
              title="暂无运行记录"
              description="执行服务返回阶段和事件后，会在这里展示。"
            />
          )}
        </section>
      )}
      {tab === "config" && (
        <div className="configuration-summary">
          <section>
            <h2>业务画像与范围</h2>
            <dl className="detail-list">
              <div>
                <dt>业务画像</dt>
                <dd>{run.profileName || run.profileId || "待读取"}</dd>
              </div>
              <div>
                <dt>画像版本</dt>
                <dd>
                  {typeof run.profileVersion === "number"
                    ? `v${run.profileVersion}`
                    : "待读取"}
                </dd>
              </div>
              <div>
                <dt>监控关键词</dt>
                <dd>
                  {run.keywords?.length ? run.keywords.join("、") : "待读取"}
                </dd>
              </div>
              <div>
                <dt>监控区域</dt>
                <dd>{run.regions || "待读取"}</dd>
              </div>
              <div>
                <dt>监控平台</dt>
                <dd>
                  {run.platforms.map(platformName).join("、") || "待读取"}
                </dd>
              </div>
            </dl>
          </section>
          <section>
            <h2>运行设置</h2>
            <dl className="detail-list">
              <div>
                <dt>执行频率</dt>
                <dd>
                  {schedule
                    ? schedule.kind === "daily"
                      ? `每日 ${schedule.times.join("、")}`
                      : `每 ${schedule.interval} 小时`
                    : "待读取"}
                </dd>
              </div>
              <div>
                <dt>执行窗口</dt>
                <dd>
                  {schedule
                    ? schedule.kind === "interval"
                      ? `${schedule.start}–${schedule.end}`
                      : "按每日设定时间"
                    : "待读取"}
                </dd>
              </div>
              <div>
                <dt>时区</dt>
                <dd>{schedule?.timezone || "待读取"}</dd>
              </div>
              <div>
                <dt>最近运行</dt>
                <dd>{formatDate(run.lastRunAt || "")}</dd>
              </div>
              <div>
                <dt>下次计划</dt>
                <dd>{formatDate(run.nextRunAt || "")}</dd>
              </div>
            </dl>
          </section>
        </div>
      )}
    </>
  );
}
export function TasksPage() {
  const { service, session, route, navigate, notify } = useApp();
  const monitor = route.path.startsWith("/monitors");
  const [tab, setTab] = useState("all");
  const [search, setSearch] = useState("");
  const [library, setLibrary] = useTaskLibrary(session.userId);
  const [currentDraft, setDraft] = useTaskDraft(session.userId);
  const tasks = useResource(() => service.tasks(), [service, session.userId]);
  const action = useAction();
  const [pending, setPending] = useState<{
    run: TaskRun;
    action: TaskAction;
  } | null>(null);
  const [deleting, setDeleting] = useState<TaskDraft | null>(null);
  const mode = monitor ? "monitor" : "once";
  const id = route.path.startsWith("/monitors/")
    ? decodeTaskId(route.path.slice("/monitors/".length))
    : null;
  const runs = (tasks.data || []).filter(
    (t) =>
      t.mode === mode &&
      t.name.toLocaleLowerCase().includes(search.toLocaleLowerCase()) &&
      (tab === "all" ||
        t.status === tab ||
        (tab === "FAILED" &&
          ["BLOCKED", "PARTIAL", "OFFLINE"].includes(t.status))),
  );
  const drafts = library.filter(
    (t) =>
      t.mode === mode &&
      t.name.toLocaleLowerCase().includes(search.toLocaleLowerCase()) &&
      (tab === "all" || tab === "draft"),
  );
  const create = () => {
    setDraft(newTaskDraft(mode));
    navigate(monitor ? "/tasks/new?mode=monitor" : "/tasks/new");
  };
  const edit = (draft: TaskDraft) => {
    const latest =
      currentDraft.id === draft.id && currentDraft.revision >= draft.revision
        ? currentDraft
        : draft;
    setDraft(structuredClone(latest));
    navigate(
      latest.mode === "monitor" ? "/tasks/new?mode=monitor" : "/tasks/new",
    );
  };
  const requestAction = (run: TaskRun, next: TaskAction) => {
    action.setError("");
    setPending({ run, action: next });
  };
  const perform = async () => {
    if (!pending) return;
    await action.run(async () => {
      await service.taskAction(pending.run.id, pending.action);
      setPending(null);
      await tasks.reload();
      notify("操作已提交，请以最新任务状态为准。", "success");
    });
  };
  const selected = tasks.data?.find((t) => t.id === id && t.mode === "monitor");
  const operationDialog = pending && (
    <Confirm
      title={`${actionLabels[pending.action]}任务？`}
      danger={pending.action === "cancel"}
      loading={action.busy}
      onCancel={() => {
        if (!action.busy) setPending(null);
      }}
      onConfirm={() => void perform()}
    >
      <p>{pending.run.name}</p>
      <p className="field-hint">{actionHints[pending.action]}</p>
      {action.error && <Notice tone="error">{action.error}</Notice>}
    </Confirm>
  );
  if (id)
    return (
      <>
        <PageHeader
          title={selected?.name || "监控任务详情"}
          back={() => navigate("/monitors")}
          extra={
            <>
              <Button
                disabled={tasks.loading || action.busy}
                onClick={tasks.reload}
              >
                刷新状态
              </Button>
              {selected && (
                <RunActions
                  run={selected}
                  onAction={requestAction}
                  disabled={tasks.loading || !!tasks.error || action.busy}
                  detail
                />
              )}
            </>
          }
        />
        <ResourceStatus
          loading={tasks.loading}
          error={tasks.error}
          onRetry={tasks.reload}
        />
        {selected ? (
          <MonitorDetail
            key={selected.id}
            run={selected}
            onAction={requestAction}
            disabled={tasks.loading || !!tasks.error || action.busy}
          />
        ) : (
          !tasks.loading &&
          !tasks.error && (
            <Empty
              title="尚无可查看的监控详情"
              description="创建并启动任务后，可查看实际运行状态。"
              action={
                <Button variant="primary" onClick={create}>
                  新建监控任务
                </Button>
              }
            />
          )
        )}{" "}
        {operationDialog}
      </>
    );
  return (
    <>
      <PageHeader
        title={monitor ? "监控任务" : "线索采集"}
        description={
          monitor
            ? "持续发现新需求，按平台查看运行状态。"
            : "配置采集范围，筛选值得推进的需求。"
        }
        extra={
          <Button variant="primary" onClick={create}>
            <Plus />
            {monitor ? "新建监控任务" : "新建获客任务"}
          </Button>
        }
      />
      <Tabs
        active={tab}
        onChange={setTab}
        items={[
          { key: "all", label: "全部任务" },
          { key: "RUNNING", label: "运行中" },
          { key: "PAUSED", label: "已暂停" },
          { key: "FAILED", label: "需要处理" },
          {
            key: "draft",
            label: "本机草稿",
            count: library.filter((t) => t.mode === mode).length,
          },
        ]}
      />
      <div className="filter-bar">
        <div className="search-input">
          <MagnifyingGlass size={18} />
          <input
            aria-label="搜索任务"
            placeholder="搜索任务名称"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <Button onClick={tasks.reload}>刷新</Button>
        {!monitor && (
          <Button variant="ghost" onClick={() => navigate("/candidates")}>
            查看原始线索 <ArrowRight />
          </Button>
        )}
      </div>
      {tab !== "draft" && (
        <ResourceStatus
          loading={tasks.loading}
          error={tasks.error}
          onRetry={tasks.reload}
        />
      )}
      <div className="task-list">
        {runs.map((run) => (
          <article className="task-list-row" key={run.id}>
            <div>
              <h3>{run.name}</h3>
              <p>
                {run.platforms.map(platformName).join("、")} ·{" "}
                {formatDate(run.updatedAt || "")}
              </p>
            </div>
            <Badge tone={stateTone(run.status)}>
              {statuses[run.status] || "状态待确认"}
            </Badge>
            <div className="inline-actions">
              {monitor && (
                <Button
                  variant="ghost"
                  onClick={() =>
                    navigate(`/monitors/${encodeURIComponent(run.id)}`)
                  }
                >
                  查看详情
                </Button>
              )}
              <RunActions
                run={run}
                onAction={requestAction}
                disabled={tasks.loading || !!tasks.error || action.busy}
              />
            </div>
          </article>
        ))}
        {drafts.map((draft) => (
          <article className="task-list-row" key={draft.id}>
            <div>
              <h3>{draft.name || "未命名任务"}</h3>
              <p>
                {draft.platforms.map(platformName).join("、") || "尚未选择平台"}{" "}
                · {formatDate(draft.savedAt || "")}
              </p>
            </div>
            <Badge>本机草稿 · 未启动</Badge>
            <div className="inline-actions">
              <Button variant="ghost" onClick={() => edit(draft)}>
                继续编辑
              </Button>
              <Button variant="ghost" onClick={() => setDeleting(draft)}>
                删除
              </Button>
            </div>
          </article>
        ))}
      </div>
      {((!tasks.loading && !tasks.error) || tab === "draft") &&
        !runs.length &&
        !drafts.length && (
          <Empty
            title={
              search
                ? "没有匹配任务"
                : monitor
                  ? "还没有监控任务"
                  : "还没有采集任务"
            }
            description={
              search
                ? "试试其他关键词，或清除筛选条件。"
                : "创建任务，确认画像、范围与执行条件。"
            }
            action={
              search ? (
                <Button onClick={() => setSearch("")}>清除搜索</Button>
              ) : (
                <Button variant="primary" onClick={create}>
                  {monitor ? "创建监控任务" : "创建第一个任务"}
                </Button>
              )
            }
          />
        )}
      {monitor && (
        <section className="sample-section">
          <div className="section-heading">
            <h2>多平台监控</h2>
            <span className="muted">能力由实际连接检查</span>
          </div>
          <div className="platform-choices">
            {PLATFORMS.map((p) => (
              <span className="platform-label" key={p.id}>
                <Globe size={20} />
                {p.name}
              </span>
            ))}
          </div>
        </section>
      )}
      {operationDialog}
      {deleting && (
        <Confirm
          title="删除本机任务草稿？"
          danger
          confirmText="删除草稿"
          onCancel={() => setDeleting(null)}
          onConfirm={() => {
            setLibrary((old) => old.filter((t) => t.id !== deleting.id));
            setDeleting(null);
            notify("本机草稿已删除。");
          }}
        >
          <p>将删除“{deleting.name || "未命名任务"}”，此草稿尚未启动。</p>
        </Confirm>
      )}
    </>
  );
}
