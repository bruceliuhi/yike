import React, { type ReactNode } from "react";
import type { RawCandidateEvidenceDto } from "../../../shared/rawCandidateEvidence";
import "./candidateEvidence.css";

type Candidate = RawCandidateEvidenceDto["candidate"];
type Content = Candidate["current_version"];

const platformLabels = {
  XIAOHONGSHU: "小红书",
  DOUYIN: "抖音",
  BILIBILI: "B站",
  ZHIHU: "知乎",
  PUBLIC_WEB: "公开网站",
} as const;
const kindLabels = { POST: "帖子", COMMENT: "评论", PAGE: "网页" } as const;

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

function EvidenceTime({ value }: { value: string | null }) {
  return value === null ? <>未知</> : <time dateTime={value}>{value}</time>;
}

function OriginalContent({
  content,
  kind,
}: {
  content: Pick<
    Content,
    | "body"
    | "title"
    | "author_public_id"
    | "published_at"
    | "parent"
    | "public_url"
  >;
  kind: Candidate["kind"];
}) {
  const bodyLabel =
    kind === "COMMENT" ? "评论原文" : kind === "POST" ? "帖子原文" : "页面原文";
  return (
    <>
      <h4>{bodyLabel}</h4>
      <div className="candidate-evidence-text" aria-label={bodyLabel}>
        {content.body}
      </div>
      <dl className="candidate-evidence-facts">
        <Fact label={kind === "COMMENT" ? "评论公开作者" : "公开作者"}>
          {content.author_public_id ?? "未知"}
        </Fact>
        <Fact label="来源发布时间">
          <EvidenceTime value={content.published_at} />
        </Fact>
        <Fact label="来源链接">{content.public_url}</Fact>
        <Fact
          label={kind === "COMMENT" ? "原帖／容器标题（上下文）" : "来源标题"}
        >
          {content.title ?? "未知"}
        </Fact>
      </dl>
      {kind === "COMMENT" ? (
        <>
          <p className="muted">
            原帖标题和父评论仅作上下文，不代表当前评论者本人的采购需求；不同作者不视为同一人。
          </p>
          {content.parent === null ? (
            <p className="muted">未取得父评论上下文。</p>
          ) : (
            <section
              aria-label="父评论上下文"
              className="candidate-evidence-context"
            >
              <h4>父评论上下文</h4>
              <div className="candidate-evidence-text" aria-label="父评论原文">
                {content.parent.body ?? "未知"}
              </div>
              <dl className="candidate-evidence-facts">
                <Fact label="父评论公开作者">
                  {content.parent.author_public_id ?? "未知"}
                </Fact>
                <Fact label="父评论发布时间">
                  <EvidenceTime value={content.parent.published_at} />
                </Fact>
                <Fact label="父评论 ID">
                  {content.parent.external_comment_id}
                </Fact>
                <Fact label="父评论链接">
                  {content.parent.public_url ?? "未知"}
                </Fact>
              </dl>
            </section>
          )}
        </>
      ) : null}
    </>
  );
}

export function CandidateOriginalEvidence({
  evidence,
}: {
  evidence: RawCandidateEvidenceDto;
}) {
  const { candidate, observations } = evidence;
  // Match the exact observation, not another receipt for the same source version.
  const currentObservation = observations.items.find(
    (item) => item.observation_id === candidate.current_observation_id,
  );
  return (
    <section className="candidate-evidence" aria-label="候选原文证据">
      <h3>原文证据</h3>
      <p className="muted">
        采集留存原文，尚未完成人工来源核验；不代表来源当前可访问或已授权联系。
      </p>
      <section aria-label="当前原文">
        <OriginalContent
          content={candidate.current_version}
          kind={candidate.kind}
        />
        <dl className="candidate-evidence-facts">
          <Fact label="来源平台">
            {platformLabels[candidate.platform]}（{candidate.platform}）
          </Fact>
          <Fact label="来源类型">
            {kindLabels[candidate.kind]}（{candidate.kind}）
          </Fact>
          <Fact label="采集端观察时间">
            <EvidenceTime value={candidate.latest_observed_at} />
          </Fact>
          <Fact label="服务器接收时间">
            {currentObservation ? (
              <EvidenceTime value={currentObservation.received_at} />
            ) : (
              "当前观察记录不在已返回历史中，未知"
            )}
          </Fact>
          <Fact label="候选修订">{candidate.revision}</Fact>
          <Fact label="来源版本 ID">
            {candidate.current_version.version_id}
          </Fact>
          <Fact label="内容版本摘要">
            {candidate.current_version.content_version}
          </Fact>
        </dl>
      </section>
      {observations.truncated ? (
        <p className="candidate-evidence-warning">
          观察历史已截断，仅显示 {observations.items.length} 条，共{" "}
          {observations.total} 条；未显示的记录不代表不存在。
        </p>
      ) : null}
      <details className="candidate-evidence-details">
        <summary>
          观察历史（{observations.items.length} / {observations.total}）
        </summary>
        <p className="muted">
          每条记录保留其自己的原文、版本与时间；历史留存不能替代当前核验。
        </p>
        {observations.items.map((item, index) => (
          <article
            key={item.observation_id}
            aria-label={`观察记录 ${index + 1}`}
            className="candidate-evidence-history"
          >
            <h4>
              观察记录 {index + 1}
              {item.observation_id === candidate.current_observation_id
                ? "（当前观察）"
                : ""}
            </h4>
            <dl className="candidate-evidence-facts">
              <Fact label="观察 ID">{item.observation_id}</Fact>
              <Fact label="来源版本 ID">{item.version_id}</Fact>
              <Fact label="内容版本摘要">{item.content_version}</Fact>
              <Fact label="采集端观察时间">
                <EvidenceTime value={item.observed_at} />
              </Fact>
              <Fact label="服务器接收时间">
                <EvidenceTime value={item.received_at} />
              </Fact>
              <Fact label="采集查询">{item.query ?? "未知"}</Fact>
              <Fact label="采集器版本">{item.collector_version}</Fact>
              <Fact label="规范化器版本">{item.normalizer_version}</Fact>
            </dl>
            <OriginalContent content={item.content} kind={candidate.kind} />
          </article>
        ))}
      </details>
    </section>
  );
}
