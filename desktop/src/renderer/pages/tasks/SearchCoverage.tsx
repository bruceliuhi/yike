import { useEffect, useRef, useState } from "react";
import { useApp } from "../../app/context";
import { boundedRequest } from "../../app/boundedRequest";
import { useResource } from "../../app/hooks";
import { PlatformLabel } from "../../components/Platform";
import {
  Badge,
  Button,
  Empty,
  Notice,
  ResourceStatus,
} from "../../components/ui";
import type { TaskRun } from "../../domain/models";
import {
  coverageLabels,
  screeningLabels,
  coverageResultLabel,
  coveragePlan,
  parseCoverageSnapshot,
  searchCoverageQuerySchema,
  type CoveragePlanRequest,
  type CoverageSnapshot,
  type CoverageUnit,
} from "../../domain/searchCoverage";
import { ServiceError, errorMessage } from "../../services/contracts";
import { SearchCoverageDetails, coverageCount } from "./SearchCoverageDetails";
import "./SearchCoverage.css";

function zoned(value: string, timezone: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: timezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(new Date(value));
}
function useExpired(expiresAt: string) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (Date.parse(expiresAt) <= now) return;
    const timer = setTimeout(
      () => setNow(Date.now()),
      Math.max(
        0,
        Math.min(Date.parse(expiresAt) - Date.now() + 1, 2_147_483_647),
      ),
    );
    return () => clearTimeout(timer);
  }, [expiresAt, now]);
  return now >= Date.parse(expiresAt);
}
function CoverageView({
  snapshot,
  run,
  onPlan,
  onRefresh,
}: {
  snapshot: CoverageSnapshot;
  run: TaskRun;
  onRefresh: () => void;
  onPlan?: (request: CoveragePlanRequest) => void | Promise<void>;
}) {
  const { navigate } = useApp();
  const [selected, setSelected] = useState<string | null>(null);
  const [handoffError, setHandoffError] = useState("");
  const [planning, setPlanning] = useState(false);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  const expired = useExpired(snapshot.expiresAt);
  const unit =
    snapshot.units.find((row) => row.id === selected) || snapshot.units[0];
  const plan = unit && coveragePlan(snapshot, unit);
  const planLabel =
    plan?.kind === "ADJUST_LIMIT" ? "调整搜贝上限" : "基于未查范围创建草稿";
  const planningAction = async () => {
    if (
      !onPlan ||
      !plan ||
      Date.now() >= Date.parse(snapshot.expiresAt) ||
      planning
    )
      return;
    setPlanning(true);
    setHandoffError("");
    try {
      await boundedRequest(() => Promise.resolve(onPlan(plan)), {
        timeoutMessage:
          "配置预览尚未返回，请核对当前草稿；未追加搜贝或恢复运行。",
      });
    } catch (error) {
      if (mounted.current) setHandoffError(errorMessage(error));
    } finally {
      if (mounted.current) setPlanning(false);
    }
  };
  const reconnect = (current: CoverageUnit) =>
    navigate(
      "/connections?" +
        new URLSearchParams({
          connect: current.platform,
          returnTo: `/monitors/${encodeURIComponent(run.id)}`,
        }),
    );
  return (
    <>
      {expired && (
        <Notice tone="warning">
          覆盖快照已过期，以下为历史结果。刷新后再处理当前范围。
        </Notice>
      )}
      {snapshot.coverage !== "COMPLETE" && (
        <Notice tone="warning">
          部分范围尚未完成，不能判断本轮是否无合格机会。平台访问、搜贝用量与筛选结果分别记录。
        </Notice>
      )}
      <div className="coverage-meta">
        <span>
          覆盖{" "}
          <Badge tone={snapshot.coverage === "COMPLETE" ? "green" : "orange"}>
            {coverageLabels[snapshot.coverage]}
          </Badge>
        </span>
        <span>
          筛选 <Badge>{screeningLabels[snapshot.screening]}</Badge>
        </span>
        <span>本次使用画像 v{snapshot.profileVersion}</span>
        <span>
          最近更新 {zoned(snapshot.generatedAt, snapshot.window.timezone)}
        </span>
        <Button className="coverage-refresh" onClick={onRefresh}>
          刷新覆盖
        </Button>
      </div>
      <p className="coverage-window">
        检查窗口：{zoned(snapshot.window.start, snapshot.window.timezone)} –{" "}
        {zoned(snapshot.window.end, snapshot.window.timezone)}（
        {snapshot.window.timezone}）
      </p>
      <div className="coverage-layout">
        <div className="coverage-left">
          <section className="coverage-table-panel" aria-label="搜索覆盖方向">
            <h3>搜索覆盖</h3>
            {!snapshot.units.length ? (
              <Empty
                title="尚未开始检查"
                description="目前没有已完成的方向，不代表范围内无需求。"
              />
            ) : (
              <div className="table-scroll">
                <table className="coverage-table">
                  <thead>
                    <tr>
                      <th>平台</th>
                      <th>搜索方向</th>
                      <th>独立来源</th>
                      <th>检查结果</th>
                      <th>操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {snapshot.units.map((row) => (
                      <tr
                        key={row.id}
                        className={row.id === unit?.id ? "selected" : ""}
                      >
                        <td>
                          <PlatformLabel platform={row.platform} />
                        </td>
                        <td>{row.direction}</td>
                        <td>{coverageCount(row.counts.independentSources)}</td>
                        <td>
                          <Badge
                            tone={
                              ["ACCESS_FAILED", "LOGIN_EXPIRED"].includes(
                                row.stopReason,
                              )
                                ? "red"
                                : row.coverage === "COMPLETE"
                                  ? "neutral"
                                  : "orange"
                            }
                          >
                            {coverageResultLabel(row)}
                          </Badge>
                          <small>
                            {coverageLabels[row.coverage]} ·{" "}
                            {screeningLabels[row.screening]}
                          </small>
                        </td>
                        <td>
                          <Button
                            variant="ghost"
                            aria-label={`查看${row.direction}覆盖明细`}
                            aria-pressed={row.id === unit?.id}
                            onClick={() => {
                              setSelected(row.id);
                              setHandoffError("");
                            }}
                          >
                            查看明细
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
          {unit && (
            <SearchCoverageDetails
              key={snapshot.snapshotId + unit.id}
              unit={unit}
            />
          )}
        </div>
        <aside className="coverage-aside" aria-label="所选方向结果">
          {unit ? (
            <>
              <h3>
                <PlatformLabel platform={unit.platform} size={24} />
              </h3>
              <h3>{coverageResultLabel(unit)}</h3>
              <p>{unit.explanation}</p>
              <dl className="detail-list">
                <div>
                  <dt>数据覆盖</dt>
                  <dd>{coverageLabels[unit.coverage]}</dd>
                </div>
                <div>
                  <dt>筛选判断</dt>
                  <dd>{screeningLabels[unit.screening]}</dd>
                </div>
                <div>
                  <dt>来源数量</dt>
                  <dd>{coverageCount(unit.counts.independentSources)}</dd>
                </div>
                <div>
                  <dt>本次范围</dt>
                  <dd>{unit.scope}</dd>
                </div>
              </dl>
              {unit.unchecked.length > 0 && (
                <>
                  <h4>尚未检查</h4>
                  <ul>
                    {unit.unchecked.map((scope, index) => (
                      <li key={index}>{scope}</li>
                    ))}
                  </ul>
                </>
              )}
              {unit.stopReason === "LOGIN_EXPIRED" &&
                unit.platform !== "web" && (
                  <Button
                    variant="primary"
                    disabled={expired}
                    onClick={() => reconnect(unit)}
                  >
                    重新连接
                  </Button>
                )}
              {unit.stopReason === "DEVICE_OFFLINE" && (
                <Button
                  disabled={expired}
                  onClick={() => navigate("/settings")}
                >
                  检查执行设备
                </Button>
              )}
              {plan && (
                <>
                  <Button
                    variant="primary"
                    disabled={expired || !onPlan || planning}
                    onClick={planningAction}
                  >
                    {planLabel}
                  </Button>
                  <p className="muted">
                    {!onPlan
                      ? "范围与搜贝预览入口尚未接通，当前没有追加用量或新建任务。"
                      : plan.kind === "ADJUST_LIMIT"
                        ? "先预览搜贝变化，确认追加后仍须明确恢复。"
                        : "保留原运行记录，仅准备新草稿，再确认启动。"}
                  </p>
                </>
              )}
              {unit.stopReason === "LIMIT_REACHED" && !plan && (
                <Notice tone="warning">
                  当前可恢复状态或搜贝版本尚未确认，请先刷新核对；不会再次执行。
                </Notice>
              )}
              {handoffError && <Notice tone="error">{handoffError}</Notice>}
            </>
          ) : (
            <p className="muted">返回方向明细后可查看检查依据。</p>
          )}
          <section className="coverage-usage" aria-label="本次搜贝用量">
            <h4>本次搜贝用量</h4>
            <dl className="detail-list">
              <div>
                <dt>预计</dt>
                <dd>{coverageCount(snapshot.usage?.estimated ?? null)} 搜贝</dd>
              </div>
              <div>
                <dt>最多</dt>
                <dd>{coverageCount(snapshot.usage?.maximum ?? null)} 搜贝</dd>
              </div>
              <div>
                <dt>实际</dt>
                <dd>{coverageCount(snapshot.usage?.actual ?? null)} 搜贝</dd>
              </div>
            </dl>
            <p className="muted">
              {snapshot.usage
                ? {
                    NOT_STARTED: "尚未开始计量",
                    RESERVED: "额度已预留，实际用量以结算为准",
                    PENDING: "结算待确认",
                    SETTLED: "服务已返回结算用量",
                    UNKNOWN: "用量状态未知，请核对原记录",
                  }[snapshot.usage.settlement]
                : "搜贝计量尚未返回，不按零消耗处理。"}
            </p>
          </section>
        </aside>
      </div>
      <details className="coverage-binding">
        <summary>运行窗口与统计口径</summary>
        <p>
          运行 {snapshot.runId} · 窗口 {snapshot.window.id} · 配置 v
          {snapshot.configurationRevision} · 去重规则{" "}
          {snapshot.deduplicationVersion}
        </p>
        <p>
          各方向计数按各自口径展示，不跨平台直接相加。任务仍绑定画像 v
          {snapshot.profileVersion}，不会随画像编辑自动更新。
        </p>
      </details>
      <Notice>
        已检查范围无合格机会，不代表所有平台没有需求。未检查、待复核和未知结果分别保留。
      </Notice>
    </>
  );
}

export function SearchCoverage({
  run,
  onPlan,
}: {
  run: TaskRun;
  onPlan?: (request: CoveragePlanRequest) => void | Promise<void>;
}) {
  const { service, session } = useApp();
  const state = useResource(async () => {
    if (!service.searchCoverage)
      throw new ServiceError(
        "CAPABILITY_UNAVAILABLE",
        "搜索覆盖服务尚未接通；现有平台状态和执行记录仍可查看。",
        501,
      );
    if (!session.authenticated || !session.userId || !session.accountScope)
      throw new ServiceError(
        "ACCOUNT_SCOPE_UNAVAILABLE",
        "当前会话尚未提供可核验的账户范围，请重新登录或等待服务接入。",
      );
    if (!run.profileId || !run.profileVersion)
      throw new ServiceError(
        "COVERAGE_PROFILE_UNAVAILABLE",
        "任务缺少已确认画像版本，无法读取覆盖统计。",
      );
    const query = searchCoverageQuerySchema.parse({
      contractVersion: 1,
      requestId: crypto.randomUUID(),
      taskId: run.id,
      profileId: run.profileId,
      profileVersion: run.profileVersion,
      expectedScope: {
        userId: session.userId,
        accountScopeId: session.accountScope.id,
        scopeVersion: session.accountScope.version,
      },
    });
    const snapshot = parseCoverageSnapshot(
      await boundedRequest(
        (signal) => service.searchCoverage!.query(query, signal),
        { timeoutMessage: "搜索覆盖读取超时，当前结果尚未确认，请刷新重试。" },
      ),
      query,
    );
    if (snapshot.units.some((unit) => !run.platforms.includes(unit.platform)))
      throw new Error("覆盖方向超出当前任务的平台范围，请刷新任务后重新核对。");
    return snapshot;
  }, [
    service,
    session.authenticated,
    session.userId,
    session.accountScope?.id,
    session.accountScope?.version,
    run.id,
    run.profileId,
    run.profileVersion,
    run.updatedAt,
    run.platforms.join(","),
  ]);
  return (
    <section className="search-coverage" aria-label="搜索覆盖与结果解释">
      {!state.loading && !state.error && state.data ? (
        <h2 className="coverage-accessible-heading">搜索覆盖与结果解释</h2>
      ) : (
        <div className="section-heading">
          <h2>搜索覆盖与结果解释</h2>
          <Button disabled={state.loading} onClick={state.reload}>
            刷新覆盖
          </Button>
        </div>
      )}
      <ResourceStatus
        loading={state.loading}
        error={state.error}
        onRetry={state.reload}
      />
      {!state.loading && !state.error && state.data && (
        <CoverageView
          key={`${session.userId}:${session.accountScope?.id}:${session.accountScope?.version}:${state.data.snapshotId}:${state.data.generatedAt}`}
          snapshot={state.data}
          run={run}
          onPlan={onPlan}
          onRefresh={state.reload}
        />
      )}
    </section>
  );
}
