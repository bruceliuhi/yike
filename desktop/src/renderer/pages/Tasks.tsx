import { useEffect, useState } from "react";
import {
  Plus,
  MagnifyingGlass,
  ArrowRight,
  ArrowClockwise,
  WarningCircle,
} from "@phosphor-icons/react";
import { PlatformLabel } from "../components/Platform";
import { TaskPlatforms } from "./tasks/TaskPlatforms";
import { useApp } from "../app/context";
import { useOperationLedger } from "../app/operationLedger";
import { useResource } from "../app/hooks";
import { boundedRequest } from "../app/boundedRequest";
import { routeHref } from "../domain/routes";
import { parseTaskRuns, taskActionsFor } from "../domain/taskOperations";
import { PendingTaskStarts } from "./tasks/PendingTaskStarts";
import { useTaskActions } from "./tasks/useTaskActions";
import { inDateRange, pageItems } from "./tasks/listState";
import { TaskDraftRow } from "./tasks/TaskDraftRow";
import { useTaskTemplates } from "./tasks/useTaskTemplates";
import { TaskEvents } from "./tasks/TaskEvents";
import { TaskProfileStatus } from "./tasks/TaskProfileStatus";
import { schedulePolicyDescription, scheduleWindowLabel } from "../domain/schedule";
import { TaskPagination } from "./tasks/TaskPagination";
import { SearchCoverage } from "./tasks/SearchCoverage";
import { CoveragePlanDrawer } from "./tasks/CoveragePlanDrawer";
import { CoverageAdjustmentRecovery } from "./tasks/CoverageAdjustmentRecovery";
import { defaultResearchSettings } from "../domain/researchUsage";
import type { CoveragePlanRequest } from "../domain/searchCoverage";
import "./tasks/tasks.css";
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
  PAUSING: "正在暂停",
  RESUMING: "正在恢复",
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
const taskActions = taskActionsFor;
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
  onCoveragePlan,
}: {
  run: TaskRun;
  onAction: (run: TaskRun, action: TaskAction) => void;
  disabled: boolean;
  onCoveragePlan?: (request: CoveragePlanRequest) => void | Promise<void>;
}) {
  const { navigate, route } = useApp();
  const requestedTab = route.query.get("tab");
  const routeTab =
    requestedTab && ["coverage", "platforms", "events", "config"].includes(requestedTab)
      ? requestedTab : "coverage";
  const routePlatform =
    run.platforms.find((id) => id === route.query.get("platform")) ?? null;
  const [tab, setTab] = useState(routeTab);
  const [chosen, setChosen] = useState<PlatformId | null>(routePlatform);
  useEffect(() => {
    setTab(routeTab);
    setChosen(routePlatform);
  }, [route.path, routeTab, routePlatform]);
  const platform =
    chosen && run.platforms.includes(chosen) ? chosen : run.platforms[0];
  // Keep the current local selection when leaving for connection/device setup.
  const returnQuery = new URLSearchParams(route.query);
  returnQuery.set("tab", tab);
  if (platform) returnQuery.set("platform", platform);
  else returnQuery.delete("platform");
  const returnTo = routeHref({ ...route, query: returnQuery });
  const stage = run.platformStages?.find((item) => item.platform === platform);
  const schedule = run.schedule;
  const keywords = run.keywords?.length ? run.keywords.join("、") : "待读取";
  const reconnect = () => {
    if (platform)
      navigate(
        "/connections?" +
          new URLSearchParams({
            connect: platform,
            returnTo,
          }),
      );
  };
  return (
    <section className="monitor-detail" aria-label="监控详情内容">
      <dl className="fact-strip monitor-facts">
        <div>
          <dt>监控任务</dt>
          <dd>{run.name}</dd>
        </div>
        <div>
          <dt>监控关键词</dt>
          <dd>
            {keywords.length > 36 ? (
              <details className="monitor-keywords">
                <summary
                  aria-label={`监控关键词，共 ${run.keywords?.length || 0} 个`}
                >
                  <span className="monitor-keywords-preview">{keywords}</span>
                  <span className="monitor-keywords-toggle">
                    共 {run.keywords?.length} 个 · 展开
                  </span>
                </summary>
                <p>{keywords}</p>
              </details>
            ) : (
              keywords
            )}
          </dd>
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
      {run.failureReason && (
        <div className="monitor-task-note" role="status">
          <WarningCircle size={16} aria-hidden />
          <span>{run.failureReason}</span>
        </div>
      )}
      <TaskProfileStatus run={run} />
      <Tabs
        active={tab}
        onChange={setTab}
        items={[
          { key: "coverage", label: "搜索覆盖" },
          { key: "platforms", label: "平台状态" },
          { key: "events", label: "执行记录" },
          { key: "config", label: "任务配置" },
        ]}
      />
      {tab === "coverage" && (
        <SearchCoverage
          run={run}
          onPlan={disabled ? undefined : onCoveragePlan}
        />
      )}
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
                                <PlatformLabel platform={id} size={18} />
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
                      <PlatformLabel platform={platform} size={24} />
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
                    <Button
                      onClick={() =>
                        navigate(
                          `/settings?returnTo=${encodeURIComponent(returnTo)}`,
                        )
                      }
                    >
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
      {tab === "events" && <TaskEvents run={run} />}
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
                  <TaskPlatforms platforms={run.platforms} empty="待读取" />
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
                  {schedule ? scheduleWindowLabel(schedule) : "待读取"}
                </dd>
              </div>
              <div>
                <dt>时区</dt>
                <dd>{schedule?.timezone || "待读取"}</dd>
              </div>
              {schedule && (
                <div>
                  <dt>日程规则</dt>
                  <dd>{schedulePolicyDescription(schedule).map((line) => <p key={line}>{line}</p>)}</dd>
                </div>
              )}
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
    </section>
  );
}
export function TasksPage({
  onCoveragePlan,
}: {
  onCoveragePlan?: (request: CoveragePlanRequest) => void | Promise<void>;
} = {}) {
  const { service, session, route, navigate, notify } = useApp();
  const [coverageRequest, setCoverageRequest] =
    useState<CoveragePlanRequest | null>(null);
  const openCoveragePlan = (request: CoveragePlanRequest) =>
    onCoveragePlan ? onCoveragePlan(request) : setCoverageRequest(request);
  useEffect(
    () => setCoverageRequest(null),
    [
      route.path,
      session.userId,
      session.accountScope?.id,
      session.accountScope?.version,
    ],
  );
  const monitor = route.path.startsWith("/monitors");
  const [tab, setTab] = useState("all");
  const [search, setSearch] = useState("");
  const [platformFilter, setPlatformFilter] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const invalidDates = !!from && !!to && from > to;
  useEffect(
    () => setPage(1),
    [search, platformFilter, from, to, tab, monitor, session.userId],
  );
  const [library, setLibrary] = useTaskLibrary(
    session.userId,
    session.accountScope,
  );
  const [currentDraft, setDraft] = useTaskDraft(
    session.userId,
    "once",
    session.accountScope,
  );
  const tasks = useResource(
    async () =>
      session.authenticated
        ? parseTaskRuns(
            await boundedRequest(() => service.tasks(), {
              timeoutMessage: "任务列表读取超时，请刷新重试。",
            }),
          )
        : [],
    [
      service,
      session.authenticated,
      session.userId,
      session.accountScope?.id,
      session.accountScope?.version,
    ],
  );
  const acceptRun = (run: TaskRun) =>
    tasks.setData((old) => [
      ...(old || []).filter((item) => item.id !== run.id),
      run,
    ]);
  const operations = useTaskActions(tasks.data || [], acceptRun);
  const [unknownStarts] = useOperationLedger(
    "unknown-task-starts",
    session.userId,
  );
  const templates = useTaskTemplates();
  const [deleting, setDeleting] = useState<TaskDraft | null>(null);
  const draftHasPending = (draft: TaskDraft) =>
    [draft.id, ...(draft.templateSourceDraftIds || [])].some(
      (id) => !!unknownStarts[id],
    );
  const mode = monitor ? "monitor" : "once";
  const id = route.path.startsWith("/monitors/")
    ? decodeTaskId(route.path.slice("/monitors/".length))
    : null;
  const runs = (tasks.data || []).filter(
    (t) =>
      t.mode === mode &&
      t.name.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase()) &&
      (!platformFilter || t.platforms.includes(platformFilter as PlatformId)) &&
      !invalidDates &&
      inDateRange(t.updatedAt, from, to) &&
      (tab === "all" ||
        t.status === tab ||
        (tab === "FAILED" &&
          ["BLOCKED", "PARTIAL", "OFFLINE"].includes(t.status))),
  );
  const drafts = library.filter(
    (t) =>
      t.mode === mode &&
      t.name.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase()) &&
      (!platformFilter || t.platforms.includes(platformFilter as PlatformId)) &&
      !invalidDates &&
      inDateRange(t.savedAt, from, to) &&
      (tab === "all" || tab === "draft"),
  );
  const create = () => {
    setDraft({ ...newTaskDraft(mode), research: defaultResearchSettings() });
    navigate(monitor ? "/tasks/new?mode=monitor" : "/tasks/new");
  };
  const edit = (draft: TaskDraft, confirm = false) => {
    const latest =
      currentDraft.id === draft.id && currentDraft.revision >= draft.revision
        ? currentDraft
        : draft;
    setDraft(structuredClone(latest));
    navigate(
      confirm
        ? "/tasks/new?mode=monitor&step=confirm"
        : latest.mode === "monitor"
          ? "/tasks/new?mode=monitor"
          : "/tasks/new",
    );
  };
  const requestAction = operations.open;
  const selected = tasks.data?.find((t) => t.id === id && t.mode === "monitor");
  const operationDialog = operations.dialog;
  const allItems = [
    ...runs.map((run) => ({ kind: "run" as const, run })),
    ...drafts.map((draft) => ({ kind: "draft" as const, draft })),
  ];
  const pagination = pageItems(allItems, page, pageSize);
  const shownRuns = pagination.items.flatMap((item) =>
    item.kind === "run" ? [item.run] : [],
  );
  const shownDrafts = pagination.items.flatMap((item) =>
    item.kind === "draft" ? [item.draft] : [],
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
                disabled={tasks.loading || operations.busy}
                onClick={tasks.reload}
              >
                刷新状态
              </Button>
              {selected && (
                <RunActions
                  run={selected}
                  onAction={requestAction}
                  disabled={
                    tasks.loading ||
                    !!tasks.error ||
                    operations.busy ||
                    operations.blockedTaskIds.has(selected.id)
                  }
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
            onCoveragePlan={openCoveragePlan}
            disabled={
              tasks.loading ||
              !!tasks.error ||
              operations.busy ||
              operations.blockedTaskIds.has(selected.id)
            }
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
        {operations.recovery}
        {operationDialog}
        {selected && <CoverageAdjustmentRecovery taskId={selected.id} />}
        {coverageRequest &&
          coverageRequest.userId === session.userId &&
          coverageRequest.accountScopeId === session.accountScope?.id &&
          coverageRequest.scopeVersion === session.accountScope.version && (
            <CoveragePlanDrawer
              key={JSON.stringify(coverageRequest)}
              plan={coverageRequest}
              onClose={() => setCoverageRequest(null)}
            />
          )}
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
        <label className="task-filter-field">
          平台
          <select
            aria-label="筛选任务平台"
            value={platformFilter}
            onChange={(e) => setPlatformFilter(e.target.value)}
          >
            <option value="">全部平台</option>
            {PLATFORMS.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
        <label className="task-filter-field">
          最近更新
          <input
            aria-label="任务更新开始日期"
            type="date"
            value={from}
            onChange={(e) => setFrom(e.target.value)}
          />
        </label>
        <label className="task-filter-field">
          至
          <input
            aria-label="任务更新结束日期"
            type="date"
            value={to}
            onChange={(e) => setTo(e.target.value)}
          />
        </label>
        <Button loading={tasks.loading} onClick={tasks.reload}>
          刷新
        </Button>
        {(platformFilter || from || to) && (
          <Button
            variant="ghost"
            onClick={() => {
              setPlatformFilter("");
              setFrom("");
              setTo("");
            }}
          >
            清除筛选
          </Button>
        )}
        {!monitor && (
          <Button variant="ghost" onClick={() => navigate("/candidates")}>
            查看原始线索 <ArrowRight />
          </Button>
        )}
      </div>
      {invalidDates && <Notice tone="error">开始日期不能晚于结束日期。</Notice>}
      <PendingTaskStarts
        mode={mode}
        onAccepted={acceptRun}
        onSettled={(status, original) => {
          if (status === "ACCEPTED")
            setLibrary((old) =>
              old.filter((draft) => draft.id !== original.draftId),
            );
          else {
            setLibrary((old) =>
              old.map((draft) =>
                draft.id === original.draftId
                  ? {
                      ...draft,
                      revision: Math.max(draft.revision, original.revision) + 1,
                    }
                  : draft,
              ),
            );
            setDraft((old) =>
              old.id === original.draftId
                ? {
                    ...old,
                    revision: Math.max(old.revision, original.revision) + 1,
                    savedAt: null,
                  }
                : old,
            );
          }
        }}
      />
      {operations.recovery}
      {tab !== "draft" && (
        <ResourceStatus
          loading={tasks.loading}
          error={tasks.error}
          onRetry={tasks.reload}
        />
      )}
      <div className="task-list">
        {shownRuns.map((run) => (
          <article className="task-list-row" key={run.id}>
            <div>
              <h3>{run.name}</h3>
              <p>
                <TaskPlatforms platforms={run.platforms} /> ·{" "}
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
                disabled={
                  tasks.loading ||
                  !!tasks.error ||
                  operations.busy ||
                  operations.blockedTaskIds.has(run.id)
                }
              />
            </div>
          </article>
        ))}
        {shownDrafts.map((draft) => (
          <TaskDraftRow
            key={draft.id}
            draft={draft}
            pending={[draft.id, ...(draft.templateSourceDraftIds || [])].some(
              (id) => !!unknownStarts[id],
            )}
            onEdit={() => edit(draft)}
            onDelete={() => setDeleting(draft)}
            onConfirm={() => edit(draft, true)}
            onTemplate={
              !monitor ? () => templates.saveTemplate(draft) : undefined
            }
          />
        ))}
      </div>
      <TaskPagination
        page={pagination.page}
        pages={pagination.pages}
        total={allItems.length}
        pageSize={pageSize}
        onPage={setPage}
        onPageSize={(size) => {
          setPageSize(size);
          setPage(1);
        }}
      />
      {((!tasks.loading && !tasks.error) || tab === "draft") &&
        !runs.length &&
        !drafts.length && (
          <Empty
            title={
              search || platformFilter || from || to
                ? "没有匹配任务"
                : monitor
                  ? "还没有监控任务"
                  : "还没有采集任务"
            }
            description={
              search || platformFilter || from || to
                ? "试试其他关键词，或清除筛选条件。"
                : "创建任务，确认画像、范围与执行条件。"
            }
            action={
              search ? (
                <Button onClick={() => setSearch("")}>清除搜索</Button>
              ) : platformFilter || from || to ? (
                <Button
                  onClick={() => {
                    setPlatformFilter("");
                    setFrom("");
                    setTo("");
                  }}
                >
                  重置筛选
                </Button>
              ) : (
                <Button variant="primary" onClick={create}>
                  {monitor ? "创建监控任务" : "创建第一个任务"}
                </Button>
              )
            }
          />
        )}
      {!monitor && templates.section}
      {templates.dialog}
      {monitor && (
        <section className="sample-section">
          <div className="section-heading">
            <h2>多平台监控</h2>
            <span className="muted">能力由实际连接检查</span>
          </div>
          <div className="platform-choices">
            {PLATFORMS.map((p) => (
              <span className="platform-label" key={p.id}>
                <PlatformLabel platform={p.id} size={20} />
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
          confirmDisabled={draftHasPending(deleting)}
          onCancel={() => setDeleting(null)}
          onConfirm={() => {
            if (draftHasPending(deleting)) return;
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
