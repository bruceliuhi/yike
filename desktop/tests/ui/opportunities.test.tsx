// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import {
  OpportunitiesPage,
  OpportunityDetailPage,
  PUBLIC_SAMPLE,
  customerCsv,
  EvidencePanel,
} from "../../src/renderer/pages/Opportunities";
import { capturedEvidenceFixture } from "../fixtures/opportunitySourceEvidence";
import { parseOpportunitySourceEvidence } from "../../src/renderer/domain/opportunitySourceEvidence";
import { parseRoute } from "../../src/renderer/domain/routes";
import type { AppContextValue } from "../../src/renderer/app/context";
import type { YikeService } from "../../src/renderer/services/contracts";
let context: AppContextValue;
vi.mock("../../src/renderer/app/context", () => ({ useApp: () => context }));
beforeEach(() => {
  context = {
    service: {
      opportunities: vi.fn().mockResolvedValue([]),
      opportunity: vi.fn(),
      copy: vi.fn().mockResolvedValue(undefined),
      openExternal: vi.fn().mockResolvedValue(undefined),
    } as unknown as YikeService,
    session: { authenticated: true, userId: "test-a" },
    route: parseRoute("#/opportunities?scope=sample"),
    navigate: vi.fn(),
    notify: vi.fn(),
    refreshSession: vi.fn(),
  };
});
afterEach(cleanup);
describe("customer and public sample boundaries", () => {
  it("keeps public sample selection and customer export disabled", async () => {
    render(<OpportunitiesPage />);
    await screen.findByText(PUBLIC_SAMPLE.title);
    expect(
      (
        screen.getByRole("checkbox", {
          name: "选择本页客户商机",
        }) as HTMLInputElement
      ).disabled,
    ).toBe(true);
    expect(
      (
        screen.getByRole("button", {
          name: "导出所选客户商机",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
    expect(customerCsv([PUBLIC_SAMPLE])).not.toContain(PUBLIC_SAMPLE.title);
  });
  it("filters actual service results and retains the list query when opening details", async () => {
    context.route = parseRoute("#/opportunities");
    context.service.opportunities = vi.fn().mockResolvedValue([
      {
        ...PUBLIC_SAMPLE,
        id: "real-a",
        sample: false,
        title: "北京展厅",
        buyer: "测试需求方",
        intentStatus: "READY",
      },
      {
        ...PUBLIC_SAMPLE,
        id: "real-b",
        sample: false,
        title: "上海展台",
        buyer: "测试需求方",
        intentStatus: "NEW",
      },
    ]);
    render(<OpportunitiesPage />);
    await screen.findByText("北京展厅");
    fireEvent.change(screen.getByRole("textbox", { name: "搜索商机" }), {
      target: { value: "上海" },
    });
    expect(screen.queryByText("北京展厅")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "查看证据" }));
    expect(context.navigate).toHaveBeenCalledWith(
      expect.stringContaining("/opportunities/real-b?returnTo="),
    );
    expect(
      decodeURIComponent(vi.mocked(context.navigate).mock.calls[0][0]),
    ).toContain("q=");
  });
  it("opens the verified exact source and copies without fabricating a sent fact", async () => {
    context.route = parseRoute("#/opportunities/sample");
    render(<OpportunityDetailPage />);
    await screen.findByText(PUBLIC_SAMPLE.title);
    fireEvent.click(screen.getByRole("button", { name: /查看来源原文/ }));
    await waitFor(() =>
      expect(context.service.openExternal).toHaveBeenCalledWith(
        PUBLIC_SAMPLE.url,
      ),
    );
    fireEvent.click(screen.getByRole("button", { name: "复制草稿" }));
    await waitFor(() =>
      expect(context.service.copy).toHaveBeenCalledWith(PUBLIC_SAMPLE.comment),
    );
    expect(screen.queryByText("已发送")).toBeNull();
  });
  it("escapes CSV formula prefixes and excludes samples even if supplied in a batch", () => {
    const result = customerCsv([
      {
        ...PUBLIC_SAMPLE,
        id: "customer-id",
        sample: false,
        title: '=HYPERLINK("bad")',
      },
      PUBLIC_SAMPLE,
    ]);
    expect(result).toContain("'=HYPERLINK");
    expect(result).not.toContain(PUBLIC_SAMPLE.title);
  });
});

describe("existing evidence panel with fixed original evidence", () => {
  function capturedRow() {
    return { ...PUBLIC_SAMPLE, id: "TEST-o", profileVersionId: "TEST-p", sample: false,
      sourceStatus: "BLOCKED", sourceEvidence: parseOpportunitySourceEvidence(capturedEvidenceFixture(), {
        opportunityId: "TEST-o", profileVersionId: "TEST-p",
      }) };
  }
  it("opens the fixed source URL only on explicit click and reports native failure", async () => {
    const row = capturedRow();
    context.service.openExternal = vi.fn().mockRejectedValue(new Error("TEST 打开失败"));
    render(<EvidencePanel opportunity={row} />);
    expect(context.service.openExternal).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "查看来源原文" }));
    await waitFor(() => expect(context.service.openExternal).toHaveBeenCalledWith(
      "https://example.test/posts/TEST-source-1?comment=TEST-comment-1",
    ));
    expect(context.notify).toHaveBeenCalledWith("TEST 打开失败", "error");
  });
  it("distinguishes confirmed absence from unloaded evidence and labels the legacy excerpt", () => {
    const row = { ...PUBLIC_SAMPLE, id: "TEST-o", sample: false,
      sourceEvidence: { status: "UNAVAILABLE", reason: "NOT_CAPTURED" } as const };
    const view = render(<EvidencePanel opportunity={row} compact />);
    expect(screen.getByText("未留存固定原文证据")).toBeTruthy();
    expect(screen.getByText("旧版摘录（非固定原文）")).toBeTruthy();
    view.rerender(<EvidencePanel opportunity={{ ...row, sourceEvidence: undefined }} compact />);
    expect(screen.queryByText("未留存固定原文证据")).toBeNull();
    expect(screen.getByText("固定原文证据尚未加载")).toBeTruthy();
  });
  it("shows the fixed body and current judgment as separate sections, not the legacy excerpt", () => {
    const row = capturedRow();
    render(<EvidencePanel opportunity={row} />);
    expect(screen.getByText(/TEST 评论正文/)).toBeTruthy();
    expect(screen.getByRole("heading", { name: "当前复核与判断" })).toBeTruthy();
    expect(screen.queryByText(PUBLIC_SAMPLE.excerpt)).toBeNull();
    expect(context.service.copy).not.toHaveBeenCalled();
    expect(context.service.openExternal).not.toHaveBeenCalled();
  });
});
