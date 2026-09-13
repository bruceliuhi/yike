// @vitest-environment jsdom
import React from "react";
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { CandidateOriginalEvidence } from "../../src/renderer/pages/opportunities/CandidateOriginalEvidence";
import { CandidateAssessmentDetails } from "../../src/renderer/pages/opportunities/CandidateAssessmentDetails";
import { parseRawCandidateEvidence } from "../../src/shared/rawCandidateEvidence";
import { parseCandidateReviewResult } from "../../src/shared/candidateReviewApi";
import { rawEvidenceBinding, rawEvidenceFixture, rawObservationFixture } from "../fixtures/rawCandidateEvidence";
import { assessmentFixture } from "../fixtures/candidateReviewApi";

afterEach(cleanup);
it('labels an author-update model citation independently from the main body',()=>{
 const fixture=assessmentFixture();fixture.intent.citations=[{field:'author_updates.0',quote:'已经结束'}];
 const result=parseCandidateReviewResult({kind:'assessment',requestId:'TEST.author:1',candidateId:fixture.candidateId,assessment:fixture},{requestId:'TEST.author:1'});
 if(result.kind!=='assessment')throw new Error('wrong result');
 render(<CandidateAssessmentDetails assessment={result.assessment}/>);
 expect(screen.getByText('作者回复 1')).toBeVisible();
 expect(screen.getByText('作者回复 1')).not.toHaveAttribute('title');
});

function assessment() {
  const fixture = assessmentFixture();
  fixture.businessMatch.citations = [
    { field: "title", quote: "本人标题原句" },
    { field: "body", quote: "  正文\n逐字原句  " },
    { field: "parent.title", quote: "原帖上下文原句" },
    { field: "parent.body", quote: "父评论原句" },
    { field: "profile.description", quote: "业务画像原句" },
  ];
  fixture.intent.reason = "采购意向依据";
  fixture.urgency.reason = "紧迫程度依据";
  fixture.actionability.reason = "可联系路径依据";
  const result = parseCandidateReviewResult(
    { kind: "assessment", requestId: "TEST.panel:1", candidateId: fixture.candidateId, assessment: fixture },
    { requestId: "TEST.panel:1" },
  );
  if (result.kind !== "assessment") throw new Error("fixture must be assessment");
  return result.assessment;
}

