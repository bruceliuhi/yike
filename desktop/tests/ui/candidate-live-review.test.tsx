// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { AppProvider } from "../../src/renderer/app/context";
import { CandidatesPage } from "../../src/renderer/pages/Opportunities";
import { service as base } from "../../src/renderer/services/client";
import { createCandidateReviewService } from "../../src/renderer/services/candidateReview";
import {
  candidateFixture,
  candidateBinding,
  assessmentFixture,
  verificationFixture,
  verificationId,
  opportunityId,
} from "../fixtures/candidateReviewApi";
import type { Candidate } from "../../src/renderer/domain/candidates";
import { rawEvidenceFixture } from "../fixtures/rawCandidateEvidence";

afterEach(() => {
  cleanup();
  localStorage.clear();
  vi.restoreAllMocks();
  Reflect.deleteProperty(window,'yikeDesktop');
  window.history.replaceState(null, "", "/");
});
function mount(
  options: {
    assessed?: boolean;
    published?: boolean;
    historical?: boolean;
    loseDecision?: boolean;
    assessmentGate?: Promise<void>;
    verificationGate?: Promise<void>;
    decisionGate?: Promise<void>;
    rawError?: boolean;
    verified?: boolean;
    assessmentUnknown?: boolean;
    wrongStrategy?: boolean;
    dynamic?: boolean;
    xhs?: boolean;
  } = {},
) {
  vi.spyOn(Date, "now").mockReturnValue(Date.parse("2026-09-10T03:00:00Z"));
  const raw = rawEvidenceFixture();
  if(options.xhs)raw.candidate.platform=raw.observations.items[0].platform='XIAOHONGSHU';
  if (options.dynamic) {
    Object.assign(raw.candidate, {kind:"PAGE",external_source_id:null,external_comment_id:null});
    const content = { ...raw.candidate.current_version, parent:null,author_public_id:null,
      body:"TEST采购人 2026年9月10日 需要设备报价" };
    raw.candidate.current_version = content;
    const {version_id:_id,content_version:_version,...stored} = content;
    Object.assign(raw.observations.items[0], {content:stored,
      normalizer_version:"dynamic-public-read-v1",collector_version:"public-web-agent-v1"});
  }
  if (options.published) {
    raw.candidate.current_version.published_at = "2026-09-09T01:00:00Z";
    raw.observations.items[0].content.published_at =
      raw.candidate.current_version.published_at;
  }
  const row: Candidate = {
    ...candidateFixture(),
    ...(options.xhs?{platform:'XIAOHONGSHU',sourceLabel:'XIAOHONGSHU'}:{}),
    status: "PENDING_REVIEW",
    sourceStatus: "UNVERIFIED",
    url: raw.candidate.current_version.public_url,
    excerpt: raw.candidate.current_version.body,
    publishedAt: raw.candidate.current_version.published_at ?? "",
    historical: options.historical ?? false,
    ...(options.assessed
      ? { assessment: assessmentFixture() as Candidate["assessment"] }
      : {}),
    ...(options.verified
      ? {
          sourceVerification:
            verificationFixture() as Candidate["sourceVerification"],
          sourceStatus: "OPEN" as const,
        }
      : {}),
  };
  const receipts = new Map<string, unknown>();
  const transport = vi.fn(
    async (operation: string, _path: string, _method: string, input: any) => {
      if (operation === "candidates.list")
        return {
          items: input?.query === "nothing" ? [] : [row],
          total: input?.query === "nothing" ? 0 : 1,
          page: 1,
          pageSize: 10,
        };
      if (operation === "candidates.rawEvidence") {
        if (options.rawError) throw new Error("TEST stale raw");
        return raw;
      }
      if (operation === "candidates.request")
        return receipts.get(decodeURIComponent(_path.split("?")[0].split("/").pop()!));
      expect(
        localStorage.getItem(
          "yike.ui.operation.v1.candidate-request-operations.TEST-live-user",
        ),
      ).toContain(input.requestId);
      if (operation === "candidates.verifySource") {
        const result = {
          ...verificationFixture(),
          requestId: input.requestId,
          status: input.status,
          openingMethod: input.openingMethod,
          locator: input.locator,
          excerpt: input.excerpt,
          contactMethod: input.contactMethod,
          ...(input.demandEvidence ? {demandEvidence: input.demandEvidence} : {}),
        };
        receipts.set(input.requestId, result);
        Object.assign(row, {
          sourceVerification: result,
          sourceStatus: result.status,
        });
        await options.verificationGate;
        return result;
      }
      if (input.action === "ASSESS") {
        await options.assessmentGate;
        if (options.assessmentUnknown) {
          const result = {
            kind: "pending",
            requestId: input.requestId,
            candidateId: row.id,
            status: "UNKNOWN",
            code: "assessment_unknown",
          };
          receipts.set(input.requestId, result);
          return result;
        }
        const result = {
          kind: "assessment",
          requestId: input.requestId,
          candidateId: row.id,
          assessment: {
            ...assessmentFixture(),
            ...(row.sourceVerification?.demandEvidence ? {demandEvidenceId:row.sourceVerification.id} : {}),
            ...(options.wrongStrategy
              ? { strategyVersionId: "99999999-9999-4999-8999-999999999999" }
              : {}),
          },
        };
        receipts.set(input.requestId, result);
        Object.assign(row, { assessment: result.assessment });
        return result;
      }
      const {
        requestId,
        action,
        candidateId: _id,
        humanConfirmed: _human,
        ...review
      } = input;
      const receipt = {
        requestId,
        action,
        status: "SUCCEEDED",
        outcome: action === "EXCLUDE" ? "EXCLUDED" : "IMPORTED",
        reviewedBy: "TEST-live-user",
        reviewedAt: "2026-09-10T03:00:00Z",
        review,
        ...(action === "INCLUDE" ? { opportunityId } : {}),
      };
      Object.assign(row, {
        status: receipt.outcome,
        lastReview: receipt,
        ...(action === "INCLUDE" ? { opportunityId } : {}),
      });
      const result = {
        kind: "decision",
        requestId,
        candidate: structuredClone(row),
        receipt,
      };
      receipts.set(requestId, result);
      await options.decisionGate;
      if (options.loseDecision) throw new Error("TEST response lost");
      return result;
    },
  );
  const api = createCandidateReviewService(transport);
  if(options.xhs)Object.defineProperty(window,'yikeDesktop',{configurable:true,value:{
    requestApi:async(input:{operation:string;payload:unknown})=>({ok:true,status:200,data:await transport(input.operation,'/candidates','GET',input.payload)}),
  }});
  const service = {
    ...base,
    candidateReview: api,
    rawCandidateEvidence: api.getRawEvidence,
    candidates: options.xhs?base.candidates:api.list,
    session: vi
      .fn()
      .mockResolvedValue({ authenticated: true, userId: "TEST-live-user" }),
    profiles: vi.fn().mockResolvedValue(
      [candidateBinding.profileId, "88888888-8888-4888-8888-888888888888"].map(
        (id) => ({
          id,
          version: 3,
          status: "CONFIRMED",
          description: "TEST",
          fields: {
            service: "TEST采购",
            customer: "企业",
            regions: "全国",
            preference: "",
            exclusions: "",
          },
        }),
      ),
    ),
    reviewCandidate: vi.fn(),
    openExternal: vi.fn().mockResolvedValue(undefined),
    openSourceView:vi.fn().mockResolvedValue({state:'OPENED' as const,sourceKind:'COMMENT' as const}),
  };
  window.history.replaceState(null, "", "#/candidates");
  render(
    <AppProvider service={service}>
      <CandidatesPage />
    </AppProvider>,
  );
  return { transport, service, row, raw };
}
async function ready() {
  await screen.findByRole("combobox", { name: "候选目标业务画像" });
}

