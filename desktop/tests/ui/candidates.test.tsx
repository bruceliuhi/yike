// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { AppProvider } from "../../src/renderer/app/context";
import { clearLocalDrafts } from "../../src/renderer/app/hooks";
import { operationLedgerKey } from "../../src/renderer/app/operationLedger";
import { CandidatesPage } from "../../src/renderer/pages/Opportunities";
import { service as baseService } from "../../src/renderer/services/client";
import {
  ServiceError,
  type YikeService,
} from "../../src/renderer/services/contracts";
import type {
  Candidate,
  CandidateAssessment,
  CandidatePage,
  CandidateReceipt,
  CandidateReview,
  CandidateReviewResult,
} from "../../src/renderer/domain/candidates";
import { reviewSnapshot } from "../../src/renderer/domain/candidates";
import type { Profile } from "../../src/renderer/domain/models";

afterEach(() => {
  cleanup();
  clearLocalDrafts();
  localStorage.clear();
  vi.restoreAllMocks();
  vi.useRealTimers();
  window.history.replaceState(null, "", "/");
});
const confirmed: Profile = {
  id: "profile-1",
  version: 1,
  status: "CONFIRMED",
  description: "仅供契约测试",
  fields: {
    service: "展区设计",
    customer: "采购方",
    regions: "上海",
    preference: "",
    exclusions: "",
  },
};
const assessment: CandidateAssessment = {
  id: "assessment-1",
  profileId: confirmed.id,
  profileVersion: 1,
  candidateRevision: 2,
  sourceVersionId: "source-v2",
  assessedAt: "2026-09-09T10:00:00Z",
  evidence: {
    matchReason: "测试服务与公开需求匹配",
    actionSignal: "公告征询设计方案",
    value: "需进一步确认采购计划",
    risk: "预算尚未确定",
    unknowns: "采购联系人资格待核实",
  },
};
function candidate(patch: Partial<Candidate> = {}): Candidate {
  return {
    id: "candidate-1",
    revision: 2,
    sample: false,
    status: "PENDING_REVIEW",
    title: "契约测试需求",
    buyer: "测试采购方",
    platform: "公开网站",
    sourceLabel: "测试公告来源",
    sourceId: "source-1",
    sourceVersionId: "source-v2",
    sourceStatus: "OPEN",
    url: "https://example.com/inquiry",
    excerpt: "这是一段测试原始摘录。",
    summary: "仅供组件契约验证，非客户业务数据。",
    publishedAt: "2026-09-09T09:00:00Z",
    collectedAt: "2026-09-09T10:00:00Z",
    assessment,
    ...patch,
  };
}
function page(
  items: Candidate[],
  total = items.length,
  pageNumber = 1,
): CandidatePage {
  return { items, total, page: pageNumber, pageSize: 10 };
}
function mount(overrides: Partial<YikeService> = {}, path = "/candidates") {
  window.history.replaceState(null, "", "#" + path);
  const service = {
    ...baseService,
    session: vi.fn().mockResolvedValue({
      authenticated: true,
      userId: "candidate-contract-user",
    }),
    profiles: vi.fn().mockResolvedValue([confirmed]),
    candidates: vi.fn().mockResolvedValue(page([candidate()])),
    ...overrides,
  };
  render(
    <AppProvider service={service}>
      <CandidatesPage />
    </AppProvider>,
  );
  return service;
}
async function ready() {
  await screen.findByRole("button", { name: "查看候选契约测试需求" });
  await waitFor(() => expect(screen.queryByText("正在加载…")).toBeNull());
}
function openImport() {
  fireEvent.click(screen.getByRole("button", { name: "确认入库" }));
  return screen.getByRole("dialog", { name: "确认候选入库" });
}
function sendConfirmed(dialog: HTMLElement) {
  fireEvent.click(within(dialog).getByRole("checkbox"));
  fireEvent.click(within(dialog).getByRole("button", { name: "确认入库" }));
}
function decision(
  request: CandidateReview,
  row = candidate(),
  outcome: "IMPORTED" | "ALREADY_IMPORTED" | "EXCLUDED" = "IMPORTED",
): CandidateReviewResult {
  if (request.action === "ASSESS") throw new Error("Test expected a decision");
  const receipt: CandidateReceipt = {
    requestId: request.requestId,
    action: request.action,
    status: "SUCCEEDED",
    outcome,
    reviewedBy: "server-test-reviewer",
    reviewedAt: "2026-09-09T10:05:00Z",
    opportunityId: outcome === "EXCLUDED" ? undefined : "opportunity-test-1",
    review: reviewSnapshot(request),
  };
  return {
    kind: "decision",
    requestId: request.requestId,
    candidate: {
      ...row,
      status:
        outcome === "EXCLUDED"
          ? "EXCLUDED"
          : outcome === "ALREADY_IMPORTED"
            ? "DUPLICATE"
            : "IMPORTED",
      opportunityId: receipt.opportunityId,
      lastReview: receipt,
    },
    receipt,
  };
}

