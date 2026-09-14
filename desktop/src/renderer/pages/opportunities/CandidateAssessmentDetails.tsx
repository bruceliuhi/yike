import React from "react";
import type { CandidateAssessmentDto } from "../../../shared/candidateReviewApi";
import { formatDate } from "../../components/ui";
import "./candidateEvidence.css";

const dimensions = [
  ["businessMatch", "业务匹配"],
  ["intent", "需求意向"],
  ["urgency", "紧迫度"],
  ["actionability", "可行动性"],
] as const;
const levels = {
  HIGH: "高",
  MEDIUM: "中",
  LOW: "低",
  UNKNOWN: "未知",
} as const;
const citationFields = {
  title: "本人标题",
  body: "本人正文",
  "parent.title": "原帖／容器标题（上下文）",
  "parent.body": "父评论正文（上下文）",
  "profile.description": "业务画像描述",
} as const;
const evidenceFields = [
  ["matchReason", "匹配依据"],
  ["actionSignal", "行动信号"],
  ["value", "潜在价值"],
  ["risk", "风险与反证"],
  ["unknowns", "待核实与未知"],
] as const;

export function CandidateAssessmentDetails({
  assessment,
  stale = false,
}: {
  assessment: CandidateAssessmentDto | undefined;
  stale?: boolean;
}) {
  if (!assessment)
    return (
      <section className="candidate-evidence" aria-label="AI 判断详情">
        <h3>AI 判断</h3>
        <p className="muted">
          暂无分析，请先查看原文，再点击“按画像重新判断”。
        </p>
      </section>
    );

  const showDrafts = !stale && assessment.effectiveDecision === "REVIEW";
  return (
    <section className="candidate-evidence" aria-label="AI 判断详情">
      <h3>AI 判断</h3>
      {stale ? (
        <p role="status" className="candidate-evidence-warning">
          此分析已过期，请重新判断。
        </p>
      ) : null}
      <div className="candidate-evidence-text">{assessment.summary}</div>
      {assessment.grade !== null ? (
        <dl className="candidate-evidence-facts">
          <div>
            <dt>商机等级</dt>
            <dd>{assessment.grade}</dd>
          </div>
        </dl>
      ) : null}
      <details className="usage-advanced">
      <summary>查看详细判断依据</summary>
      <div className="candidate-assessment-dimensions">
        {dimensions.map(([key, label]) => (
          <section
            key={key}
            aria-label={label}
            className="candidate-assessment-dimension"
          >
            <h4>{label}</h4>
            <p>
              {levels[assessment[key].level]}
            </p>
            <p className="candidate-evidence-text">{assessment[key].reason}</p>
            {assessment[key].citations.length === 0 ? (
              <p className="muted">暂无原文引用。</p>
            ) : (
              <ul className="candidate-assessment-citations">
                {assessment[key].citations.map((citation, index) => (
                  <li key={`${citation.field}:${index}`}>
                    <span className="muted">
                      {citation.field.startsWith('author_updates.')?`作者回复 ${Number(citation.field.split('.')[1])+1}`:citationFields[citation.field as keyof typeof citationFields]}
                    </span>
                    <blockquote className="candidate-evidence-text">
                      {citation.quote}
                    </blockquote>
                  </li>
                ))}
              </ul>
            )}
          </section>
        ))}
      </div>
      </details>
      <dl className="candidate-evidence-facts">
        {evidenceFields.map(([key, label]) => (
          <div key={key}>
            <dt>{label}</dt>
            <dd>{assessment.evidence[key]}</dd>
          </div>
        ))}
      </dl>
      {showDrafts ? <>
      <section
        aria-label="评论草稿（未发送）"
        className="candidate-assessment-draft"
      >
        <h4>评论草稿（未发送）</h4>
        <p className="candidate-evidence-text">{assessment.draftComment}</p>
      </section>
      <section
        aria-label="私信草稿（未发送）"
        className="candidate-assessment-draft"
      >
        <h4>私信草稿（未发送）</h4>
        <p className="candidate-evidence-text">{assessment.draftDm}</p>
      </section>
      </> : <p className="muted">
        {stale ? "此判断的联系草稿已收起，请按当前版本重新判断。" :
          assessment.effectiveDecision === "EXCLUDE" ? "当前判断为排除，不建议联系，因此不展示联系草稿。" :
          "当前仅建议观察，先等待新的采购动作，再重新判断是否联系。"}
      </p>}
      <section aria-label="判断时间">
        <dl className="candidate-evidence-facts">
          <div>
            <dt>判断时间</dt>
            <dd>
              <time dateTime={assessment.assessedAt}>
                {formatDate(assessment.assessedAt)}
              </time>
            </dd>
          </div>
        </dl>
      </section>
    </section>
  );
}