it('opens XHS in the bound source viewer and labels a parent-only comment view',async()=>{
  const {service,transport,row}=mount({xhs:true});await ready();
  fireEvent.click(screen.getByRole('button',{name:/查看原文/}));
  await waitFor(()=>expect(service.openSourceView).toHaveBeenCalledWith({candidateId:row.id,candidateRevision:row.revision,sourceVersionId:row.sourceVersionId,profileId:row.profileId,strategyVersionId:row.strategyVersionId}));
  expect(await screen.findByText('已打开所属原帖，未定位该评论')).toBeTruthy();
  expect(service.openExternal).not.toHaveBeenCalled();
  expect(transport.mock.calls.filter(call=>call[2]==='POST')).toHaveLength(0);
});

it("selects the bound profile and reads full original evidence without an implicit model call", async () => {
  const { transport, raw } = mount();
  await ready();
  expect(screen.queryByText(/发送给配置的模型/)).toBeNull();
  expect(
    (
      screen.getByRole("combobox", {
        name: "候选目标业务画像",
      }) as HTMLSelectElement
    ).value,
  ).toBe(candidateBinding.profileId);
  await waitFor(() =>
    expect(document.body.textContent).toContain(
      raw.candidate.current_version.body,
    ),
  );
  expect(document.querySelector("script")).toBeNull();
  expect(
    transport.mock.calls.filter((call) => call[2] === "POST"),
  ).toHaveLength(0);
  expect(
    (screen.getByRole("button", { name: "确认入库" }) as HTMLButtonElement)
      .disabled,
  ).toBe(true);
});

