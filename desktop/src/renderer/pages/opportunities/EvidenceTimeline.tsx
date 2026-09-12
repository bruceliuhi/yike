import { useApp } from "../../app/context";
import { boundedRequest } from "../../app/boundedRequest";
import { useResource } from "../../app/hooks";
import { Badge, Button, Notice, ResourceStatus } from "../../components/ui";
import {
  hasResearchScope,
  parseResearchTimeline,
  researchBinding,
} from "../../domain/opportunityResearch";
import { deadlineText } from "../../domain/opportunityLibrary";
import type { Opportunity } from "../../domain/models";
import { isSample } from "./OpportunityEvidence";
import { useDeadlineClock } from "./LibraryFacts";
import "./research.css";

function time(value: string | null | undefined) {
  return value ? deadlineText(value).full : "待真实记录回执";
}
export function EvidenceTimeline({
  opportunity: row,
}: {
  opportunity: Opportunity;
}) {
  const { service, session } = useApp();
  const sample = isSample(row);
  const now = useDeadlineClock();
  const binding = researchBinding(
    row,
    session.authenticated ? session.userId : undefined,
    session.accountScope,
  );
  const key = JSON.stringify(binding);
  const resource = useResource(async () => {
    if (sample || !service.opportunityResearch || !binding) return null;
    return parseResearchTimeline(
      await boundedRequest(
        (signal) => service.opportunityResearch!.timeline(binding, signal),
        { timeoutMessage: "证据时间线读取超时，请重试。" },
      ),
      binding,
    );
  }, [service, key, sample, session.authenticated]);
  if (!sample && !service.opportunityResearch)
    return (
      <Notice>
        同来源版本链与关联联系事件服务尚未接通；当前原文与人工跟进仍可查看。
      </Notice>
    );
  if (!sample && !hasResearchScope(session.accountScope))
    return (
      <Notice tone="warning">
        当前账户空间尚未核验，时间线暂不可用；原文仍可查看。
      </Notice>
    );
  if (!sample && !binding)
    return (
      <Notice tone="warning">
        当前机会的画像或来源版本尚未确认，不能关联历史记录。
      </Notice>
    );
  const data = resource.data;
  const observedData = data && data.schemaVersion!==1 ? data : null;
  const entries = observedData ? observedData.observations.map(observation=>({
    key:observation.id,version:observedData.versions.find(v=>v.id===observation.versionId)!,
    observedAt:observation.observedAt,receivedAt:observation.receivedAt,anchor:observation.id===observedData.anchorObservationId,
  })) : data?.versions.map(version=>({key:version.id,version,observedAt:version.observedAt,receivedAt:null,anchor:false})) ?? [];
  const stale = Boolean(data && Date.parse(data.expiresAt) <= now);
  return (
    <section className="research-timeline">
      <h2>项目变化时间线</h2>
      {!sample && (
        <ResourceStatus
          loading={resource.loading}
          error={resource.error}
          onRetry={resource.reload}
        />
      )}
      {stale && (
        <Notice tone="warning">
          证据时间线快照已过期。
          <Button onClick={resource.reload}>刷新时间线</Button>
        </Notice>
      )}
      {sample ? (
        <>
          <ol className="research-version-list">
            <li>
              <h3>原文版本 v1</h3>
              <p>发布于 {time(row.publishedAt)}</p>
              <p className="muted">首次留存时间　待真实采集回执</p>
            </li>
            <li>
              <p className="muted">尚无后续原文版本</p>
            </li>
          </ol>
          <h2>联系与回复</h2>
          <p className="muted">暂无记录；公开样例没有客户联系或渠道回复。</p>
          <details className="research-gap" open>
            <summary>待补证</summary>
            <p>技术资料获取方式、实际采购预算</p>
          </details>
        </>
      ) : data && !resource.loading && !resource.error && !stale ? (
        <>
          {data.schemaVersion!==1&&<p className="field-hint">纳入依据保持原样；下方显示本账号同一来源的留存观察，不代表已重新核验需求。</p>}
          <ol className="research-version-list" aria-label="原文观察记录">
            {entries.map(({key,version:v,observedAt,receivedAt,anchor}) => (
              <li key={key}>
                <h3>原文版本 v{v.ordinal}</h3>
                {anchor&&<Badge>纳入商机时的依据</Badge>}
                <p>发布于 {time(v.publishedAt)}</p>
                <p className="muted">系统观察时间　{time(observedAt)}</p>
                {receivedAt&&<p className="muted">系统收到证据　{time(receivedAt)}</p>}
                {v.access !== "AVAILABLE" && (
                  <Badge tone="orange">
                    {v.access === "FAILED" ? "本次访问失败" : "访问状态待核验"}
                  </Badge>
                )}
                <details>
                  <summary>查看该版本原文</summary>
                  <blockquote className="evidence-quote">
                    {v.content}
                  </blockquote>
                  {'sourceContext' in v&&v.sourceContext&&<>
                    <h4>该次留存的作者回复</h4>
                    <p className="muted">已读取 {v.sourceContext.replies_read} 条回复；{v.sourceContext.replies_complete?'读取数量与当时标注一致':'读取范围不完整'}，附言未读取。</p>
                    {v.sourceContext.author_replies.map(reply=><div key={reply.id}>
                      <p className="muted">回复 {reply.id} · 原标注发布时间 {time(reply.published_at)}</p>
                      <blockquote className="evidence-quote">{reply.body}</blockquote>
                    </div>)}
                    {!v.sourceContext.author_replies.length&&<p className="muted">该次范围内未读到作者本人回复。</p>}
                  </>}
                </details>
              </li>
            ))}
          </ol>
          {data.schemaVersion===1 && data.versions.length === 1 && (
            <p className="muted">尚无后续原文版本</p>
          )}
          {data.schemaVersion!==1&&!data.changes.length&&<p className="muted">本次已读取范围内，尚无可确定方向的纳入后正文变化。</p>}
          {data.changes.length > 0 && (
            <section>
              <h3>有证据的变化</h3>
              {data.changes.map((change) => (
                <article className="research-change" key={change.id}>
                  <h3>{change.label}</h3>
                  {'detectedAt' in change&&data.schemaVersion!==1 ? <>
                    <p className="muted">实际编辑时间未知；不能由此判断需求已关闭或预算已确认。</p>
                    <p className="muted">后次观察时间　{time(data.observations.find(o=>o.id===change.toObservationId)?.observedAt)}</p>
                    <p className="muted">系统收到证据　{time(change.detectedAt)}</p>
                  </> : <p className="muted">
                    实际变化时间　{time(change.occurredAt)}
                  </p>}
                  <div className="research-diff">
                    <div>
                      <span>变化前 · {change.from.evidenceVersion}</span>
                      <blockquote>{change.from.quote}</blockquote>
                    </div>
                    <div>
                      <span>变化后 · {change.to.evidenceVersion}</span>
                      <blockquote>{change.to.quote}</blockquote>
                    </div>
                  </div>
                </article>
              ))}
            </section>
          )}
          {data.schemaVersion===3&&data.authorChanges.length>0&&(
            <section aria-label="作者回复变化">
              <h3>作者回复变化</h3>
              <p className="muted">仅比较已留存的作者本人回复；首次读到不等于刚发布，也不代表需求已核验。</p>
              {data.authorChanges.map(change=>(
                <article className="research-change" key={change.id}>
                  <h3>{change.label}</h3>
                  <p className="muted">回复编号 {change.replyId} · 实际编辑时间未知</p>
                  <p className="muted">后次观察时间　{time(data.observations.find(o=>o.id===change.toObservationId)?.observedAt)}</p>
                  <p className="muted">系统收到证据　{time(change.detectedAt)}</p>
                  <div className="research-diff">
                    <div>
                      {change.from?<><span>前次留存 · {change.from.evidenceVersion}</span><blockquote>{change.from.quote}</blockquote></>:
                        <p className="muted">此前留存范围内未读到该回复</p>}
                    </div>
                    <div><span>本次留存 · {change.to.evidenceVersion}</span><blockquote>{change.to.quote}</blockquote></div>
                  </div>
                </article>
              ))}
            </section>
          )}
          <h2>联系与回复</h2>
          {data.contacts.length ? (
            data.contacts.map((event) => (
              <article className="research-contact-event" key={event.id}>
                <Badge tone={event.kind === "MANUAL" ? "neutral" : "blue"}>
                  {event.kind === "MANUAL" ? "人工登记" : "渠道回执"}
                </Badge>
                <h3>{event.label}</h3>
                <p>{event.detail}</p>
                <p className="muted">
                  事件时间 {time(event.occurredAt)} · 记录时间{" "}
                  {time(event.recordedAt)}
                </p>
                <small className="muted">
                  {event.kind === "MANUAL"
                    ? `登记人 ${event.operator}`
                    : `回执 ${event.receiptId}`}
                </small>
              </article>
            ))
          ) : (
            <p className="muted">当前已读取范围内暂无联系与回复记录。</p>
          )}
          <details className="research-gap">
            <summary>待补证 · {data.gaps.length} 项</summary>
            {data.gaps.length ? (
              <ul>
                {data.gaps.map((gap) => (
                  <li key={gap}>{gap}</li>
                ))}
              </ul>
            ) : (
              <p>本快照未列出待补证项，不代表所有事实已核实。</p>
            )}
          </details>
          <Button variant="ghost" onClick={resource.reload}>
            刷新时间线
          </Button>
        </>
      ) : null}
      <Notice>访问失败不代表项目关闭。后续检查以实际任务状态为准。</Notice>
    </section>
  );
}
