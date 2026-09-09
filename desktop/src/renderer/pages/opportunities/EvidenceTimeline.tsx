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
          <ol className="research-version-list">
            {data.versions.map((v) => (
              <li key={v.id}>
                <h3>原文版本 v{v.ordinal}</h3>
                <p>发布于 {time(v.publishedAt)}</p>
                <p className="muted">系统观察时间　{time(v.observedAt)}</p>
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
                </details>
              </li>
            ))}
          </ol>
          {data.versions.length === 1 && (
            <p className="muted">尚无后续原文版本</p>
          )}
          {data.changes.length > 0 && (
            <section>
              <h3>有证据的变化</h3>
              {data.changes.map((change) => (
                <article className="research-change" key={change.id}>
                  <h3>{change.label}</h3>
                  <p className="muted">
                    实际变化时间　{time(change.occurredAt)}
                  </p>
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