it("changing a profile only edits selection; explicit judgment persists before POST", async () => {
  const { transport, service } = mount();
  await ready();
  fireEvent.change(screen.getByRole("combobox", { name: "候选目标业务画像" }), {
    target: { value: "88888888-8888-4888-8888-888888888888" },
  });
  await new Promise((resolve) => setTimeout(resolve, 0));
  expect(service.reviewCandidate).not.toHaveBeenCalled();
  expect(
    transport.mock.calls.filter((call) => call[2] === "POST"),
  ).toHaveLength(0);
  fireEvent.change(screen.getByRole("combobox", { name: "候选目标业务画像" }), {
    target: { value: candidateBinding.profileId },
  });
  fireEvent.click(screen.getByRole("button", { name: /按画像.*判断/ }));
  await waitFor(() =>
    expect(
      transport.mock.calls.filter((call) => call[2] === "POST"),
    ).toHaveLength(1),
  );
  await screen.findByText("您希望什么时候完成采购？");
  expect(service.reviewCandidate).not.toHaveBeenCalled();
});

it("opening the original URL does not create a human verification", async () => {
  const { transport, service } = mount();
  await ready();
  fireEvent.click(screen.getByRole("button", { name: /查看原文/ }));
  await waitFor(() => expect(service.openExternal).toHaveBeenCalledTimes(1));
  expect(
    transport.mock.calls.filter((call) => call[2] === "POST"),
  ).toHaveLength(0);
  expect(
    (screen.getByRole("button", { name: "保存来源核验" }) as HTMLButtonElement)
      .disabled,
  ).toBe(true);
});

async function verify(waitForReceipt = true) {
  const form = screen.getByRole("region", { name: "人工来源核验" });
  fireEvent.change(within(form).getByRole("combobox", { name: "来源状态" }), {
    target: { value: "OPEN" },
  });
  fireEvent.change(within(form).getByRole("combobox", { name: "联系路径" }), {
    target: { value: "COMMENT" },
  });
  fireEvent.change(within(form).getByRole("textbox", { name: "定位描述" }), {
    target: { value: "https://example.com/posts/TEST-1#comment-2" },
  });
  fireEvent.change(
    within(form).getByRole("textbox", { name: "原文逐字摘录" }),
    { target: { value: "评论原文" } },
  );
  fireEvent.click(within(form).getByRole("checkbox"));
  fireEvent.click(within(form).getByRole("button", { name: "保存来源核验" }));
  if (waitForReceipt) await within(form).findByText("当前版本核验记录");
}

