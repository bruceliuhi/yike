import { ArrowSquareOut } from "@phosphor-icons/react";
import { useApp } from "../../app/context";
import { Button, Notice, formatDate } from "../../components/ui";
import { PlatformIcon, PlatformLabel } from "../../components/Platform";
import type { Opportunity } from "../../domain/models";
import { libraryExportFields } from "../../domain/opportunityLibrary";
import { errorMessage } from "../../services/contracts";
import { FixedSourceEvidence } from "./FixedSourceEvidence";

// Source verified on 2026-09-09. This public inquiry is never a customer record.
export const PUBLIC_SAMPLE: Opportunity = {
  id: "sample",
  sample: true,
  title: "180㎡高交会展区设计搭建预算询价",
  buyer: "湖南省商务厅对外贸易发展处",
  summary: "180㎡展区，涵盖设计、搭建、维护、撤展和组展服务。",
  excerpt: "本次报价仅用于预算测算。",
  matchReason: "买方公开征询服务方案与成本；适配需结合地域、施工及组展能力。",
  actionSignal: "9月15日18:00前递交资料，可评估是否参与预算询价。",
  value: "适合提前了解需求；预算、合同和收入尚未确定。",
  risk: "预算金额未公开，需进一步核实。本次不确定供应商、不签合同，参与不带来后续招标优先资格。",
  contactPath: "以官方公告的采购咨询、资料递交要求为准。",
  url: "https://swt.hunan.gov.cn/swt/hnswt/85753/fdzdgknr/caizhengxinxi/zfcgh/202609/t20260908_44997689265690696.html",
  platform: "公开网站",
  sourceStatus: "UNVERIFIED",
  profileStatus: "UNBOUND",
  profileVersionId: "",
  reviewer: "",
  reviewedAt: "",
  publishedAt: "2026-09-08T16:54:00+08:00",
  updatedAt: "",
  sourceObservedAt: "2026-09-09T11:20:40Z",
  sourceEvidenceVersion: "public-sample-20260909-v1",
  libraryFacts: {
    schema_version: 1,
    opportunity_id: "sample",
    source_url:
      "https://swt.hunan.gov.cn/swt/hnswt/85753/fdzdgknr/caizhengxinxi/zfcgh/202609/t20260908_44997689265690696.html",
    observed_at: "2026-09-09T11:20:40Z",
    evidence_version: "public-sample-20260909-v1",
    stage: {
      status: "KNOWN",
      label: "预算询价",
      evidence_excerpt: "本次为预算编制阶段市场调研询价。",
    },
    materials_deadline: {
      status: "KNOWN",
      at: "2026-09-15T18:00:00+08:00",
      evidence_excerpt: "递交截止时间：2026年9月15日18:00（北京时间）",
    },
  },
  intentStatus: "PENDING_REVIEW",
  comment:
    "请问本次展区设计搭建的技术资料与服务范围说明，可以从哪里获取？",
  dm: "您好，看到本次高交会展区预算询价，想先了解资料要求。请问技术资料与服务范围说明可以从哪里获取？",
};
export function isSample(row: Opportunity) {
  return row.sample === true || row.id === "sample";
}
export function SourcePlatform({
  platform,
  sourceLabel,
}: {
  platform: string;
  sourceLabel?: string;
}) {
  return sourceLabel ? (
    <span className="brand-platform-label" style={{ whiteSpace: "normal" }}>
      <PlatformIcon platform={platform} size={16} />
      <span>{sourceLabel}</span>
    </span>
  ) : (
    <PlatformLabel platform={platform || "来源待核验"} size={16} />
  );
}
export function opportunityStatus(row: Opportunity) {
  if (isSample(row)) return "待复核";
  return (
    (
      {
        NEW: "新商机",
        REVIEW: "待复核",
        READY: "可联系",
        CONTACTED: "已联系",
        CLOSED: "已关闭",
        REPLIED: "已回复",
        MEETING: "已约谈",
        QUOTED: "已报价",
        WON: "已成交",
        LOST: "已关闭",
        PENDING_REVIEW: "待复核",
      } as Record<string, string>
    )[row.intentStatus] ||
    row.intentStatus ||
    "状态待核验"
  );
}
export function customerCsv(rows: Opportunity[]) {
  const cell = (value: string) =>
    '"' +
    (/^[\s]*[=+\-@\t\r]/.test(value) ? "'" + value : value).replaceAll(
      '"',
      '""',
    ) +
    '"';
  const fields = [
    [
      "商机标题",
      "需求方",
      "来源平台",
      "阶段",
      "状态",
      "资料截止",
      "来源链接",
      "原文摘录",
    ],
    ...rows
      .filter((r) => !isSample(r))
      .map((r) => [
        r.title,
        r.buyer,
        r.platform,
        libraryExportFields(r)[0],
        opportunityStatus(r),
        libraryExportFields(r)[1],
        r.url,
        r.excerpt,
      ]),
  ];
  return "\uFEFF" + fields.map((row) => row.map(cell).join(",")).join("\r\n");
}
export function EvidencePanel({
  opportunity: row,
  compact = false,
}: {
  opportunity: Opportunity;
  compact?: boolean;
}) {
  const { service, notify } = useApp();
  const fixed = row.sourceEvidence?.status === "CAPTURED" ? row.sourceEvidence : undefined;
  const sourceUrl = fixed?.snapshot.source.public_url ?? row.url;
  const open = async (url: string) => {
    try {
      await service.openExternal(url);
    } catch (error) {
      notify(errorMessage(error), "error");
    }
  };
  return (
    <section className="evidence-panel">
      <div className="section-heading">
        <h2>原文证据</h2>
        <Button variant="ghost" disabled={!sourceUrl} onClick={() => void open(sourceUrl)}>
          查看来源原文 <ArrowSquareOut />
        </Button>
      </div>
      {fixed ? (
        <FixedSourceEvidence key={fixed.snapshot_sha256} evidence={fixed}
          compact={compact} onOpen={(url) => void open(url)} />
      ) : (
        <>
          {!isSample(row) && <p className="muted">
            {row.sourceEvidence?.status === "UNAVAILABLE"
              ? "未留存固定原文证据" : "固定原文证据尚未加载"}
          </p>}
          <h3>{isSample(row) ? "公开样例摘录" : "旧版摘录（非固定原文）"}</h3>
          <blockquote className="evidence-quote">
            {row.excerpt || "尚未提供原始摘录"}
          </blockquote>
          <p className="muted source-meta">
            <SourcePlatform platform={row.platform}
              sourceLabel={isSample(row) ? "湖南省商务厅官网" : undefined} />{" "}
            · 发布于 {formatDate(row.publishedAt)}
          </p>
        </>
      )}
      {!compact && (
        <>
          <h3>当前复核与判断</h3>
          <p className="muted source-meta">
            复核人：{row.reviewer || "未知"} · 复核时间：{row.reviewedAt ? formatDate(row.reviewedAt) : "未知"}
          </p>
          <h3>需求概述</h3>
          <p>{row.summary || "尚未提供需求概述"}</p>
          <h3>证据评估</h3>
          <dl className="detail-list">
            <div>
              <dt>匹配依据</dt>
              <dd>{row.matchReason || "尚未复核"}</dd>
            </div>
            <div>
              <dt>行动信号</dt>
              <dd>{row.actionSignal || "尚未核实"}</dd>
            </div>
            <div>
              <dt>机会价值</dt>
              <dd>{row.value || "尚未判断"}</dd>
            </div>
          </dl>
          <Notice tone="warning">{row.risk || "风险与未知项尚未核实"}</Notice>
          <h3>联系渠道</h3>
          <p>{row.contactPath || "尚未核实联系渠道"}</p>
        </>
      )}
    </section>
  );
}
