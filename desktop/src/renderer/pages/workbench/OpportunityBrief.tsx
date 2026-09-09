import { useEffect, useState } from "react";
import { ArrowRight } from "@phosphor-icons/react";
import { useApp } from "../../app/context";
import { boundedRequest } from "../../app/boundedRequest";
import { useResource } from "../../app/hooks";
import {
  Badge,
  Button,
  Empty,
  Notice,
  ResourceStatus,
  Tabs,
} from "../../components/ui";
import { PlatformLabel } from "../../components/Platform";
import {
  PLATFORMS,
  type Profile,
  type PlatformConnection,
} from "../../domain/models";
import {
  briefBusinessDay,
  nextBriefDay,
  briefGroupLabels,
  briefQuerySchema,
  briefTarget,
  parseOpportunityBrief,
  type BriefGroup,
  type OpportunityBriefSnapshot,
} from "../../domain/opportunityBrief";
import { ServiceError } from "../../services/contracts";
import "./OpportunityBrief.css";

const time = (value: string | null, timezone: string) =>
  value === null
    ? "暂无"
    : new Intl.DateTimeFormat("zh-CN", {
        timeZone: timezone,
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      }).format(new Date(value));
const connectionLabels = {
  CONNECTED: "已连接",
  DISCONNECTED: "待连接",
  EXPIRED: "登录失效",
  LIMITED: "访问受限",
  UNAVAILABLE: "尚未接通",
};

function BriefRows({
  snapshot,
  now,
}: {
  snapshot: OpportunityBriefSnapshot;
  now: number;
}) {
  const { navigate } = useApp();
  const [group, setGroup] = useState<BriefGroup>("contact");
  const [page, setPage] = useState(1);
  const [rowError, setRowError] = useState("");
  const data = snapshot.groups[group];
  const expired = now >= Date.parse(snapshot.expiresAt);
  const complete = snapshot.coverage === "COMPLETE";
  return (
    <>
      <Tabs
        active={group}
        items={(Object.keys(briefGroupLabels) as BriefGroup[]).map((key) => ({
          key,
          label: briefGroupLabels[key],
          count: snapshot.groups[key].total,
        }))}
        onChange={(value) => {
          setGroup(value as BriefGroup);
          setPage(1);
          setRowError("");
        }}
      />
      {rowError && <Notice tone="error">{rowError}</Notice>}
      {!data.items.length ? (
        <Empty
          title={
            expired
              ? "简报已过期，请更新后再判断"
              : snapshot.coverage === "NOT_CHECKED"
                ? "尚未完成检查"
                : complete
                  ? `本次已查范围暂无${group === "contact" ? "已复核的客户机会" : group === "changes" ? "已核验的重要变化" : "待跟进事项"}`
                  : "已完成部分暂未列出事项"
          }
          description={
            complete && !expired
              ? "仅表示当前画像和检查窗口内的结果。"
              : "检查未完成或简报尚未更新，不代表今天没有需求。"
          }
          action={
            <Button onClick={() => navigate("/monitors")}>查看获客任务</Button>
          }
        />
      ) : (
        <div className="brief-rows">
          {data.items.slice((page - 1) * 6, page * 6).map((item) => (
            <article className="brief-row" key={item.id}>
              <div className="brief-row-heading">
                <strong>{item.title}</strong>
                {item.validity !== "VALID" && (
                  <Badge tone="orange">
                    {item.validity === "TARGET_MISSING"
                      ? "目标已不可用"
                      : "依据已过期"}
                  </Badge>
                )}
              </div>
              <p>{item.reason}</p>
              <details>
                <summary>查看判断依据</summary>
                <blockquote>{item.basis.excerpt}</blockquote>
                <p className="muted">
                  {item.basis.kind === "MANUAL_FOLLOWUP"
                    ? "人工跟进记录"
                    : item.basis.kind === "CHANNEL_FOLLOWUP"
                      ? "真实通道记录"
                      : item.basis.kind === "VERIFIED_CHANGE"
                        ? "已核验变化"
                        : "已人工复核需求"}{" "}
                  · {time(item.basis.verifiedAt, snapshot.timezone)}（
                  {snapshot.timezone}）
                </p>
                <p className="muted">
                  记录 {item.basis.recordId} · 版本 {item.basis.version}
                </p>
              </details>
              <Button
                variant="ghost"
                disabled={expired || item.validity !== "VALID"}
                onClick={() => {
                  if (Date.now() >= Date.parse(snapshot.expiresAt)) {
                    setRowError("简报已过期，请刷新后再打开当前对象。");
                    return;
                  }
                  const target = briefTarget(group, item);
                  if (target) navigate(target);
                  else setRowError("当前目标未找到，请更新简报。");
                }}
              >
                {group === "followup" ? "查看该商机跟进" : "查看机会证据"}
                <ArrowRight aria-hidden />
              </Button>
            </article>
          ))}
          {data.total > 6 && (
            <div className="brief-pagination">
              <Button
                disabled={page === 1}
                onClick={() => setPage((value) => value - 1)}
              >
                上一页
              </Button>
              <span>
                {page} / {Math.ceil(data.total / 6)}
              </span>
              <Button
                disabled={page * 6 >= data.total}
                onClick={() => setPage((value) => value + 1)}
              >
                下一页
              </Button>
            </div>
          )}
        </div>
      )}
      <details className="brief-scope">
        <summary>查看检查范围与口径</summary>
        <p>
          业务日期 {snapshot.businessDate}（{snapshot.timezone}） · 画像 v
          {snapshot.profileVersion}
        </p>
        <h4>已检查</h4>
        {snapshot.checkedScope.length ? (
          <ul>
            {snapshot.checkedScope.map((scope, index) => (
              <li key={index}>{scope}</li>
            ))}
          </ul>
        ) : (
          <p>暂无已完成范围。</p>
        )}
        <h4>尚未检查</h4>
        {snapshot.uncheckedScope.length ? (
          <ul>
            {snapshot.uncheckedScope.map((scope, index) => (
              <li key={index}>{scope}</li>
            ))}
          </ul>
        ) : (
          <p>{complete ? "本次声明的范围已完成。" : "范围尚待核实。"}</p>
        )}
        <p>同一机会可出现在不同组，不合计为新增客户；数量仅属于本份快照。</p>
      </details>
    </>
  );
}