describe("原始候选 P07", () => {
  it("默认适配器仍明确不可用，不制造客户候选或复核结果", async () => {
    await expect(baseService.candidates()).rejects.toMatchObject({
      code: "CAPABILITY_UNAVAILABLE",
    });
    await expect(
      baseService.reviewCandidate({
        action: "ASSESS",
        candidateId: "test",
        candidateRevision: 1,
        sourceVersionId: "source-test",
        profileId: "profile-test",
        profileVersion: 1,
        requestId: "request-test",
      }),
    ).rejects.toMatchObject({ code: "CAPABILITY_UNAVAILABLE" });
  });
  it("筛选与分页传服务端契约，条件变化回到第一页", async () => {
    const load = vi
      .fn()
      .mockImplementation(async (query) =>
        page(
          [candidate({ id: "candidate-" + query?.page })],
          21,
          query?.page || 1,
        ),
      );
    mount({ candidates: load });
    await ready();
    fireEvent.click(screen.getByRole("button", { name: "下一页" }));
    await waitFor(() =>
      expect(load).toHaveBeenLastCalledWith(
        expect.objectContaining({ page: 2, pageSize: 10 }),
      ),
    );
    await screen.findByText("2 / 3");
    fireEvent.change(screen.getByRole("combobox", { name: "候选来源筛选" }), {
      target: { value: "抖音" },
    });
    await waitFor(() =>
      expect(load).toHaveBeenLastCalledWith(
        expect.objectContaining({ platform: "抖音", page: 1 }),
      ),
    );
    fireEvent.change(screen.getByRole("textbox", { name: "搜索原始线索" }), {
      target: { value: "  展区  " },
    });
    await waitFor(() =>
      expect(load).toHaveBeenLastCalledWith(
        expect.objectContaining({ query: "展区", page: 1 }),
      ),
    );
  });
  it("公开样例完全只读，客户接口夹带样例也被阻止", async () => {
    const service = mount(
      { reviewCandidate: vi.fn() },
      "/candidates?scope=sample",
    );
    await screen.findByText("公开样例只供查看，不能确认入库或排除客户线索。");
    expect(
      (screen.getByRole("button", { name: "确认入库" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    expect(service.candidates).not.toHaveBeenCalled();
    expect(service.reviewCandidate).not.toHaveBeenCalled();
    cleanup();
    mount({
      candidates: vi
        .fn()
        .mockResolvedValue(page([candidate({ sample: true })])),
    });
    await screen.findByText("服务返回了公开样例，已阻止其进入客户候选列表。");
    expect(
      screen.queryByRole("button", { name: "查看候选契约测试需求" }),
    ).toBeNull();
  });
  it("仅已确认画像可绑定，过期判断结果不可用于入库", async () => {
    const review = vi
      .fn()
      .mockImplementation(async (request: CandidateReview) => ({
        kind: "assessment",
        requestId: request.requestId,
        candidateId: request.candidateId,
        assessment: { ...assessment, sourceVersionId: "obsolete-source" },
      }));
    mount({
      candidates: vi
        .fn()
        .mockResolvedValue(page([candidate({ assessment: undefined })])),
      profiles: vi
        .fn()
        .mockResolvedValue([
          confirmed,
          { ...confirmed, id: "draft", version: 2, status: "DRAFT" },
        ]),
      reviewCandidate: review,
    });
    await ready();
    const select = screen.getByRole("combobox", { name: "候选目标业务画像" });
    expect(within(select).queryByText("版本 2 · 展区设计")).toBeNull();
    fireEvent.change(select, { target: { value: confirmed.id } });
    await screen.findByText("判断结果与当前画像或来源不一致，请重新判断。");
    expect(review).toHaveBeenCalledWith(
      expect.objectContaining({
        action: "ASSESS",
        candidateRevision: 2,
        sourceVersionId: "source-v2",
        profileId: "profile-1",
        profileVersion: 1,
      }),
    );
    expect(
      (screen.getByRole("button", { name: "确认入库" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
  });
  it("重新判断保护人工编辑，判断失败保留修改内容", async () => {
    const review = vi
      .fn()
      .mockRejectedValue(new ServiceError("FAILED", "判断暂不可用", 503));
    mount({ reviewCandidate: review });
    await ready();
    fireEvent.change(screen.getByRole("textbox", { name: "候选匹配理由" }), {
      target: { value: "人工重新核实后的理由" },
    });
    fireEvent.click(screen.getByRole("button", { name: "按画像重新判断" }));
    let dialog = screen.getByRole("dialog", {
      name: "重新判断并替换人工修改？",
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "取消" }));
    expect(review).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "按画像重新判断" }));
    dialog = screen.getByRole("dialog", { name: "重新判断并替换人工修改？" });
    fireEvent.click(within(dialog).getByRole("button", { name: "重新判断" }));
    await screen.findByText("判断暂不可用");
    expect(
      (
        screen.getByRole("textbox", {
          name: "候选匹配理由",
        }) as HTMLTextAreaElement
      ).value,
    ).toBe("人工重新核实后的理由");
  });
  it("绑定后采用服务返回的五项判断，尚未产生入库操作", async () => {
    const review = vi
      .fn()
      .mockImplementation(async (request: CandidateReview) => ({
        kind: "assessment",
        requestId: request.requestId,
        candidateId: request.candidateId,
        assessment,
      }));
    mount({
      candidates: vi
        .fn()
        .mockResolvedValue(page([candidate({ assessment: undefined })])),
      reviewCandidate: review,
    });
    await ready();
    fireEvent.change(
      screen.getByRole("combobox", { name: "候选目标业务画像" }),
      { target: { value: confirmed.id } },
    );
    await screen.findByRole("textbox", { name: "候选匹配理由" });
    expect(
      (screen.getByRole("textbox", { name: "候选风险" }) as HTMLTextAreaElement)
        .value,
    ).toBe(assessment.evidence.risk);
    expect(
      (screen.getByRole("button", { name: "确认入库" }) as HTMLButtonElement)
        .disabled,
    ).toBe(false);
    expect(review.mock.calls.map((call) => call[0].action)).toEqual(["ASSESS"]);
    expect(screen.queryByText("已确认入库。")).toBeNull();
  });
  it.each(["EXPIRED", "BLOCKED", "UNVERIFIED"] as const)(
    "来源 %s 阻止入库，打开原文不会解除门禁",
    async (sourceStatus) => {
      const openExternal = vi.fn().mockResolvedValue(undefined);
      mount({
        candidates: vi
          .fn()
          .mockResolvedValue(page([candidate({ sourceStatus })])),
        openExternal,
      });
      await ready();
      fireEvent.click(screen.getByRole("button", { name: /查看原文/ }));
      await waitFor(() =>
        expect(openExternal).toHaveBeenCalledWith(
          "https://example.com/inquiry",
        ),
      );
      expect(
        (screen.getByRole("button", { name: "确认入库" }) as HTMLButtonElement)
          .disabled,
      ).toBe(true);
    },
  );
  it("空证据阻止入库；确认快照绑定版本、人工依据并只提交一次", async () => {
    let resolve!: (value: CandidateReviewResult) => void;
    const review = vi.fn().mockImplementation(
      () =>
        new Promise<CandidateReviewResult>((yes) => {
          resolve = yes;
        }),
    );
    mount({ reviewCandidate: review });
    await ready();
    fireEvent.change(screen.getByRole("textbox", { name: "候选匹配理由" }), {
      target: { value: "" },
    });
    expect(
      (screen.getByRole("button", { name: "确认入库" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    fireEvent.change(screen.getByRole("textbox", { name: "候选匹配理由" }), {
      target: { value: "人工核实的匹配依据" },
    });
    const dialog = openImport();
    expect(
      (
        within(dialog).getByRole("button", {
          name: "确认入库",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
    sendConfirmed(dialog);
    fireEvent.click(within(dialog).getByRole("button", { name: "确认入库" }));
    await waitFor(() => expect(review).toHaveBeenCalledTimes(1));
    const request = review.mock.calls[0][0] as CandidateReview;
    expect(request).toMatchObject({
      action: "INCLUDE",
      candidateId: "candidate-1",
      candidateRevision: 2,
      sourceVersionId: "source-v2",
      profileId: "profile-1",
      profileVersion: 1,
      assessmentId: "assessment-1",
      humanConfirmed: true,
      evidence: { matchReason: "人工核实的匹配依据" },
    });
    expect(request).not.toHaveProperty("tenantId");
    expect(request).not.toHaveProperty("reviewedBy");
    expect(request).not.toHaveProperty("reviewedAt");
    resolve(decision(request));
    await screen.findByText("已确认入库。");
    expect(
      screen.queryByRole("button", { name: "查看候选契约测试需求" }),
    ).toBeNull();
  });
  it("超时结果保留同一请求，仅核对确定回执后解除保护", async () => {
    const review = vi
      .fn()
      .mockRejectedValue(new ServiceError("NETWORK", "连接中断", 0));
    const load = vi.fn().mockImplementation(async (query) => {
      if (query?.reviewRequestId) {
        const request = review.mock.calls[0][0] as CandidateReview;
        const result = decision(request);
        if (result.kind === "decision") return page([result.candidate]);
      }
      return page([candidate()]);
    });
    mount({ reviewCandidate: review, candidates: load });
    await ready();
    sendConfirmed(openImport());
    await screen.findByText(
      "本次复核结果尚未确定，已保留请求记录；核对前不会再次提交。",
    );
    expect(
      (screen.getByRole("button", { name: "确认入库" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "核对本次结果" }));
    await screen.findByText("已确认入库。");
    expect(review).toHaveBeenCalledTimes(1);
    expect(load).toHaveBeenLastCalledWith({
      ids: ["candidate-1"],
      reviewRequestId: review.mock.calls[0][0].requestId,
      page: 1,
      pageSize: 1,
    });
  });
  it("不接受行状态与成功回执矛盾的结果，不显示假成功", async () => {
    const review = vi
      .fn()
      .mockImplementation(async (request: CandidateReview) => {
        const result = decision(request);
        return result.kind === "decision"
          ? {
              ...result,
              candidate: { ...result.candidate, status: "PENDING_REVIEW" },
            }
          : result;
      });
    mount({ reviewCandidate: review });
    await ready();
    sendConfirmed(openImport());
    await screen.findByText("服务结果尚不能确认，请核对本次复核。");
    expect(screen.queryByText("已确认入库。")).toBeNull();
    expect(
      (screen.getByRole("button", { name: "确认入库" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
  });
  it("服务回执不能悄悄改写用户确认的复核依据", async () => {
    const review = vi
      .fn()
      .mockImplementation(async (request: CandidateReview) => {
        const result = decision(request);
        if (result.kind !== "decision") return result;
        return {
          ...result,
          receipt: {
            ...result.receipt,
            review: {
              ...result.receipt.review!,
              evidence: {
                ...result.receipt.review!.evidence,
                risk: "不一致的风险",
              },
            },
          },
        };
      });
    mount({ reviewCandidate: review });
    await ready();
    sendConfirmed(openImport());
    await screen.findByText("服务结果尚不能确认，请核对本次复核。");
    expect(screen.queryByText("已确认入库。")).toBeNull();
    expect(screen.getByRole("button", { name: "核对本次结果" })).toBeTruthy();
  });
  it("确定拒绝保留手动证据，用户可核对后再次确认", async () => {
    const review = vi
      .fn()
      .mockRejectedValue(
        new ServiceError("REVIEW_REJECTED", "复核条件已变化", 409),
      );
    mount({ reviewCandidate: review });
    await ready();
    fireEvent.change(screen.getByRole("textbox", { name: "候选风险" }), {
      target: { value: "人工确认的风险" },
    });
    sendConfirmed(openImport());
    await screen.findByText("复核条件已变化");
    expect(
      (screen.getByRole("textbox", { name: "候选风险" }) as HTMLTextAreaElement)
        .value,
    ).toBe("人工确认的风险");
    expect(screen.queryByRole("button", { name: "核对本次结果" })).toBeNull();
    expect(
      (screen.getByRole("button", { name: "确认入库" }) as HTMLButtonElement)
        .disabled,
    ).toBe(false);
    expect(review).toHaveBeenCalledTimes(1);
  });
  it("重复来源回执展示已有商机，不宣称新建；排除要求人工原因", async () => {
    const review = vi
      .fn()
      .mockImplementation(async (request: CandidateReview) =>
        decision(request, candidate(), "ALREADY_IMPORTED"),
      );
    mount({ reviewCandidate: review });
    await ready();
    sendConfirmed(openImport());
    await screen.findByText("该来源已入库，未重复创建商机。");
    expect(screen.getByRole("button", { name: "查看商机" })).toBeTruthy();
    cleanup();
    const exclude = vi
      .fn()
      .mockImplementation(async (request: CandidateReview) =>
        decision(request, candidate(), "EXCLUDED"),
      );
    mount({ reviewCandidate: exclude });
    await ready();
    fireEvent.click(screen.getByRole("button", { name: "排除" }));
    const dialog = screen.getByRole("dialog", { name: "确认排除候选" });
    fireEvent.click(within(dialog).getByRole("checkbox"));
    expect(
      (
        within(dialog).getByRole("button", {
          name: "确认排除",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
    fireEvent.change(
      within(dialog).getByRole("textbox", { name: "候选排除原因" }),
      { target: { value: "服务地区不符合已确认能力" } },
    );
    fireEvent.click(within(dialog).getByRole("button", { name: "确认排除" }));
    await screen.findByText("候选已排除。");
    expect(exclude).toHaveBeenCalledWith(
      expect.objectContaining({
        action: "EXCLUDE",
        reason: "服务地区不符合已确认能力",
        humanConfirmed: true,
      }),
    );
  });
  it("批量复核逐项展示，第一项未知即停止其余提交", async () => {
    const review = vi
      .fn()
      .mockRejectedValue(new ServiceError("NETWORK", "连接中断", 0));
    mount({
      reviewCandidate: review,
      candidates: vi
        .fn()
        .mockResolvedValue(
          page([
            candidate(),
            candidate({ id: "candidate-2", title: "第二条测试需求" }),
          ]),
        ),
    });
    await ready();
    fireEvent.click(
      screen.getByRole("checkbox", { name: "选择本页待复核候选" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "批量确认入库（2）" }));
    const dialog = screen.getByRole("dialog", { name: "批量确认 2 条入库" });
    expect(within(dialog).getByText("契约测试需求")).toBeTruthy();
    expect(within(dialog).getByText("第二条测试需求")).toBeTruthy();
    sendConfirmed(dialog);
    await screen.findByText("连接中断 本批已完成 0 条，其余未继续提交。");
    expect(review).toHaveBeenCalledTimes(1);
  });
});

const candidateLedgerKey = operationLedgerKey(
  "candidate-reviews",
  "candidate-contract-user",
);
function storedCandidateReviews() {
  return JSON.parse(localStorage.getItem(candidateLedgerKey) || "{}") as Record<
    string,
    string
  >;
}
async function unknownReview() {
  const review = vi
    .fn()
    .mockRejectedValue(new ServiceError("NETWORK", "TEST 结果未知", 0));
  mount({ reviewCandidate: review });
  await ready();
  sendConfirmed(openImport());
  await screen.findByText("TEST 结果未知");
  return { review, request: review.mock.calls[0][0] as CandidateReview };
}
describe("P07 durable original review reconciliation", () => {
  it("retains the original request after clearing drafts and remounting, and only queries that request", async () => {
    const { request } = await unknownReview();
    const stored = Object.entries(storedCandidateReviews());
    expect(stored).toHaveLength(1);
    expect(stored[0][1]).toBe("PENDING");
    expect(stored[0][0]).toContain(request.requestId);
    expect(JSON.stringify(stored)).not.toContain("测试服务与公开需求匹配");
    cleanup();
    clearLocalDrafts();
    const review = vi.fn();
    const load = vi.fn().mockImplementation(async (query) => {
      if (query?.reviewRequestId) {
        const result = decision(request);
        if (result.kind === "decision") return page([result.candidate]);
      }
      return page([candidate()]);
    });
    mount({ reviewCandidate: review, candidates: load });
    await ready();
    expect(
      (screen.getByRole("button", { name: "确认入库" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "核对本次结果" }));
    await screen.findByText("已确认入库。");
    expect(review).not.toHaveBeenCalled();
    expect(load).toHaveBeenLastCalledWith({
      ids: ["candidate-1"],
      reviewRequestId: request.requestId,
      page: 1,
      pageSize: 1,
    });
    expect(storedCandidateReviews()).toEqual({});
  });
  it("keeps recovery reachable when the original candidate is absent from the current list", async () => {
    const { request } = await unknownReview();
    cleanup();
    const load = vi.fn().mockImplementation(async (query) => {
      if (query?.reviewRequestId) {
        const result = decision(request);
        if (result.kind === "decision") return page([result.candidate]);
      }
      return page([]);
    });
    const review = vi.fn();
    mount({ candidates: load, reviewCandidate: review });
    const recover = await screen.findByRole("button", {
      name: "核对原复核结果",
    });
    fireEvent.click(recover);
    await screen.findByText("已确认入库。");
    expect(review).not.toHaveBeenCalled();
    expect(storedCandidateReviews()).toEqual({});
  });
  it("does not unlock a failed receipt with changed confirmation words; exact failure can be retried manually", async () => {
    const { request } = await unknownReview();
    cleanup();
    const result = decision(request);
    if (result.kind !== "decision") throw new Error("fixture");
    let mismatch = true;
    const review = vi.fn();
    const load = vi
      .fn()
      .mockImplementation(async (query) =>
        query?.reviewRequestId
          ? page([
              candidate({
                lastReview: {
                  ...result.receipt,
                  status: "FAILED",
                  outcome: undefined,
                  opportunityId: undefined,
                  review: mismatch
                    ? {
                        ...result.receipt.review!,
                        reason: "TEST different confirmation",
                      }
                    : result.receipt.review,
                },
              }),
            ])
          : page([candidate()]),
      );
    mount({ reviewCandidate: review, candidates: load });
    await ready();
    fireEvent.click(screen.getByRole("button", { name: "核对本次结果" }));
    await screen.findByText("尚未获得本次复核的确定结果，请稍后再次核对。");
    expect(Object.keys(storedCandidateReviews())).toHaveLength(1);
    expect(
      (screen.getByRole("button", { name: "确认入库" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    mismatch = false;
    fireEvent.click(screen.getByRole("button", { name: "核对本次结果" }));
    await screen.findByText(
      "服务端确认本次复核失败，当前信息已保留，可检查后重新提交。",
    );
    expect(storedCandidateReviews()).toEqual({});
    expect(
      (screen.getByRole("button", { name: "确认入库" }) as HTMLButtonElement)
        .disabled,
    ).toBe(false);
    expect(review).not.toHaveBeenCalled();
  });
  it("isolates durable records by user and does not unlock on a generic 4xx response", async () => {
    const review = vi
      .fn()
      .mockRejectedValue(new ServiceError("UPSTREAM", "TEST 网关400", 400));
    mount({ reviewCandidate: review });
    await ready();
    sendConfirmed(openImport());
    await screen.findByText("TEST 网关400");
    expect(Object.keys(storedCandidateReviews())).toHaveLength(1);
    cleanup();
    mount({
      session: vi
        .fn()
        .mockResolvedValue({
          authenticated: true,
          userId: "TEST-another-user",
        }),
    });
    await ready();
    expect(screen.queryByRole("button", { name: "核对本次结果" })).toBeNull();
    expect(
      (screen.getByRole("button", { name: "确认入库" }) as HTMLButtonElement)
        .disabled,
    ).toBe(false);
    expect(Object.keys(storedCandidateReviews())).toHaveLength(1);
  });
  it("does not dispatch when durable storage fails", async () => {
    const setItem = Storage.prototype.setItem;
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(function (
      this: Storage,
      key,
      value,
    ) {
      if (key === candidateLedgerKey)
        throw new Error("TEST storage unavailable");
      return setItem.call(this, key, value);
    });
    const review = vi.fn();
    mount({ reviewCandidate: review });
    await ready();
    sendConfirmed(openImport());
    await screen.findByText(
      "操作确认记录暂时无法可靠保存，请检查本机存储并核对平台记录后重试。",
    );
    expect(review).not.toHaveBeenCalled();
  });
  it("does not dispatch after leaving while the confirmation fingerprint is being prepared", async () => {
    let finish!: (value: ArrayBuffer) => void;
    vi.spyOn(crypto.subtle, "digest").mockImplementation(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    const review = vi.fn();
    mount({ reviewCandidate: review });
    await ready();
    sendConfirmed(openImport());
    await waitFor(() => expect(finish).toBeTypeOf("function"));
    cleanup();
    await act(async () => {
      finish(new Uint8Array(32).buffer);
    });
    expect(review).not.toHaveBeenCalled();
    expect(storedCandidateReviews()).toEqual({});
  });
  it("rechecks the durable candidate lock immediately after hashing instead of trusting render-time state", async () => {
    let finish!: (value: ArrayBuffer) => void;
    vi.spyOn(crypto.subtle, "digest").mockImplementation(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    const review = vi.fn();
    mount({ reviewCandidate: review });
    await ready();
    sendConfirmed(openImport());
    await waitFor(() => expect(finish).toBeTypeOf("function"));
    const key = JSON.stringify([
      "candidate-1",
      "INCLUDE",
      "TEST-other-request",
      "a".repeat(64),
    ]);
    localStorage.setItem(
      candidateLedgerKey,
      JSON.stringify({ [key]: "PENDING" }),
    );
    await act(async () => {
      finish(new Uint8Array(32).buffer);
    });
    await screen.findByText("上次复核结果尚未核对，未再次提交。");
    expect(review).not.toHaveBeenCalled();
    expect(storedCandidateReviews()).toEqual({ [key]: "PENDING" });
  });
});

it("P07 actual timeout survives leaving and clearing drafts, with no new mutation on re-entry", async () => {
  const review = vi.fn().mockImplementation(() => new Promise(() => {}));
  mount({ reviewCandidate: review });
  await ready();
  vi.useFakeTimers();
  vi.spyOn(crypto.subtle, "digest").mockResolvedValue(
    new Uint8Array(32).buffer,
  );
  sendConfirmed(openImport());
  await act(async () => {
    await vi.advanceTimersByTimeAsync(20001);
  });
  expect(screen.getByText("请求已超时，请核对结果后再继续。")).toBeTruthy();
  const original = review.mock.calls[0][0] as CandidateReview;
  cleanup();
  clearLocalDrafts();
  vi.useRealTimers();
  const restartedReview = vi.fn();
  const load = vi.fn().mockResolvedValue(page([candidate()]));
  mount({ reviewCandidate: restartedReview, candidates: load });
  await ready();
  expect(
    (screen.getByRole("button", { name: "确认入库" }) as HTMLButtonElement)
      .disabled,
  ).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "核对本次结果" }));
  await screen.findByText("尚未获得本次复核的确定结果，请稍后再次核对。");
  expect(load).toHaveBeenLastCalledWith({
    ids: ["candidate-1"],
    reviewRequestId: original.requestId,
    page: 1,
    pageSize: 1,
  });
  expect(restartedReview).not.toHaveBeenCalled();
  expect(Object.keys(storedCandidateReviews())).toHaveLength(1);
});
it("P07 refuses dispatch with a corrupt stored request fingerprint", async () => {
  const key = JSON.stringify([
    "candidate-1",
    "INCLUDE",
    "TEST-older-request",
    "not-a-hash",
  ]);
  const review = vi.fn();
  mount({ reviewCandidate: review });
  await ready();
  localStorage.setItem(
    candidateLedgerKey,
    JSON.stringify({ [key]: "PENDING" }),
  );
  sendConfirmed(openImport());
  await screen.findByText(
    "操作确认记录暂时无法可靠保存，请检查本机存储并核对平台记录后重试。",
  );
  expect(review).not.toHaveBeenCalled();
  expect(storedCandidateReviews()).toEqual({ [key]: "PENDING" });
});
