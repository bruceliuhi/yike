import { useState, type ReactNode } from "react";
import { Button, formatDate } from "../../components/ui";
import type { OpportunitySourceEvidence } from "../../domain/opportunitySourceEvidence";

type CapturedEvidence = Extract<
  OpportunitySourceEvidence,
  { status: "CAPTURED" }
>;

const LONG_BODY_LENGTH = 600;

const platformLabels = {
  XIAOHONGSHU: "小红书",
  DOUYIN: "抖音",
  BILIBILI: "B站",
  ZHIHU: "知乎",
  PUBLIC_WEB: "公开网站",
} as const;

const kindLabels = {
  POST: "帖子",
  COMMENT: "评论",
  PAGE: "网页",
} as const;

const dimensionLabels = {
  businessMatch: "业务匹配",
  intent: "需求意向",
  urgency: "紧迫度",
  actionability: "可行动性",
} as const;

const openingMethodLabels = {
  DIRECT: "直接打开",
  IN_PLATFORM: "平台内打开",
} as const;

const contactMethodLabels = {
  COMMENT: "评论",
  DM: "私信",
  PUBLIC_CONTACT: "公开联系方式",
} as const;

function EvidenceTime({ value }: { value: string | null }) {
  return value === null ? (
    <>未知</>
  ) : (
    <time dateTime={value} title={value}>
      {formatDate(value)}
    </time>
  );
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

function fieldLabel(
  field: CapturedEvidence["snapshot"]["assessment"]["citations"][number]["field"],
  kind: CapturedEvidence["snapshot"]["source"]["kind"],
) {
  switch (field) {
    case "source.title":
      return "来源标题";
    case "source.body":
      return kind === "COMMENT" ? "评论原文" : "来源正文";
    case "source.container_title":
      return "原帖标题（上下文）";
    case "source.parent.body":
      return "父评论原文";
  }
}

export function FixedSourceEvidence({
  evidence,
  onOpen,
  compact = false,
}: {
  evidence: CapturedEvidence;
  onOpen: (url: string) => void;
  compact?: boolean;
}) {
  const [bodyExpanded, setBodyExpanded] = useState(false);
  const { snapshot, snapshot_sha256: snapshotSha256 } = evidence;
  const { source, observation, assessment, verification } = snapshot;
  const parent = source.kind === "COMMENT" ? source.parent : null;
  const bodyIsLong = source.body.length > LONG_BODY_LENGTH;
  const bodyHeading =
    source.kind === "COMMENT"
      ? "评论原文"
      : source.kind === "POST"
        ? "帖子原文"
        : "页面原文";

  return (
    <section
      aria-label="固定原文证据快照"
      className={`fixed-source-evidence${compact ? " fixed-source-evidence--compact" : ""}`}
    >
      <h3>{bodyHeading}</h3>
      {source.kind !== "COMMENT" && (
        <div className="fixed-evidence-context">
          <strong>来源标题</strong>
          <p>{source.title ?? "未知"}</p>
        </div>
      )}
      <div
        className={`fixed-evidence-body${bodyIsLong && !bodyExpanded ? " fixed-evidence-body--collapsed" : ""}`}
        data-testid="fixed-evidence-source-body"
      >
        {source.body}
      </div>
      {bodyIsLong && (
        <Button
          variant="ghost"
          aria-expanded={bodyExpanded}
          onClick={() => setBodyExpanded((current) => !current)}
        >
          {bodyExpanded ? "收起原文" : "展开完整原文"}
        </Button>
      )}

      <dl className="detail-list fixed-evidence-source-facts">
        <Fact label="来源平台">{platformLabels[source.platform]}</Fact>
        <Fact label="来源类型">{kindLabels[source.kind]}</Fact>
        <Fact label={source.kind === "COMMENT" ? "评论公开作者" : "公开作者"}>
          {source.author_public_id ?? "未知"}
        </Fact>
        <Fact label="来源发布">
          <EvidenceTime value={source.published_at} />
        </Fact>
        <Fact label="采集端观察">
          <EvidenceTime value={observation.observed_at} />
        </Fact>
        <Fact label="服务器收到">
          <EvidenceTime value={observation.received_at} />
        </Fact>
        <Fact label="纳入留存">
          <EvidenceTime value={snapshot.captured_at} />
        </Fact>
      </dl>

      {source.kind === "COMMENT" && (
        <section className="fixed-evidence-context" data-testid="comment-context">
          <h3>评论所在上下文</h3>
          <dl className="detail-list">
            <Fact label="原帖标题（上下文）">
              {source.container_title ?? "未知"}
            </Fact>
          </dl>
          <p className="muted">
            原帖和父评论仅作上下文，不代表该评论者本人有采购需求。
          </p>
          {parent !== null && (
            <div>
              <h4>父评论</h4>
              <div className="fixed-evidence-body">
                {parent.body ?? "未知"}
              </div>
              <dl className="detail-list">
                <Fact label="父评论公开作者">
                  {parent.author_public_id ?? "未知"}
                </Fact>
                <Fact label="父评论发布时间">
                  <EvidenceTime value={parent.published_at} />
                </Fact>
              </dl>
              {parent.public_url !== null && (
                <Button
                  variant="ghost"
                  onClick={() => onOpen(parent.public_url!)}
                >
                  查看父评论所在来源
                </Button>
              )}
            </div>
          )}
        </section>
      )}

      <section className="fixed-evidence-citations">
        <h3>AI 公开原文逐字引用</h3>
        {assessment.citations.length === 0 ? (
          <p className="muted">无可展示的公开引用</p>
        ) : (
          <ul aria-label="AI 公开原文逐字引用">
            {assessment.citations.map((citation, index) => (
              <li key={`${citation.dimension}-${citation.field}-${index}`}>
                <p>
                  <strong>{dimensionLabels[citation.dimension]}</strong>
                  {" · "}
                  <span>{fieldLabel(citation.field, source.kind)}</span>
                </p>
                <blockquote
                  className="fixed-evidence-body"
                  data-testid="citation-quote"
                >
                  {citation.quote}
                </blockquote>
              </li>
            ))}
          </ul>
        )}
        {assessment.omitted_profile_citations > 0 && (
          <p className="muted">
            另有 {assessment.omitted_profile_citations} 条画像依据未在此共享，仅显示数量。
          </p>
        )}
      </section>

      <details className="fixed-evidence-versions">
        <summary>版本与当时判断明细</summary>
        <dl className="detail-list">
          <Fact label="快照格式">{snapshot.schema_version}</Fact>
          <Fact label="来源版本">{source.version_id}</Fact>
          <Fact label="来源内容摘要">{source.content_sha256}</Fact>
          <Fact label="固定快照摘要">{snapshotSha256}</Fact>
          <Fact label="观察记录">{observation.id}</Fact>
          <Fact label="判断记录">{assessment.id}</Fact>
          <Fact label="当时画像版本">
            {assessment.profile_version_id} · 第 {assessment.profile_version} 版
          </Fact>
          <Fact label="当时策略版本">{assessment.strategy_version_id}</Fact>
          <Fact label="模型提供方">{assessment.provider}</Fact>
          <Fact label="当时模型">{assessment.model}</Fact>
          <Fact label="规则版本">{assessment.rule_version}</Fact>
          <Fact label="规则摘要">{assessment.rule_sha256}</Fact>
          <Fact label="当时模型判断时间">
            <EvidenceTime value={assessment.assessed_at} />
          </Fact>
          <Fact label="人工回看时间（历史）">
            <EvidenceTime value={verification.checked_at} />
          </Fact>
          <Fact label="纳入时来源状态">有效（纳入时）</Fact>
          <Fact label="纳入时回看方式">
            {openingMethodLabels[verification.opening_method]}
          </Fact>
          <Fact label="纳入时联系方式">
            {contactMethodLabels[verification.contact_method]}
          </Fact>
        </dl>
      </details>

      <p className="muted fixed-evidence-history-note">
        这是纳入时的历史留存，不证明对方当前仍在采购，也不表示已允许联系。来源当前失效时，有权查看的历史快照仍保留。
      </p>
    </section>
  );
}