export function OpportunityBrief({
  profiles,
  profilesLoading,
  profilesError,
  onProfilesRetry,
  connections,
  connectionsLoading,
  connectionsError,
  onConnectionsRetry,
}: {
  profiles: Profile[];
  profilesLoading: boolean;
  profilesError: string;
  onProfilesRetry: () => void;
  connections: PlatformConnection[];
  connectionsLoading: boolean;
  connectionsError: string;
  onConnectionsRetry: () => void;
}) {
  const { service, session, navigate } = useApp();
  const [selectedProfile, setSelectedProfile] = useState("");
  const [emptyGroup, setEmptyGroup] = useState<BriefGroup>("contact");
  const confirmed = profiles
    .filter((profile) => profile.status === "CONFIRMED")
    .sort((a, b) => b.version - a.version);
  const profile =
    confirmed.find((value) => value.id === selectedProfile) || confirmed[0];
  const [now, setNow] = useState(Date.now());
  const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  const businessDate = briefBusinessDay(now, timezone);
  const state = useResource(async () => {
    if (!session.authenticated || !session.userId)
      throw new ServiceError("UNAUTHENTICATED", "登录后查看客户空间简报。");
    if (profilesLoading) return null;
    if (profilesError)
      throw new Error("画像读取未完成，请重试业务画像后查看简报。");
    if (!profile) return null;
    if (!service.opportunityBrief)
      throw new ServiceError(
        "CAPABILITY_UNAVAILABLE",
        "机会简报服务尚未接通；原有待办与公开研究样例仍可查看。",
        501,
      );
    if (!session.accountScope)
      throw new ServiceError(
        "ACCOUNT_SCOPE_UNAVAILABLE",
        "当前会话尚未提供可核验的账户范围，不能读取简报。",
      );
    const query = briefQuerySchema.parse({
      contractVersion: 1,
      requestId: crypto.randomUUID(),
      userId: session.userId,
      accountScopeId: session.accountScope.id,
      scopeVersion: session.accountScope.version,
      profileId: profile.id,
      profileVersion: profile.version,
      businessDate,
      timezone,
    });
    return parseOpportunityBrief(
      await boundedRequest(
        (signal) => service.opportunityBrief!.query(query, signal),
        { timeoutMessage: "机会简报读取超时，请重试；尚不能判断今日结果。" },
      ),
      query,
    );
  }, [
    service,
    service.opportunityBrief,
    session.authenticated,
    session.userId,
    session.accountScope?.id,
    session.accountScope?.version,
    profile?.id,
    profile?.version,
    profilesLoading,
    profilesError,
    businessDate,
    timezone,
  ]);
  const expiry = state.data ? Date.parse(state.data.expiresAt) : null;
  useEffect(() => {
    const delay = Math.min(
      60_000,
      nextBriefDay(now, timezone) - now + 1,
      expiry !== null && expiry > now ? expiry - now + 1 : 60_000,
    );
    const timer = setTimeout(() => setNow(Date.now()), delay);
    return () => clearTimeout(timer);
  }, [now, expiry, timezone]);
  const expired = expiry !== null && now >= expiry;
  const snapshot = !state.loading && !state.error ? state.data : null;
  return (
    <section className="opportunity-brief" aria-label="机会简报">
      <Notice
        tone={snapshot?.coverage === "PARTIAL" || expired ? "warning" : "info"}
        action={
          <Button variant="ghost" onClick={() => navigate("/monitors")}>
            查看运行情况
            <ArrowRight aria-hidden />
          </Button>
        }
      >
        <strong>
          {expired
            ? "简报已过期"
            : snapshot?.coverage === "COMPLETE"
              ? "本次检查已完成"
              : snapshot?.coverage === "PARTIAL"
                ? "部分范围尚未完成检查"
                : "简报尚未更新"}{" "}
          · 最近完成检查：
          {snapshot
            ? time(snapshot.lastCompletedCheckAt, timezone)
            : "暂无可核验时间"}
        </strong>
        <p>
          {snapshot
            ? `当前简报按 ${snapshot.businessDate}（${snapshot.timezone}）展示，未覆盖范围不作无机会结论。`
            : "首次检查完成后，按证据与跟进安排生成简报。"}
        </p>
      </Notice>
      <div className="brief-layout">
        <div className="brief-main">
          <div className="section-heading">
            <h2>机会简报</h2>
            <Button
              disabled={state.loading || profilesLoading}
              onClick={state.reload}
            >
              刷新简报
            </Button>
          </div>
          {confirmed.length > 1 && (
            <label className="brief-profile">
              业务画像
              <select
                aria-label="简报业务画像"
                value={profile?.id || ""}
                onChange={(event) => setSelectedProfile(event.target.value)}
              >
                {confirmed.map((value) => (
                  <option value={value.id} key={value.id}>
                    {value.fields.service || "业务画像"} · v{value.version}
                  </option>
                ))}
              </select>
            </label>
          )}
          <ResourceStatus
            loading={profilesLoading || state.loading}
            error={profilesError || state.error}
            onRetry={profilesError ? onProfilesRetry : state.reload}
          />
          {snapshot ? (
            <BriefRows
              key={`${session.userId}:${session.accountScope?.id}:${session.accountScope?.version}:${profile?.id}:${snapshot.snapshotId}:${snapshot.generatedAt}`}
              snapshot={snapshot}
              now={now}
            />
          ) : (
            <>
              <Tabs
                items={(Object.keys(briefGroupLabels) as BriefGroup[]).map(
                  (key) => ({ key, label: briefGroupLabels[key] }),
                )}
                active={emptyGroup}
                onChange={(value) => setEmptyGroup(value as BriefGroup)}
              />
              {!profilesLoading &&
                !state.loading &&
                !profilesError &&
                !state.error && (
                  <Empty
                    title="先确认业务画像"
                    description="按已确认的画像寻找和复核需求。"
                    action={
                      <Button onClick={() => navigate("/profile")}>
                        完善业务画像
                      </Button>
                    }
                  />
                )}
            </>
          )}
          {!profilesLoading && !profilesError && !profile && (
            <div className="brief-next">
              <h3>待完善</h3>
              <Button onClick={() => navigate("/profile")}>
                确认业务画像
                <ArrowRight aria-hidden />
              </Button>
              <Button onClick={() => navigate("/connections")}>
                连接目标平台
                <ArrowRight aria-hidden />
              </Button>
            </div>
          )}
        </div>
        <aside className="brief-platforms" aria-label="平台准备">
          <div className="section-heading">
            <h2>平台准备</h2>
            <Button variant="ghost" onClick={() => navigate("/connections")}>
              管理平台连接
            </Button>
          </div>
          <ResourceStatus
            loading={connectionsLoading}
            error={connectionsError}
            onRetry={onConnectionsRetry}
          />
          <ul>
            {PLATFORMS.map((platform) => {
              const connection = connections.find(
                (row) => row.platform === platform.id,
              );
              return (
                <li key={platform.id}>
                  <PlatformLabel platform={platform.id} size={28} />
                  <span className="muted">
                    {connectionsLoading || connectionsError
                      ? "待检查"
                      : connection
                        ? connectionLabels[connection.status] || "待核验"
                        : platform.id === "web"
                          ? "范围由任务确认"
                          : "待连接"}
                  </span>
                </li>
              );
            })}
          </ul>
          <p className="brief-hint">
            平台连接状态不代表已完成搜索；覆盖结果以运行详情为准。
          </p>
        </aside>
      </div>
    </section>
  );
}
