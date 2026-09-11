// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { parseOpportunitySourceEvidence } from "../../src/renderer/domain/opportunitySourceEvidence";
import { FixedSourceEvidence } from "../../src/renderer/pages/opportunities/FixedSourceEvidence";
import { capturedEvidenceFixture } from "../fixtures/opportunitySourceEvidence";

afterEach(cleanup);
it('shows retained author updates and incomplete reading in the included opportunity',()=>{
 const raw:any=capturedEvidenceFixture();Object.assign(raw.snapshot.source,{platform:'PUBLIC_WEB',kind:'PAGE',external_comment_id:null,container_title:null,parent:null,author_updates:['请提供作品'],source_read_scope:'AUTHOR_REPLIES_PARTIAL_SUPPLEMENTS_UNREAD'});
 raw.snapshot.assessment.citations=[{dimension:'intent',field:'source.author_updates.0',quote:'提供作品'}];
 const evidence=parseOpportunitySourceEvidence(raw,{opportunityId:'TEST-o',profileVersionId:'TEST-p'});
 if(evidence.status!=='CAPTURED')throw new Error('invalid fixture');
 render(<FixedSourceEvidence evidence={evidence} onOpen={vi.fn()}/>);
 expect(screen.getByText('请提供作品')).toBeTruthy();expect(screen.getByText(/附言未读/)).toBeTruthy();
 expect(screen.getByText(/作者回复 1/)).toBeTruthy();
});

function captured() {
  const evidence = parseOpportunitySourceEvidence(capturedEvidenceFixture(), {
    opportunityId: "TEST-o",
    profileVersionId: "TEST-p",
  });
  if (evidence.status !== "CAPTURED") throw new Error("TEST fixture must be captured");
  return evidence;
}

