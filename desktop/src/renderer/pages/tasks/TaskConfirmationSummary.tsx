import { PlatformLabel } from "../../components/Platform";
import { Badge, Button } from "../../components/ui";
import {
  type PlatformConnection,
  type Profile,
  type TaskDraft,
} from "../../domain/models";
import "./confirmation.css";
import { DEMAND_TYPES, type UsageQuote } from "../../domain/researchUsage";
import { schedulePolicyDescription, scheduleWindowLabel } from "../../domain/schedule";
import {hasPublicSourceBinding} from '../../domain/task';
import {allowsPublicSource,DEFAULT_PUBLIC_SOURCE,publicSourceScope} from '../../../shared/publicSources';
import {DYNAMIC_RESEARCH_SOURCE,researchSelectionScope} from '../../../shared/dynamicResearch';
import {researchSourceScope} from '../../../shared/researchRuntime';
import {researchSources,researchRecordAllotments,researchIndexLabel,RESEARCH_PLAN_LABEL} from '../../../shared/researchSourcePlan';

export function TaskConfirmationSummary({
  draft,
  usage,
  profile,
  connections,
  deviceReady,
  disabled,
  onEdit,
}: {
  draft: TaskDraft;
  usage?: UsageQuote | null;
  profile?: Profile;
  connections: PlatformConnection[];
  deviceReady: boolean;
  disabled: boolean;
  onEdit: () => void;
}) {
  const source = draft.source === "search" ? "关键词搜索" : "指定内容链接";
  const hasAI = [...draft.terms, ...draft.exclusions].some(
    (term) => term.origin === "ai",
  );
  const edited = [...draft.terms, ...draft.exclusions].some(
    (term) => term.edited || term.origin !== "ai",
  );
  return (
    <>
      <section className="task-confirm-summary">
        <div className="section-heading">
          <h2>配置摘要</h2>
          <Button variant="ghost" disabled={disabled} onClick={onEdit}>
            修改配置
          </Button>
        </div>
        <div className="task-confirm-columns">
          <dl className="detail-list">
            {draft.research && (
              <>
                <div>
                  <dt>需求类型</dt>
                  <dd>
                    {draft.research.demandTypes
                      .map((type) => DEMAND_TYPES[type])
                      .join("、")}
                  </dd>
                </div>
                <div>
                  <dt>搜贝上限</dt>
                  <dd>
                    {draft.research.maxSoubei === null
                      ? "待设置"
                      : `${draft.research.maxSoubei} 搜贝`}
                  </dd>
                </div>
                <div>
                  <dt>{usage?.strategyBinding ? '资源上限估算' : '预计消耗'}</dt>
                  <dd>
                    {usage
                      ? `${usage.estimatedSoubei} 搜贝`
                      : "待重新估算"}
                  </dd>
                </div>
                {draft.research.provenance && (
                  <div>
                    <dt>相似研究来源</dt>
                    <dd>
                      {draft.research.provenance.sourceUrl}
                      <br />
                      {draft.research.provenance.additionalScope}
                    </dd>
                  </div>
                )}
                {draft.research.coverageProvenance && (
                  <div>
                    <dt>原检查范围</dt>
                    <dd>
                      {draft.research.coverageProvenance.scopeSummary}
                      <br />
                      原运行 {draft.research.coverageProvenance.runId} ·
                      去重版本{" "}
                      {draft.research.coverageProvenance.deduplicationVersion}
                    </dd>
                  </div>
                )}
              </>
            )}
            <div>
              <dt>任务名称</dt>
              <dd>{draft.name || "未填写"}</dd>
            </div>
            <div>
              <dt>业务画像</dt>
              <dd>{profile?.fields.service || "待确认真实画像"}</dd>
            </div>
            <div>
              <dt>画像版本</dt>
              <dd>
                {draft.profileVersion ? `v${draft.profileVersion}` : "未确认"}
              </dd>
            </div>
            <div>
              <dt>执行设备</dt>
              <dd>{deviceReady ? "执行服务已就绪" : "本机 · 待绑定或检查"}</dd>
            </div>
            <div>
              <dt>本次处理范围</dt>
              <dd>{draft.executionLimits
                ? `${draft.executionLimits.max_records ?? "待设置"} 条记录 / ${draft.executionLimits.max_runtime_seconds ?? "待设置"} 秒`
                : "尚未设置，请返回配置设置后再启动。"}</dd>
            </div>
            <div>
              <dt>搜索关键词</dt>
              <dd>
                {draft.terms.map((term) => term.value).join("、") || "未填写"}
                {draft.source !== "search" && "（保留但本次不执行）"}
              </dd>
            </div>
            {(draft.source === "links" || draft.links) && (
              <div>
                <dt>内容链接</dt>
                <dd>{draft.links || "未填写"}{draft.source !== "links" && "（保留但本次不执行）"}</dd>
              </div>
            )}
          </dl>
          <dl className="detail-list">
            <div>
              <dt>来源范围</dt>
              <dd>{source}</dd>
            </div>
            <div>
              <dt>运行方式</dt>
              <dd>{draft.mode === "once" ? "单次采集" : "持续监控"}</dd>
            </div>
            <div>
              <dt>排除词</dt>
              <dd>
                {draft.exclusions.map((term) => term.value).join("、") || "无"}
              </dd>
            </div>
            <div>
              <dt>条件来源</dt>
              <dd>
                {hasAI
                  ? edited
                    ? "AI 建议与人工编辑"
                    : "AI 建议"
                  : "人工配置"}{" "}
                · 可返回修改
              </dd>
            </div>
            {draft.mode === "monitor" && (
              <>
                <div>
                  <dt>执行频率</dt>
                  <dd>
                    {draft.schedule.kind === "daily"
                      ? `每日 ${draft.schedule.times.join("、")}`
                      : `每 ${draft.schedule.interval} 小时`}
                  </dd>
                </div>
                <div>
                  <dt>执行窗口</dt>
                  <dd>
                    {scheduleWindowLabel(draft.schedule)}
                  </dd>
                </div>
                <div>
                  <dt>时区</dt>
                  <dd>{draft.schedule.timezone}</dd>
                </div>
                <div>
                  <dt>日程规则</dt>
                  <dd>{schedulePolicyDescription(draft.schedule).map((line) => <p key={line}>{line}</p>)}</dd>
                </div>
              </>
            )}
          </dl>
        </div>
        {draft.research && <p className="field-hint">达到本次上限即暂停，不会自动追加用量。</p>}
        {usage && <details><summary>用量规则详情</summary><p>计量规则：{usage.ruleVersion}</p></details>}
      </section>
      <section className="task-confirm-platforms">
        <h2>平台与执行账号</h2>
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>平台</th>
                <th>执行账号</th>
                <th>连接状态</th>
                <th>范围</th>
              </tr>
            </thead>
            <tbody>
              {draft.platforms.map((id) => {
                const selected = draft.accounts[id];
                const readyConnection = connections.find(
                  (row) =>
                    row.platform === id &&
                    !row.registration &&
                    row.status === "CONNECTED" &&
                    (id === "web" || row.accountId === selected),
                );
                const connection =
                  readyConnection ||
                  connections.find(
                    (row) =>
                      row.platform === id &&
                      !row.registration &&
                      (id === "web" || row.accountId === selected),
                  );
                const matches =
                  !!selected && selected === connection?.accountId;
                const status = connection
                  ? {
                      CONNECTED: "已连接",
                      DISCONNECTED: "未连接",
                      EXPIRED: "登录已过期",
                      LIMITED: "平台限流",
                      UNAVAILABLE: "暂不可用",
                      UNVERIFIED: "待核验",
                    }[connection.status]
                  : "待核验";
                const webReady =
                  id === "web" &&
                  draft.publicSource!==DYNAMIC_RESEARCH_SOURCE&&
                  !!readyConnection && hasPublicSourceBinding(readyConnection) &&
                  researchSources(draft.publicSource ?? DEFAULT_PUBLIC_SOURCE,draft.research?.sourcePlan).every(source=>allowsPublicSource(source,
                    readyConnection.publicBinding?.sourceId,readyConnection.publicBinding?.sourceIds));
                return (
                  <tr key={id}>
                    <td>
                      <span className="task-confirm-platform">
                        <PlatformLabel platform={id} size={20} />
                      </span>
                    </td>
                    <td>
                      {id === "web"
                        ? "无需账号"
                        : matches
                          ? connection?.accountName || selected
                          : selected
                            ? `${selected}（待核对）`
                            : "—"}
                    </td>
                    <td>
                      <Badge
                        tone={
                          (
                            id === "web"
                              ? webReady
                              : matches && connection?.status === "CONNECTED"
                          )
                            ? "green"
                            : "neutral"
                        }
                      >
                        {id === "web"
                          ? draft.publicSource===DYNAMIC_RESEARCH_SOURCE?'服务端能力启动前复核':webReady
                            ? "公开读取可用"
                            : "范围待确认"
                          : connection?.status === "CONNECTED" && !matches
                            ? selected
                              ? "执行账号待核对"
                              : "待选择执行账号"
                            : status}
                      </Badge>
                    </td>
                    <td>{id === 'web' ? draft.research?.sourcePlan ? RESEARCH_PLAN_LABEL : draft.research ? researchSourceScope(draft.publicSource) : researchSelectionScope(draft.publicSource) : source}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {!draft.platforms.length && <p className="muted">尚未选择平台。</p>}
        {draft.research?.sourcePlan&&<>
          <table aria-label="已确认来源配额">
            <thead><tr><th>读取顺序与来源</th><th>记录配额</th></tr></thead>
            <tbody>{researchRecordAllotments(draft.executionLimits?.max_records??0,draft.research.sourcePlan.sources).map((row,index)=><tr key={row.sourceId}>
              <td>{index+1}. {researchIndexLabel(row.sourceId)}</td><td>{row.recordLimit} 条</td>
            </tr>)}</tbody>
          </table>
          <p className="field-hint">各来源共享总上限，空来源配额不转移；仅读取索引主题，未读评论与作者回复。不同来源可能出现同一原文，不等于更多买方。</p>
        </>}
      </section>
    </>
  );
}