describe("candidate original evidence", () => {
  it("renders full own original text verbatim and escapes malicious markup", () => {
    const raw = rawEvidenceFixture();
    raw.candidate.current_version.body += "x".repeat(1200);
    raw.observations.items[0].content.body = raw.candidate.current_version.body;
    const { container } = render(<CandidateOriginalEvidence evidence={parseRawCandidateEvidence(raw, rawEvidenceBinding)} />);
    const current = screen.getByRole("region", { name: "当前原文" });
    expect(within(current).getByLabelText("评论原文").textContent).toBe(raw.candidate.current_version.body);
    expect(container.querySelector("script")).toBeNull();
    expect(within(current).getByText("公开网站")).toBeVisible();
    expect(within(current).getByText("评论")).toBeVisible();
    expect(within(current).getByText("评论作者🙂")).toBeVisible();
    expect(container.querySelector("textarea, input, a")).toBeNull();
  });

  it("removes source version metadata while keeping original evidence and timestamps visible", () => {
    const raw = rawEvidenceFixture();
    render(<CandidateOriginalEvidence evidence={parseRawCandidateEvidence(raw, rawEvidenceBinding)} />);
    const current = within(screen.getByRole("region", { name: "当前原文" }));
    expect(current.queryByText("查看来源记录详情")).toBeNull();
    expect(screen.queryByText(raw.candidate.current_version.content_version)).toBeNull();
    expect(current.getByText("评论作者🙂")).toBeVisible();
    expect(current.getByText("采集端观察时间")).toBeVisible();
    expect(current.getByText("服务器接收时间")).toBeVisible();
    expect(current.queryByText("候选修订")).toBeNull();
  });

  it("keeps unknown source publication distinct from observer and server times", () => {
    const raw = rawEvidenceFixture();
    raw.candidate.current_version.author_public_id = null;
    raw.observations.items[0].content.author_public_id = null;
    render(<CandidateOriginalEvidence evidence={parseRawCandidateEvidence(raw, rawEvidenceBinding)} />);
    const current = within(screen.getByRole("region", { name: "当前原文" }));
    expect(current.getByText("来源发布时间").nextElementSibling).toHaveTextContent("未知");
    expect(current.getByText("评论公开作者").nextElementSibling).toHaveTextContent("未知");
    expect(current.getByText("采集端观察时间").nextElementSibling).toHaveTextContent(raw.candidate.latest_observed_at);
    expect(current.getByText("服务器接收时间").nextElementSibling).toHaveTextContent(raw.observations.items[0].received_at);
  });

  it("separates container title and parent comment author/body/publication from the current speaker", () => {
    const raw = rawEvidenceFixture();
    render(<CandidateOriginalEvidence evidence={parseRawCandidateEvidence(raw, rawEvidenceBinding)} />);
    const current = within(screen.getByRole("region", { name: "当前原文" }));
    expect(current.getByText("原帖／容器标题（上下文）").nextElementSibling?.textContent).toBe(raw.candidate.current_version.title);
    expect(current.getByText(/不代表当前评论者本人的采购需求/)).toBeVisible();
    const parent = current.getByRole("region", { name: "父评论上下文" });
    expect(within(parent).getByLabelText("父评论原文").textContent).toBe(raw.candidate.current_version.parent?.body);
    expect(within(parent).getByText("父评论公开作者").nextElementSibling).toHaveTextContent("父评论作者");
    expect(within(parent).getByText("父评论发布时间").nextElementSibling).toHaveTextContent("2026-09-09T00:00:00Z");
  });

  it("shows each historical observation with its own content, version and times", () => {
    const raw = rawEvidenceFixture();
    const old = rawObservationFixture();
    old.observation_id = "aaaa1111-1111-4111-8111-111111111111";
    old.version_id = "bbbb1111-1111-4111-8111-111111111111";
    old.content_version = "d".repeat(64);
    old.observed_at = "2026-09-09T01:00:00Z";
    old.received_at = "2026-09-09T02:00:00Z";
    old.content.body = "  旧版自己的正文\n仍保留  ";
    old.content.author_public_id = "旧作者";
    raw.observations.items.push(old);
    raw.observations.total = 2;
    render(<CandidateOriginalEvidence evidence={parseRawCandidateEvidence(raw, rawEvidenceBinding)} />);
    fireEvent.click(screen.getByText("观察历史（2 / 2）"));
    const record = within(screen.getByRole("article", { name: "观察记录 2" }));
    expect(record.getByLabelText("评论原文").textContent).toBe(old.content.body);
    for (const value of [old.observed_at, old.received_at, "旧作者"]) {
      expect(record.getByText(value)).toBeVisible();
    }
    expect(record.queryByText(raw.candidate.current_version.version_id)).not.toBeInTheDocument();
    expect(screen.queryByText("候选修订")).toBeNull();
    expect(record.queryByText(old.version_id)).toBeNull();
    expect(record.queryByText(old.content_version)).toBeNull();
  });

  it("explicitly warns about truncated history and does not borrow another receipt for a missing current observation", () => {
    const raw = rawEvidenceFixture();
    raw.observations.items = Array.from({ length: 100 }, (_, index) => ({
      ...rawObservationFixture(),
      observation_id: `${String(index + 1).padStart(8, "0")}-aaaa-4aaa-8aaa-aaaaaaaaaaaa`,
    }));
    raw.observations.total = 101;
    raw.observations.truncated = true;
    render(<CandidateOriginalEvidence evidence={parseRawCandidateEvidence(raw, rawEvidenceBinding)} />);
    expect(screen.getByText(/观察历史已截断，仅显示 100 条，共 101 条/)).toBeVisible();
    const current = within(screen.getByRole("region", { name: "当前原文" }));
    expect(current.getByText("服务器接收时间").nextElementSibling).toHaveTextContent("当前观察记录不在已返回历史中，未知");
  });

  it.each([["POST", "帖子原文", "帖子"], ["PAGE", "页面原文", "网页"]])(
    "labels %s own title and body without inventing comment context",
    (kind, bodyLabel, kindLabel) => {
      const raw = rawEvidenceFixture();
      raw.candidate.kind = kind;
      raw.candidate.external_comment_id = null;
      raw.candidate.current_version.parent = null;
      raw.observations.items[0].content.parent = null;
      render(<CandidateOriginalEvidence evidence={parseRawCandidateEvidence(raw, rawEvidenceBinding)} />);
      const current = within(screen.getByRole("region", { name: "当前原文" }));
      expect(current.getByLabelText(bodyLabel).textContent).toBe(raw.candidate.current_version.body);
      expect(current.getByText(kindLabel)).toBeVisible();
      expect(current.getByText("来源标题").nextElementSibling?.textContent).toBe(raw.candidate.current_version.title);
      expect(current.queryByText("原帖／容器标题（上下文）")).not.toBeInTheDocument();
      expect(current.queryByRole("region", { name: "父评论上下文" })).not.toBeInTheDocument();
    },
  );
});

