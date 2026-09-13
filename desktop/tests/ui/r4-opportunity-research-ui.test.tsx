// @vitest-environment jsdom
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import {
  OpportunitiesPage,
  OpportunityDetailPage,
  PUBLIC_SAMPLE,
} from "../../src/renderer/pages/Opportunities";
import { readResearchRecord } from "../../src/renderer/services/opportunityResearch";
import { EvidenceTimeline } from "../../src/renderer/pages/opportunities/EvidenceTimeline";
import { SimilarResearchDrawer } from "../../src/renderer/pages/opportunities/SimilarResearchDrawer";
import type { AppContextValue } from "../../src/renderer/app/context";
import type { YikeService } from "../../src/renderer/services/contracts";
import { parseRoute } from "../../src/renderer/domain/routes";
import { capturedEvidenceFixture } from "../fixtures/opportunitySourceEvidence";
import { parseOpportunitySourceEvidence } from "../../src/renderer/domain/opportunitySourceEvidence";
import {
  binding,
  collection,
  researchProfile,
  researchRecord,
  researchRow,
  similar,
  timeline,
} from "./r4-opportunity-research-fixtures";
let context: AppContextValue;
vi.mock("../../src/renderer/app/context", () => ({ useApp: () => context }));
beforeEach(() => {
  context = {
    session: {
      authenticated: true,
      userId: binding.userId,
      accountScope: binding.accountScope,
    },
    route: parseRoute("#/opportunities"),
    navigate: vi.fn(),
    notify: vi.fn(),
    refreshSession: vi.fn(),
    service: {
      opportunityResearch: {
        list: vi.fn().mockResolvedValue(collection),
        timeline: vi.fn().mockResolvedValue(timeline),
        similar: vi.fn(async (_binding, requestId) => ({
          ...structuredClone(similar),
          requestId,
        })),
      },
      profiles: vi.fn().mockResolvedValue([researchProfile]),
      opportunity: vi.fn().mockResolvedValue({ ...researchRow,
        sourceEvidence: { status: "UNAVAILABLE", reason: "NOT_CAPTURED" } }),
      opportunities: vi.fn().mockResolvedValue([researchRow]),
    } as unknown as YikeService,
  };
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("R4 opportunity collection and source timeline", () => {
  it("keeps contact preparation available after closing the expanded research drawer", async () => {
    context.route = parseRoute(
      "#/opportunities/" + researchRow.id + "?tab=changes",
    );
    render(<OpportunityDetailPage />);
    await screen.findByText(researchRow.title);
    expect(screen.getByText("有效")).toBeTruthy();
    expect(screen.getByText("已确认")).toBeTruthy();
    expect(screen.queryByText("OPEN")).toBeNull();
    expect(screen.queryByText("CONFIRMED")).toBeNull();
    expect(screen.getByRole("textbox", { name: "询问草稿" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "多找类似" }));
    await screen.findByDisplayValue(researchProfile.description);
    expect(screen.queryByRole("textbox", { name: "询问草稿" })).toBeNull();
    expect(screen.getByText(/查看依据原文/).closest("details")?.open).toBe(
      false,
    );
    fireEvent.click(screen.getByRole("button", { name: "关闭多找类似" }));
    expect(screen.getByRole("textbox", { name: "询问草稿" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "生成联系草稿" })).toBeTruthy();
  });
  it("keeps the old facade available without calling R4 when trusted scope is absent", async () => {
    context.session = { authenticated: true, userId: binding.userId };
    render(<OpportunitiesPage />);
    await screen.findByText(researchRow.title);
    expect(screen.getByText(/当前账户空间尚未核验/)).toBeTruthy();
    expect(context.service.opportunityResearch!.list).not.toHaveBeenCalled();
    cleanup();
    context.route = parseRoute("#/opportunities/" + researchRow.id);
    render(<OpportunityDetailPage />);
    await screen.findByText(researchRow.title);
    expect(context.service.opportunity).toHaveBeenCalledWith(researchRow.id, expect.any(AbortSignal));
    expect(context.service.opportunityResearch!.list).not.toHaveBeenCalled();
    await expect(
      readResearchRecord(
        context.service.opportunityResearch!,
        context.session,
        researchRow.id,
      ),
    ).rejects.toThrow("账户空间尚未核验");
    expect(context.service.opportunityResearch!.list).not.toHaveBeenCalled();
  });
  it("refuses timeline and similar preview before a request when session scope is absent", () => {
    context.session = { authenticated: true, userId: binding.userId };
    render(<EvidenceTimeline opportunity={researchRow} />);
    expect(screen.getByText(/当前账户空间尚未核验/)).toBeTruthy();
    expect(
      context.service.opportunityResearch!.timeline,
    ).not.toHaveBeenCalled();
    cleanup();
    const handoff = vi.fn();
    render(
      <SimilarResearchDrawer
        opportunity={researchRow}
        onClose={vi.fn()}
        onCreateDraft={handoff}
      />,
    );
    expect(screen.getByText(/当前账户空间尚未核验/)).toBeTruthy();
    expect(context.service.opportunityResearch!.similar).not.toHaveBeenCalled();
    expect(context.service.profiles).not.toHaveBeenCalled();
    expect(handoff).not.toHaveBeenCalled();
  });
  it("does not display another workspace's classification for the same user", async () => {
    context.session = {
      ...context.session,
      accountScope: { id: "other-space", version: 1 },
    };
    render(<OpportunitiesPage />);
    await screen.findByText(/身份或证据版本不匹配/);
    expect(screen.queryByText(researchRow.title)).toBeNull();
  });
  it("preserves filters and the exact selection in a detail return path", async () => {
    render(<OpportunitiesPage />);
    await screen.findByText(researchRow.title);
    fireEvent.change(screen.getByRole("textbox", { name: "搜索商机" }), {
      target: { value: "服务" },
    });
    fireEvent.change(screen.getByRole("combobox", { name: "筛选复核状态" }), {
      target: { value: "RECOGNIZED" },
    });
    fireEvent.click(screen.getByRole("button", { name: "查看完整证据" }));
    const path = vi.mocked(context.navigate).mock.calls[0][0];
    const back = new URLSearchParams(path.split("?")[1]).get("returnTo")!;
    expect(new URLSearchParams(back.split("?")[1]).get("q")).toBe("服务");
    expect(new URLSearchParams(back.split("?")[1]).get("selected")).toBe(
      researchRow.id,
    );
    cleanup();
    context.route = parseRoute("#" + back);
    render(<OpportunitiesPage />);
    expect(await screen.findByDisplayValue("服务")).toBeTruthy();
    expect(
      (
        screen.getByRole("combobox", {
          name: "筛选复核状态",
        }) as HTMLSelectElement
      ).value,
    ).toBe("RECOGNIZED");
  });
  it("shows observations as research evidence without customer outreach actions", async () => {
    context.route = parseRoute("#/opportunities/" + researchRow.id);
    const record = structuredClone(researchRecord);
    record.classification.category = "OBSERVATION";
    record.classification.reason = "TEST 先观察补证";
    context.service.opportunityResearch!.list = vi
      .fn()
      .mockResolvedValue({ ...collection, records: [record] });
    render(<OpportunityDetailPage />);
    await screen.findByText("研究判断");
    expect(screen.getByText("观察池")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "生成联系草稿" })).toBeNull();
    expect(screen.queryByRole("button", { name: "添加跟进" })).toBeNull();
  });
  it("separates observation from opportunity despite identical processing statuses", async () => {
    const observation = structuredClone(researchRecord);
    observation.opportunity = {
      ...observation.opportunity,
      id: "test-observation",
      title: "TEST 新店开业",
      url: "https://example.test/opening",
    };
    observation.classification.category = "OBSERVATION";
    observation.classification.type = "开店";
    observation.classification.evidence[0].sourceUrl =
      observation.opportunity.url;
    context.service.opportunityResearch!.list = vi.fn().mockResolvedValue({
      ...collection,
      records: [researchRecord, observation],
    });
    render(<OpportunitiesPage />);
    await screen.findByText(researchRow.title);
    expect(screen.queryByText("TEST 新店开业")).toBeNull();
    fireEvent.click(screen.getByRole("tab", { name: "观察池" }));
    expect(screen.getByText("TEST 新店开业")).toBeTruthy();
    expect(screen.queryByText(researchRow.title)).toBeNull();
    expect(
      (
        screen.getByRole("button", {
          name: "导出所选客户商机",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
  });
  it("rejects another user snapshot and offers retry instead of an empty result", async () => {
    context.service.opportunityResearch!.list = vi
      .fn()
      .mockResolvedValue({ ...collection, userId: "other" });
    render(<OpportunitiesPage />);
    await screen.findByText(/研究数据的身份或证据版本不匹配/);
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.getByRole("button", { name: "重试" })).toBeTruthy();
  });
  it("discards a previous identity's late collection", async () => {
    let finish!: (value: typeof collection) => void;
    context.service.opportunityResearch!.list = vi
      .fn()
      .mockImplementationOnce(
        () =>
          new Promise<typeof collection>((resolve) => {
            finish = resolve;
          }),
      )
      .mockResolvedValue({ ...collection, userId: "other", records: [] });
    const ui = render(<OpportunitiesPage />);
    await act(async () => {});
    context = {
      ...context,
      session: {
        authenticated: true,
        userId: "other",
        accountScope: binding.accountScope,
      },
    };
    ui.rerender(<OpportunitiesPage />);
    await act(async () => {
      finish(collection);
    });
    expect(screen.queryByText(researchRow.title)).toBeNull();
  });
  it("shows bound before/after evidence without treating access failure as closure", async () => {
    render(<EvidenceTimeline opportunity={researchRow} />);
    await screen.findByText("TEST 资料截止延后");
    expect(screen.getByText("资料截止为9月15日")).toBeTruthy();
    expect(screen.getByText("资料截止为9月20日")).toBeTruthy();
    expect(screen.getByText("人工登记")).toBeTruthy();
    expect(screen.queryByText("渠道回执")).toBeNull();
    expect(screen.getByText("本次访问失败")).toBeTruthy();
    expect(screen.queryByText("已关闭")).toBeNull();
  });
  it("keeps sample history at one original with unknown observation time", async () => {
    render(<EvidenceTimeline opportunity={PUBLIC_SAMPLE} />);
    expect(screen.getByText("原文版本 v1")).toBeTruthy();
    expect(screen.getByText(/首次留存时间.*待真实采集回执/)).toBeTruthy();
    expect(
      context.service.opportunityResearch!.timeline,
    ).not.toHaveBeenCalled();
  });
  it("retains legacy customer functionality when the new optional adapter is absent", async () => {
    delete context.service.opportunityResearch;
    render(<OpportunitiesPage />);
    await screen.findByText(researchRow.title);
    expect(screen.getByText(/需求分类与观察服务尚未接通/)).toBeTruthy();
  });
  it("never displays a mismatched opportunity returned for a detail request", async () => {
    delete context.service.opportunityResearch;
    context.route = parseRoute("#/opportunities/wanted");
    render(<OpportunityDetailPage />);
    await screen.findByText(/机会身份不匹配/);
    expect(screen.queryByText(researchRow.title)).toBeNull();
  });
});

it("keeps observation guidance optional without hiding classification or its navigation", async () => {
  render(<OpportunitiesPage />);
  await screen.findByText(researchRow.title);
  const summary = screen.getByText("什么情况先观察？");
  expect(summary.closest("details")).not.toHaveAttribute("open");
  expect(screen.getByText(/开店、扩产、参展等业务变化/)).not.toBeVisible();
  expect(screen.getByRole("tab", { name: "观察池" })).toBeVisible();
  expect(screen.getByText(researchRecord.classification.reason)).toBeVisible();
  fireEvent.click(summary);
  expect(screen.getByText(/开店、扩产、参展等业务变化/)).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "查看观察池" }));
  expect(screen.getByRole("tab", { name: "观察池" })).toHaveAttribute("aria-selected", "true");
});