it("requires human source verification then snapshots its ID before a confirmed include", async () => {
  const { transport } = mount({ assessed: true, published: true });
  await ready();
  expect(
    (screen.getByRole("button", { name: "确认入库" }) as HTMLButtonElement)
      .disabled,
  ).toBe(true);
  await verify();
  fireEvent.click(screen.getByRole("button", { name: "确认入库" }));
  const dialog = screen.getByRole("dialog", { name: "确认候选入库" });
  expect(dialog.textContent).not.toContain(verificationId);
  fireEvent.click(within(dialog).getByRole("checkbox"));
  fireEvent.click(within(dialog).getByRole("button", { name: "确认入库" }));
  await screen.findByText("已确认入库。");
  expect(
    transport.mock.calls
      .filter((c) => c[2] === "POST")
      .map((c) => c[3].sourceVerificationId),
  ).toEqual([undefined, verificationId]);
  expect(screen.getByRole("button", { name: "查看商机" })).toBeTruthy();
});

it("a valid OPEN verification does not invent an unknown original publication date", async () => {
  mount({ assessed: true });
  await ready();
  await verify();
  expect(
    (screen.getByRole("button", { name: "确认入库" }) as HTMLButtonElement)
      .disabled,
  ).toBe(true);
  expect(document.body.textContent).toContain("本人发布时间未知");
});

it("dynamic page proof enables inclusion only after an explicit new assessment", async () => {
  const {transport} = mount({assessed:true,dynamic:true});
  await ready();
  const form = screen.getByRole("region", {name:"人工来源核验"});
  fireEvent.change(within(form).getByLabelText("来源状态"),{target:{value:"OPEN"}});
  fireEvent.click(await within(form).findByRole("checkbox",{name:"确认需求发言人和时间"}));
  for (const [name,value] of Object.entries({"定位描述":"原网页TEST第2楼", "原文逐字摘录":"需要设备报价",
    "需求作者定位":"TEST第2楼", "原文作者标记":"TEST采购人", "本人需求摘录":"需要设备报价",
    "需求日期":"2026-09-10", "原文时间表示":"2026年9月10日", "联系路径":"COMMENT"})) {
    fireEvent.change(within(form).getByLabelText(name),{target:{value}});
  }
  fireEvent.click(within(form).getByRole("checkbox",{name:/我已亲自核对/}));
  fireEvent.click(within(form).getByRole("button",{name:"保存来源核验"}));
  await within(form).findByText("当前版本核验记录");
  expect((screen.getByRole("button",{name:"确认入库"}) as HTMLButtonElement).disabled).toBe(true);
  expect(transport.mock.calls.filter(c=>c[3]?.action==='ASSESS')).toHaveLength(0);
  fireEvent.click(screen.getByRole("button",{name:"按画像重新判断"}));
  await waitFor(()=>expect((screen.getByRole("button",{name:"确认入库"}) as HTMLButtonElement).disabled).toBe(false));
  expect(transport.mock.calls.filter(c=>c[3]?.action==='ASSESS')).toHaveLength(1);
});

it("recovers a lost decision outside the current filter using only the original GET", async () => {
  const { transport } = mount({
    assessed: true,
    published: true,
    loseDecision: true,
  });
  await ready();
  await verify();
  fireEvent.click(screen.getByRole("button", { name: "确认入库" }));
  const dialog = screen.getByRole("dialog", { name: "确认候选入库" });
  fireEvent.click(within(dialog).getByRole("checkbox"));
  fireEvent.click(within(dialog).getByRole("button", { name: "确认入库" }));
  await screen.findByText(/本次结果尚未确定，请核对原请求/);
  fireEvent.change(screen.getByRole("textbox", { name: "搜索原始线索" }), {
    target: { value: "nothing" },
  });
  await screen.findByText("没有符合条件的线索");
  const history = screen.getByRole("region", { name: "候选原请求记录" });
  fireEvent.click(within(history).getByText(/^查看处理记录/));
  const includeRecord =
    within(history).getByText(/确认入库 · 结果待确认/).parentElement!;
  fireEvent.click(
    within(includeRecord).getByRole("button", { name: /^查看处理结果/ }),
  );
  await screen.findByText(/原请求已核对成功/);
  expect(screen.queryByText(/本次结果尚未确定，请核对原请求/)).toBeNull();
  expect(transport.mock.calls.filter((c) => c[2] === "POST")).toHaveLength(2);
  expect(
    transport.mock.calls.filter((c) => c[0] === "candidates.request"),
  ).toHaveLength(1);
});