describe("candidate assessment details", () => {
  it.each(['EXCLUDE','OBSERVE'] as const)('does not present outreach drafts for %s while keeping evidence', decision => {
    const value={...assessment(),decision,effectiveDecision:decision,grade:null};
    render(<CandidateAssessmentDetails assessment={value}/>);
    expect(screen.queryByRole('region',{name:'评论草稿（未发送）'})).not.toBeInTheDocument();
    expect(screen.queryByRole('region',{name:'私信草稿（未发送）'})).not.toBeInTheDocument();
    expect(screen.queryByText(value.draftDm)).not.toBeInTheDocument();
    expect(screen.getByText(value.evidence.risk)).toBeVisible();
    expect(screen.getByText(value.summary)).toBeVisible();
    expect(screen.getByText(decision==='EXCLUDE'?/当前判断为排除，不建议联系/:/当前仅建议观察，先等待新的采购动作/)).toBeVisible();
  });
  it("shows four separate dimensions with reasons and every verbatim field-labelled citation", () => {
    const value = assessment();
    render(<CandidateAssessmentDetails assessment={value} />);
    for (const [key, label] of [["businessMatch", "业务匹配"], ["intent", "需求意向"], ["urgency", "紧迫度"], ["actionability", "可行动性"]] as const) {
      const dimension = within(screen.getByRole("region", { name: label }));
      expect(dimension.getByText("高")).toBeVisible();
      expect(dimension.getByText(value[key].reason)).toBeVisible();
      for (const citation of value[key].citations) {
        const quote = dimension.getByText(citation.quote, { normalizer: text => text });
        expect(quote.previousElementSibling?.textContent).toMatch(/本人|上下文|画像/);
        expect(dimension.queryByTitle(citation.field)).toBeNull();
        expect(dimension.getByText(citation.quote, { normalizer: (text) => text }).textContent).toBe(citation.quote);
      }
    }
    expect(screen.getByText(value.evidence.risk)).toBeVisible();
    expect(screen.getByText(value.evidence.unknowns)).toBeVisible();
    expect(screen.getByText(value.summary)).toBeVisible();
  });

  it("keeps distinct drafts read-only and judgment time without model metadata", () => {
    const value = assessment();
    const { container } = render(<CandidateAssessmentDetails assessment={value} />);
    expect(screen.getByRole("region", { name: "评论草稿（未发送）" })).toHaveTextContent(value.draftComment);
    expect(screen.getByRole("region", { name: "私信草稿（未发送）" })).toHaveTextContent(value.draftDm);
    expect(container.querySelector("textarea, input, button")).toBeNull();
    expect(screen.queryByText("判断元数据")).toBeNull();
    expect(screen.getByText(value.assessedAt)).toBeVisible();
    for (const text of [value.provider, value.model, value.rule_version, value.rule_sha256, value.strategyVersionId]) {
      expect(screen.queryByText(text)).toBeNull();
    }
  });

  it("does not invent grades or drafts when analysis is absent", () => {
    render(<CandidateAssessmentDetails assessment={undefined} />);
    expect(screen.getByText(/尚无 AI 判断/)).toBeVisible();
    expect(screen.queryByText("高（HIGH）")).not.toBeInTheDocument();
    expect(screen.queryByText("商机等级")).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "评论草稿（未发送）" })).not.toBeInTheDocument();
  });

  it("marks stale analysis as read-only and omits null grade", () => {
    const value = { ...assessment(), grade: null };
    render(<CandidateAssessmentDetails assessment={value} stale />);
    expect(screen.getByRole("status")).toHaveTextContent("此判断已过期，仅供只读核对");
    expect(screen.getByText(value.summary)).toBeVisible();
    expect(screen.queryByText("商机等级")).not.toBeInTheDocument();
    expect(screen.queryByRole('region',{name:'评论草稿（未发送）'})).not.toBeInTheDocument();
    expect(screen.queryByRole('region',{name:'私信草稿（未发送）'})).not.toBeInTheDocument();
  });

  it("preserves UNKNOWN with no citations instead of inventing evidence", () => {
    const value = assessment();
    value.urgency = { level: "UNKNOWN", reason: "未提到明确时间", citations: [] };
    render(<CandidateAssessmentDetails assessment={value} />);
    const dimension = within(screen.getByRole("region", { name: "紧迫度" }));
    expect(dimension.getByText("未知")).toBeVisible();
    expect(dimension.getByText("未提到明确时间")).toBeVisible();
    expect(dimension.getByText("暂无逐字引用；不据此补造依据。")).toBeVisible();
    expect(dimension.queryByRole("list")).not.toBeInTheDocument();
  });
});
