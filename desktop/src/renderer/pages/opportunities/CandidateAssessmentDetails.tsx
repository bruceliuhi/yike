import React from "react";
import type { CandidateAssessmentDto } from "../../../shared/candidateReviewApi";
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
          尚无 AI
          判断，请先查看原文，再显式发起判断；不会自动生成等级或联系草稿。
        </p>
      </section>
    );

  const showDrafts = !stale && assessment.effectiveDecision === "REVIEW";
  return (
    <section className="candidate-evidence" aria-label="AI 判断详情">
      <h3>AI 判断</h3>
      {stale ? (
        <p role="status" className="candidate-evidence-warning">
          此判断已过期，仅供只读核对；请返回当前来源、画像与策略版本重新判断。
        </p>
      ) : null}
      <p className="muted">
        以下为 AI 分析，不是原文事实或发送授权，仍需人工核实。
      </p>
      <div className="candidate-evidence-text">{assessment.summary}</div>
      {assessment.grade !== null ? (
        <dl className="candidate-evidence-facts">
          <div>
            <dt>商机等级</dt>
            <dd>{assessment.grade}</dd>
          </div>
        </dl>
      ) : null}
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
              <p className="muted">暂无逐字引用；不据此补造依据。</p>
            ) : (
              <ul className="candidate-assessment-citations">
                {assessment[key].citations.map((citation, index) => (
                  <li key={`${citation.field}:${index}`}>
                    <span className="muted" title={citation.field}>
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
      <p className="muted">
        草稿仅供阅读，不会自动填入人工证据，也不会自动发送。
      </p>
      </> : <p className="muted">
        {stale ? "此判断的联系草稿已收起，请按当前版本重新判断。" :
          assessment.effectiveDecision === "EXCLUDE" ? "当前判断为排除，不建议联系，因此不展示联系草稿。" :
          "当前仅建议观察，先等待新的采购动作，再重新判断是否联系。"}
      </p>}
      <details className="candidate-evidence-details">
        <summary>判断元数据</summary>
        <dl className="candidate-evidence-facts">
          <div>
            <dt>服务提供方</dt>
            <dd>{assessment.provider}</dd>
          </div>
          <div>
            <dt>模型</dt>
            <dd>{assessment.model}</dd>
          </div>
          <div>
            <dt>规则版本</dt>
            <dd>{assessment.rule_version}</dd>
          </div>
          <div>
            <dt>规则 SHA-256</dt>
            <dd>{assessment.rule_sha256}</dd>
          </div>
          <div>
            <dt>策略版本 ID</dt>
            <dd>{assessment.strategyVersionId}</dd>
          </div>
          <div>
            <dt>判断时间</dt>
            <dd>
              <time dateTime={assessment.assessedAt}>
                {assessment.assessedAt}
              </time>
            </dd>
          </div>
          <div>
            <dt>判断 ID</dt>
            <dd>{assessment.id}</dd>
          </div>
          <div>
            <dt>候选修订</dt>
            <dd>{assessment.candidateRevision}</dd>
          </div>
          <div>
            <dt>来源版本 ID</dt>
            <dd>{assessment.sourceVersionId}</dd>
          </div>
          <div>
            <dt>画像版本 ID</dt>
            <dd>{assessment.profileId}</dd>
          </div>
          <div>
            <dt>画像版本号</dt>
            <dd>{assessment.profileVersion}</dd>
          </div>
        </dl>
      </details>
    </section>
  );
}