it("historical candidates cannot trigger assessment or verification", async () => {
  const { transport } = mount({ assessed: true, historical: true });
  await ready();
  expect(
    (screen.getByRole("button", { name: /按画像.*判断/ }) as HTMLButtonElement)
      .disabled,
  ).toBe(true);
  expect(
    (screen.getByRole("button", { name: "保存来源核验" }) as HTMLButtonElement)
      .disabled,
  ).toBe(true);
  expect(
    (screen.getByRole("button", { name: "确认入库" }) as HTMLButtonElement)
      .disabled,
  ).toBe(true);
  expect(transport.mock.calls.filter((c) => c[2] === "POST")).toHaveLength(0);
});

it("does not adopt a late judgment after leaving and returning to the same filtered view", async () => {
  let finish!: () => void;
  const gate = new Promise<void>((resolve) => {
    finish = resolve;
  });
  mount({ assessmentGate: gate });
  await ready();
  fireEvent.click(screen.getByRole("button", { name: /按画像.*判断/ }));
  await screen.findByText(/画像判断 · 结果待确认/);
  fireEvent.change(screen.getByRole("textbox", { name: "搜索原始线索" }), {
    target: { value: "nothing" },
  });
  await screen.findByText("没有符合条件的线索");
  fireEvent.change(screen.getByRole("textbox", { name: "搜索原始线索" }), {
    target: { value: "" },
  });
  await ready();
  finish();
  await screen.findByText(/画像判断 · 结果已返回/);
  expect(screen.queryByText("您希望什么时候完成采购？")).toBeNull();
});

it("a raw evidence read failure cannot be replaced by a summary to enable INCLUDE", async () => {
  mount({ assessed: true, published: true, verified: true, rawError: true });
  await ready();
  await screen.findByText(/原文或绑定可能已变化/);
  expect(
    (screen.getByRole("button", { name: "确认入库" }) as HTMLButtonElement)
      .disabled,
  ).toBe(true);
});

it("unknown assessment locks ordinary writes and exposes only explicit original-request recovery", async () => {
  const { transport } = mount({ assessmentUnknown: true });
  await ready();
  fireEvent.click(screen.getByRole("button", { name: /按画像.*判断/ }));
  await screen.findByText(/画像判断 · 结果待确认/);
  fireEvent.click(screen.getByText('查看处理记录（1）'));
  const retry = await screen.findByRole('button', {name:'确认后重新判断'});
  await waitFor(()=>expect((retry as HTMLButtonElement).disabled).toBe(false));
  expect(
    (screen.getByRole("button", { name: /按画像.*判断/ }) as HTMLButtonElement)
      .disabled,
  ).toBe(true);
  expect(
    (screen.getByRole("button", { name: "保存来源核验" }) as HTMLButtonElement)
      .disabled,
  ).toBe(true);
  fireEvent.click(retry);
  const dialog = screen.getByRole("dialog", { name: "重新发起判断？" });
  expect(dialog.textContent).not.toContain('向配置的模型发送');
  expect(dialog.textContent).toContain('仍在处理时不重发');
  expect(dialog.textContent).toContain('可能再次消耗');
  fireEvent.click(within(dialog).getByRole("button", { name: "取消" }));
  expect(transport.mock.calls.filter((c) => c[2] === "POST")).toHaveLength(1);
});