describe("fixed evidence in the preferred R4 detail path", () => {
  function detailRoute() {
    context.route = parseRoute("#/opportunities/" + researchRow.id);
  }
  function capturedRow() {
    return { ...researchRow, sourceEvidence: parseOpportunitySourceEvidence(
      capturedEvidenceFixture({ opportunityId: researchRow.id, profileVersionId: researchRow.profileVersionId }),
      { opportunityId: researchRow.id, profileVersionId: researchRow.profileVersionId },
    ) };
  }
  it("supplements missing R4 fixed evidence from the ordinary authenticated detail", async () => {
    detailRoute();
    context.service.opportunity = vi.fn().mockResolvedValue(capturedRow());
    render(<OpportunityDetailPage />);
    await screen.findByText(researchRow.title);
    expect(context.service.opportunity).toHaveBeenCalledWith(researchRow.id, expect.any(AbortSignal));
    expect(context.service.opportunityResearch!.list).toHaveBeenCalledTimes(1);
  });
  it("does not issue a second read when R4 already carries validated fixed evidence", async () => {
    detailRoute();
    context.service.opportunityResearch!.list = vi.fn().mockResolvedValue({ ...collection,
      records: [{ ...researchRecord, opportunity: capturedRow() }] });
    render(<OpportunityDetailPage />);
    await screen.findByText(researchRow.title);
    expect(context.service.opportunity).not.toHaveBeenCalled();
  });
  it.each(["identity", "profile", "missing", "malformed"])("rejects %s in the supplemental detail instead of showing incomplete evidence", async (kind) => {
    detailRoute();
    const row = capturedRow();
    if (kind === "identity") row.id = "TEST-other";
    if (kind === "profile") row.profileVersionId = "TEST-other";
    if (kind === "missing") delete (row as { sourceEvidence?: unknown }).sourceEvidence;
    if (kind === "malformed") Object.assign(row, { sourceEvidence: null });
    context.service.opportunity = vi.fn().mockResolvedValue(row);
    render(<OpportunityDetailPage />);
    await screen.findByText(/原文证据.*重新读取/);
    expect(screen.queryByText(researchRow.title)).toBeNull();
    expect(screen.queryByText("未留存固定原文证据")).toBeNull();
  });
  it("retries a failed supplementary read without silently substituting the legacy excerpt", async () => {
    detailRoute();
    context.service.opportunity = vi.fn().mockRejectedValueOnce(new Error("TEST 原文读取失败"))
      .mockResolvedValueOnce(capturedRow());
    render(<OpportunityDetailPage />);
    await screen.findByText("TEST 原文读取失败");
    expect(screen.queryByText(researchRow.title)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "重试" }));
    await screen.findByText(researchRow.title);
    expect(context.service.opportunity).toHaveBeenCalledTimes(2);
  });
  it("aborts the shared generation and never starts fallback after an account switch", async () => {
    detailRoute();
    let resolve!: (value: typeof collection) => void;
    context.service.opportunityResearch!.list = vi.fn(() => new Promise<typeof collection>((done) => { resolve = done; }));
    const view = render(<OpportunityDetailPage />);
    await waitFor(() => expect(context.service.opportunityResearch!.list).toHaveBeenCalledTimes(1));
    const signal = vi.mocked(context.service.opportunityResearch!.list).mock.calls[0][0]!;
    context = { ...context, session: { authenticated: false } };
    view.rerender(<OpportunityDetailPage />);
    expect(signal.aborted).toBe(true);
    await act(async () => { resolve(collection); });
    expect(context.service.opportunity).not.toHaveBeenCalled();
    expect(screen.queryByText(researchRow.title)).toBeNull();
  });
  it("does not display a late fallback after switching to another opportunity", async () => {
    detailRoute();
    let resolve!: (value: ReturnType<typeof capturedRow>) => void;
    context.service.opportunity = vi.fn(() => new Promise<ReturnType<typeof capturedRow>>((done) => { resolve = done; }));
    const view = render(<OpportunityDetailPage />);
    await waitFor(() => expect(context.service.opportunity).toHaveBeenCalledTimes(1));
    const signal = vi.mocked(context.service.opportunity).mock.calls[0][1]!;
    context = { ...context, route: parseRoute("#/opportunities/TEST-other") };
    view.rerender(<OpportunityDetailPage />);
    expect(signal.aborted).toBe(true);
    await act(async () => { resolve(capturedRow()); });
    await screen.findByText(/未找到该记录/);
    expect(screen.queryByText(researchRow.title)).toBeNull();
  });
});
describe("R4 similar research local draft preview", () => {
  it("never calls services or hands off a public sample", () => {
    const handoff = vi.fn();
    render(
      <SimilarResearchDrawer
        opportunity={PUBLIC_SAMPLE}
        onClose={vi.fn()}
        onCreateDraft={handoff}
      />,
    );
    expect(
      (
        screen.getByRole("button", {
          name: "创建任务草稿",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
    expect(context.service.opportunityResearch!.similar).not.toHaveBeenCalled();
    expect(handoff).not.toHaveBeenCalled();
  });
  it("exposes editable terms, actual supported platform and unknown soubei before local handoff", async () => {
    const handoff = vi.fn();
    render(
      <SimilarResearchDrawer
        opportunity={researchRow}
        onClose={vi.fn()}
        onCreateDraft={handoff}
      />,
    );
    await screen.findByDisplayValue(researchProfile.description);
    expect(screen.queryByRole("checkbox", { name: "抖音" })).toBeNull();
    fireEvent.click(screen.getByRole("checkbox", { name: "公开网站" }));
    fireEvent.change(screen.getByRole("spinbutton", { name: "单次搜贝上限" }), {
      target: { value: "50" },
    });
    fireEvent.click(screen.getByRole("button", { name: "删除TEST 服务比较" }));
    fireEvent.click(screen.getByRole("button", { name: "创建任务草稿" }));
    await waitFor(() => expect(handoff).toHaveBeenCalledTimes(1));
    const input = handoff.mock.calls[0][0];
    expect(input.keywords).toEqual(["TEST 服务询价"]);
    expect(input.exclusions).toEqual(["TEST 招聘"]);
    expect(input.platforms).toEqual(["web"]);
    expect(input.limits).toMatchObject({ soubei: 50, stopAtAnyLimit: true });
    expect(input.usage.status).toBe("UNKNOWN");
    expect(input.binding).toEqual(binding);
  });
  it("rechecks source and profile before handoff and preserves edited text on rejection", async () => {
    const handoff = vi.fn();
    render(
      <SimilarResearchDrawer
        opportunity={researchRow}
        onClose={vi.fn()}
        onCreateDraft={handoff}
      />,
    );
    await screen.findByDisplayValue(researchProfile.description);
    fireEvent.change(screen.getByRole("textbox", { name: "新任务名称" }), {
      target: { value: "TEST 人工新名称" },
    });
    fireEvent.click(screen.getByRole("checkbox", { name: "公开网站" }));
    context.service.opportunityResearch!.list = vi.fn().mockResolvedValue({
      ...collection,
      records: [
        {
          ...researchRecord,
          opportunity: { ...researchRow, sourceEvidenceVersion: "v3" },
          classification: {
            ...researchRecord.classification,
            evidence: [
              {
                ...researchRecord.classification.evidence[0],
                evidenceVersion: "v3",
              },
            ],
          },
        },
      ],
    });
    fireEvent.click(screen.getByRole("button", { name: "创建任务草稿" }));
    await screen.findByText(/来源或画像已变化/);
    expect(screen.getByDisplayValue("TEST 人工新名称")).toBeTruthy();
    expect(handoff).not.toHaveBeenCalled();
  });
  it("requires explicit discard when edited configuration is closed", async () => {
    const close = vi.fn();
    render(
      <SimilarResearchDrawer
        opportunity={researchRow}
        onClose={close}
        onCreateDraft={vi.fn()}
      />,
    );
    await screen.findByDisplayValue(researchProfile.description);
    fireEvent.change(screen.getByRole("textbox", { name: "新任务名称" }), {
      target: { value: "TEST 修改" },
    });
    fireEvent.click(screen.getByRole("button", { name: "关闭多找类似" }));
    expect(
      screen.getByRole("dialog", { name: "放弃本次相似研究配置？" }),
    ).toBeTruthy();
    expect(close).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "放弃更改" }));
    expect(close).toHaveBeenCalledOnce();
  });
  it("refuses local handoff if recognition is revoked during the final read", async () => {
    const handoff = vi.fn();
    render(
      <SimilarResearchDrawer
        opportunity={researchRow}
        onClose={vi.fn()}
        onCreateDraft={handoff}
      />,
    );
    await screen.findByDisplayValue(researchProfile.description);
    fireEvent.click(screen.getByRole("checkbox", { name: "公开网站" }));
    context.service.opportunityResearch!.list = vi.fn().mockResolvedValue({
      ...collection,
      records: [
        {
          ...researchRecord,
          classification: {
            ...researchRecord.classification,
            review: { status: "PENDING", reviewer: "", reviewedAt: null },
          },
        },
      ],
    });
    fireEvent.click(screen.getByRole("button", { name: "创建任务草稿" }));
    await screen.findByText(/认可记录或建议已变化/);
    expect(handoff).not.toHaveBeenCalled();
  });
  it("does not apply a late preflight after the user edits the requested configuration", async () => {
    let finish!: (value: typeof collection) => void;
    const handoff = vi.fn();
    render(
      <SimilarResearchDrawer
        opportunity={researchRow}
        onClose={vi.fn()}
        onCreateDraft={handoff}
      />,
    );
    await screen.findByDisplayValue(researchProfile.description);
    fireEvent.click(screen.getByRole("checkbox", { name: "公开网站" }));
    context.service.opportunityResearch!.list = vi.fn(
      () =>
        new Promise<typeof collection>((resolve) => {
          finish = resolve;
        }),
    );
    fireEvent.click(screen.getByRole("button", { name: "创建任务草稿" }));
    await act(async () => {});
    fireEvent.change(screen.getByRole("textbox", { name: "新任务名称" }), {
      target: { value: "TEST 迟到期间手工修改" },
    });
    await act(async () => {
      finish(collection);
    });
    expect(screen.getByText(/核验期间配置已修改/)).toBeTruthy();
    expect(handoff).not.toHaveBeenCalled();
  });
  it("does not hand off a response after the same user switches workspace", async () => {
    let finish!: (value: typeof collection) => void;
    const handoff = vi.fn();
    const ui = render(
      <SimilarResearchDrawer
        opportunity={researchRow}
        onClose={vi.fn()}
        onCreateDraft={handoff}
      />,
    );
    await screen.findByDisplayValue(researchProfile.description);
    fireEvent.click(screen.getByRole("checkbox", { name: "公开网站" }));
    context.service.opportunityResearch!.list = vi.fn(
      () =>
        new Promise<typeof collection>((resolve) => {
          finish = resolve;
        }),
    );
    fireEvent.click(screen.getByRole("button", { name: "创建任务草稿" }));
    await act(async () => {});
    context = {
      ...context,
      session: {
        ...context.session,
        accountScope: { id: "other-space", version: 1 },
      },
    };
    ui.rerender(
      <SimilarResearchDrawer
        opportunity={researchRow}
        onClose={vi.fn()}
        onCreateDraft={handoff}
      />,
    );
    await act(async () => {
      finish(collection);
    });
    expect(handoff).not.toHaveBeenCalled();
  });
  it("bounds a suggestion read and offers a safe retry", async () => {
    vi.useFakeTimers();
    context.service.opportunityResearch!.similar = vi.fn(
      () => new Promise<typeof similar>(() => {}),
    );
    render(
      <SimilarResearchDrawer opportunity={researchRow} onClose={vi.fn()} />,
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30001);
    });
    expect(screen.getByText(/相似研究建议读取超时/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "重试" })).toBeTruthy();
  });
});