describe("固定来源原文证据", () => {
  it("逐字显示评论正文，并把原帖上下文与父评论归属分开", () => {
    const evidence = captured();
    render(<FixedSourceEvidence evidence={evidence} onOpen={vi.fn()} />);

    const region = screen.getByRole("region", { name: "固定原文证据快照" });
    const ownBody = within(region)
      .getByRole("heading", { name: "评论原文" })
      .nextElementSibling;
    expect(ownBody?.textContent).toBe("TEST 评论正文：我们需要批量制作\n  保留 空白");
    expect(within(region).getByText("评论公开作者").nextElementSibling?.textContent).toBe(
      "TEST-public-author",
    );

    const context = within(region).getByTestId("comment-context");
    expect(within(context).getByText("原帖标题（上下文）")).toBeTruthy();
    expect(within(context).getByText("TEST 原帖标题：门店视频需求")).toBeTruthy();
    expect(within(context).getByRole("heading", { name: "父评论" })).toBeTruthy();
    expect(within(context).getByText("TEST 父评论正文：请说明交付时间")).toBeTruthy();
    expect(within(context).getByText("父评论公开作者").nextElementSibling?.textContent).toBe(
      "TEST-parent-author",
    );
    expect(
      within(context).getByText(
        "原帖和父评论仅作上下文，不代表该评论者本人有采购需求。",
      ),
    ).toBeTruthy();
    expect(within(context).queryByText("评论标题")).toBeNull();
  });

  it("对未知公开作者、发布时间和父评论字段明确显示未知", () => {
    const evidence = captured();
    evidence.snapshot.source.author_public_id = null;
    evidence.snapshot.source.published_at = null;
    evidence.snapshot.source.container_title = null;
    evidence.snapshot.source.parent = {
      ...evidence.snapshot.source.parent!,
      body: null,
      author_public_id: null,
      published_at: null,
      public_url: null,
    };
    render(<FixedSourceEvidence evidence={evidence} onOpen={vi.fn()} />);

    expect(screen.getAllByText("未知").length).toBeGreaterThanOrEqual(5);
    expect(screen.queryByRole("button", { name: "查看父评论所在来源" })).toBeNull();
  });

  it("按判断维度和原文字段逐字展示公开引用并保留引用空白", () => {
    render(<FixedSourceEvidence evidence={captured()} onOpen={vi.fn()} />);

    const citations = screen.getByRole("list", { name: "AI 公开原文逐字引用" });
    const rows = within(citations).getAllByRole("listitem");
    expect(rows).toHaveLength(4);
    expect(rows[0].textContent).toContain("业务匹配");
    expect(rows[0].textContent).toContain("原帖标题（上下文）");
    expect(rows[1].textContent).toContain("需求意向");
    expect(rows[1].textContent).toContain("评论原文");
    expect(rows[2].textContent).toContain("紧迫度");
    expect(rows[2].textContent).toContain("父评论原文");
    expect(within(rows[3]).getByTestId("citation-quote").textContent).toBe(
      "\n  保留 空白",
    );
    expect(screen.getByText("另有 1 条画像依据未在此共享，仅显示数量。")).toBeTruthy();
    expect(screen.queryByText(/profile\.description/i)).toBeNull();
  });

  it("没有公开引用时如实说明，且只公开省略画像依据的数量", () => {
    const evidence = captured();
    evidence.snapshot.assessment.citations = [];
    evidence.snapshot.assessment.omitted_profile_citations = 2;
    render(<FixedSourceEvidence evidence={evidence} onOpen={vi.fn()} />);

    expect(screen.getByText("无可展示的公开引用")).toBeTruthy();
    expect(screen.getByText("另有 2 条画像依据未在此共享，仅显示数量。")).toBeTruthy();
  });

  it("长正文以普通按钮展开，展开后仍是完整逐字内容", () => {
    const evidence = captured();
    const longBody = `TEST 起始\n  ${"很长的原文 ".repeat(120)}\nTEST 完整结尾`;
    evidence.snapshot.source.body = longBody;
    render(<FixedSourceEvidence evidence={evidence} onOpen={vi.fn()} />);

    const button = screen.getByRole("button", { name: "展开完整原文" });
    expect(button.getAttribute("aria-expanded")).toBe("false");
    const body = screen.getByTestId("fixed-evidence-source-body");
    expect(body.classList.contains("fixed-evidence-body--collapsed")).toBe(true);
    expect(body.textContent).toBe(longBody);

    fireEvent.click(button);
    expect(button.getAttribute("aria-expanded")).toBe("true");
    expect(body.classList.contains("fixed-evidence-body--collapsed")).toBe(false);
    expect(body.textContent).toBe(longBody);
  });

  it("把版本、摘要、模型规则及历史判断时间收在可展开明细中", () => {
    const evidence = captured();
    render(<FixedSourceEvidence evidence={evidence} onOpen={vi.fn()} />);

    const details = screen.getByText("版本与当时判断明细").closest("details");
    expect(details?.open).toBe(false);
    fireEvent.click(screen.getByText("版本与当时判断明细"));
    expect(details?.open).toBe(true);
    expect(within(details!).getByText("TEST-source-version-1")).toBeTruthy();
    expect(within(details!).getByText("a".repeat(64))).toBeTruthy();
    expect(within(details!).getByText("TEST-model")).toBeTruthy();
    expect(within(details!).getByText("TEST-rule-v1")).toBeTruthy();
    expect(within(details!).getByText("TEST-p · 第 7 版")).toBeTruthy();
    expect(within(details!).getByText("有效（纳入时）")).toBeTruthy();
    expect(within(details!).getByText("直接打开")).toBeTruthy();
    expect(within(details!).getByText("评论")).toBeTruthy();
    expect(within(details!).queryByText("OPEN")).toBeNull();
    expect(within(details!).queryByText("DIRECT")).toBeNull();
    expect(within(details!).queryByText("COMMENT")).toBeNull();
    expect(
      details?.querySelector('time[datetime="2026-09-10T01:05:00.999999+00:00"]'),
    ).toBeTruthy();
    expect(
      details?.querySelector('time[datetime="2026-09-10T01:07:00.123456+00:00"]'),
    ).toBeTruthy();
  });

  it("分别显示四个事件时间并保留原始时间戳", () => {
    const evidence = captured();
    render(<FixedSourceEvidence evidence={evidence} onOpen={vi.fn()} />);
    const region = screen.getByRole("region", { name: "固定原文证据快照" });

    for (const [label, value] of [
      ["来源发布", evidence.snapshot.source.published_at],
      ["采集端观察", evidence.snapshot.observation.observed_at],
      ["服务器收到", evidence.snapshot.observation.received_at],
      ["纳入留存", evidence.snapshot.captured_at],
    ] as const) {
      const term = within(region).getByText(label);
      const time = term.nextElementSibling?.querySelector("time");
      expect(time?.getAttribute("datetime")).toBe(value);
      expect(time?.textContent).not.toBe(value);
    }
  });

  it("只把已校验的父评论公开链接交给打开回调且不会自动打开", () => {
    const evidence = captured();
    const onOpen = vi.fn();
    render(<FixedSourceEvidence evidence={evidence} onOpen={onOpen} />);
    expect(onOpen).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "查看父评论所在来源" }));
    expect(onOpen).toHaveBeenCalledOnce();
    expect(onOpen).toHaveBeenCalledWith(evidence.snapshot.source.parent?.public_url);
  });

  it("compact 模式仍保留正文、来源事实和非当前采购或联系许可边界", () => {
    const evidence = captured();
    const view = render(
      <FixedSourceEvidence evidence={evidence} onOpen={vi.fn()} compact />,
    );

    expect(view.container.querySelector(".fixed-source-evidence--compact")).toBeTruthy();
    expect(screen.getByTestId("fixed-evidence-source-body").textContent).toBe(
      evidence.snapshot.source.body,
    );
    expect(screen.getByText("来源发布")).toBeTruthy();
    expect(
      screen.getByText(
        "这是纳入时的历史留存，不证明对方当前仍在采购，也不表示已允许联系。来源当前失效时，有权查看的历史快照仍保留。",
      ),
    ).toBeTruthy();
  });
});