it("rejects judgment from a different strategy even when the five-field request binding matches", async () => {
  mount({ wrongStrategy: true });
  await ready();
  fireEvent.click(screen.getByRole("button", { name: /按画像.*判断/ }));
  await screen.findByText(/画像判断 · 结果已返回/);
  expect(screen.queryByText("您希望什么时候完成采购？")).toBeNull();
  expect(screen.getByText(/判断结果与当前画像或来源不一致/)).toBeTruthy();
});

it("profile A to B to A clears the source form words and its human confirmation", async () => {
  mount();
  await ready();
  const form = screen.getByRole("region", { name: "人工来源核验" });
  fireEvent.change(within(form).getByRole("textbox", { name: "定位描述" }), {
    target: { value: "TEST location" },
  });
  fireEvent.click(within(form).getByRole("checkbox"));
  const profile = screen.getByRole("combobox", { name: "候选目标业务画像" });
  fireEvent.change(profile, {
    target: { value: "88888888-8888-4888-8888-888888888888" },
  });
  fireEvent.change(profile, { target: { value: candidateBinding.profileId } });
  const returned = screen.getByRole("region", { name: "人工来源核验" });
  expect(
    (within(returned).getByRole("checkbox") as HTMLInputElement).checked,
  ).toBe(false);
  expect(
    (
      within(returned).getByRole("textbox", {
        name: "定位描述",
      }) as HTMLTextAreaElement
    ).value,
  ).toBe("");
});

it("lets the user read the current candidate version without making a write", async () => {
  const { transport } = mount();
  await ready();
  const before = transport.mock.calls.filter(
    (call) => call[0] === "candidates.list",
  ).length;
  fireEvent.click(screen.getByRole("button", { name: "刷新当前版本" }));
  await waitFor(() =>
    expect(
      transport.mock.calls.filter((call) => call[0] === "candidates.list"),
    ).toHaveLength(before + 1),
  );
  expect(
    transport.mock.calls.filter((call) => call[2] === "POST"),
  ).toHaveLength(0);
});

it.each(["verification", "decision"] as const)(
  "does not overwrite refreshed binding with a late %s receipt",
  async (kind) => {
    let finish!: () => void;
    const gate = new Promise<void>((resolve) => {
      finish = resolve;
    });
    const { row } = mount({
      assessed: true,
      published: true,
      verified: kind === "decision",
      [kind === "decision" ? "decisionGate" : "verificationGate"]: gate,
    });
    await ready();
    if (kind === "verification") await verify(false);
    else {
      await waitFor(() =>
        expect(
          (
            screen.getByRole("button", {
              name: "确认入库",
            }) as HTMLButtonElement
          ).disabled,
        ).toBe(false),
      );
      fireEvent.click(screen.getByRole("button", { name: "确认入库" }));
      const dialog = screen.getByRole("dialog", { name: "确认候选入库" });
      fireEvent.click(within(dialog).getByRole("checkbox"));
      fireEvent.click(within(dialog).getByRole("button", { name: "确认入库" }));
    }
    await screen.findByText(
      new RegExp(
        `${kind === "decision" ? "确认入库" : "来源核验"} · 结果待确认`,
      ),
    );
    Object.assign(row, {
      status: "PENDING_REVIEW",
      currentBindingValid: false,
      assessmentStale: true,
      historical: true,
      sourceStatus: "UNVERIFIED",
    });
    delete row.sourceVerification;
    delete row.lastReview;
    delete row.opportunityId;
    fireEvent.click(
      screen.getByRole("button", { name: "刷新当前版本", hidden: true }),
    );
    await ready();
    finish();
    await screen.findByText(
      new RegExp(
        `${kind === "decision" ? "确认入库" : "来源核验"} · 结果已返回`,
      ),
    );
    expect(
      screen.getByRole("button", { name: "查看候选食品工厂扩产" }),
    ).toBeTruthy();
    expect(screen.queryByText("当前版本核验记录")).toBeNull();
    expect(screen.queryByText("已确认入库。")).toBeNull();
  },
);
