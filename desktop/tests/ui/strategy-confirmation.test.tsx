// @vitest-environment jsdom
import { StrictMode } from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TaskWizardPage } from "../../src/renderer/pages/TaskWizard";
import { clearLocalDrafts } from "../../src/renderer/app/hooks";
import { operationLedgerKey } from "../../src/renderer/app/operationLedger";
import { newTaskDraft, EMPTY_PROFILE, type TaskDraft } from "../../src/renderer/domain/models";
import { makeTerm } from "../../src/renderer/domain/task";
import { parseRoute } from "../../src/renderer/domain/routes";
import { ServiceError, type YikeService } from "../../src/renderer/services/contracts";
import type { AppContextValue } from "../../src/renderer/app/context";
import type { ResearchStrategiesService } from "../../src/renderer/services/researchStrategies";
import type { StrategyReceipt, StrategyView } from "../../src/shared/researchStrategies";

let context: AppContextValue;
let draft: TaskDraft & { executionLimits: { max_records: number; max_runtime_seconds: number } };
let fake: ReturnType<typeof strategyServerFixture>;
const CHECKBOX = "我已核对以上画像版本、搜索条件、账号与运行设置";
vi.mock("../../src/renderer/app/context", () => ({ useApp: () => context }));

/** In-memory UI fixture, not live business, transport, source, or execution proof. */
function strategyServerFixture() {
  const receipts = new Map<string, StrategyReceipt>();
  let prepared: StrategyReceipt | null = null;
  let state: StrategyReceipt["state"] = "DRAFT";
  const instant = "2026-09-10T00:00:00Z";
  const api = {
    prepare: vi.fn<ResearchStrategiesService["prepare"]>(async request => {
      expect(localStorage.getItem(operationLedgerKey("research-strategy-operations", context.session.userId!))).toContain(request.request_id);
      const id = crypto.randomUUID();
      prepared = {
        schema_version: "strategy-confirmation-v1", request_id: request.request_id, operation: "PREPARE",
        strategy_version_id: id, draft_id: request.draft_id, draft_revision: request.draft_revision,
        profile_version_id: request.profile_version_id, profile_sha256: "a".repeat(64), configuration_sha256: "b".repeat(64),
        snapshot: { strategy_version_id: id, profile_version_id: request.profile_version_id,
          configuration: request.configuration, platforms: request.platforms,
          max_records: request.max_records, max_runtime_seconds: request.max_runtime_seconds },
        state: "DRAFT", recorded_at: instant,
      };
      state = "DRAFT";
      receipts.set(request.request_id, structuredClone(prepared));
      return structuredClone(prepared);
    }),
    confirm: vi.fn<ResearchStrategiesService["confirm"]>(async request => {
      state = "CONFIRMED";
      const receipt: StrategyReceipt = { ...prepared!, request_id: request.request_id, operation: "CONFIRM", state };
      receipts.set(request.request_id, structuredClone(receipt));
      return receipt;
    }),
    revoke: vi.fn<ResearchStrategiesService["revoke"]>(async request => {
      state = "REVOKED";
      const receipt: StrategyReceipt = { ...prepared!, request_id: request.request_id, operation: "REVOKE", state };
      receipts.set(request.request_id, structuredClone(receipt));
      return receipt;
    }),
    getReceipt: vi.fn<ResearchStrategiesService["getReceipt"]>(async requestId => {
      if (!receipts.has(requestId)) throw new ServiceError("request_not_found", "未找到", 404);
      return structuredClone(receipts.get(requestId));
    }),
    getStrategy: vi.fn<ResearchStrategiesService["getStrategy"]>(async () => {
      const { request_id: _requestId, operation: _operation, recorded_at: _recordedAt, ...binding } = prepared!;
      const view: StrategyView = { ...binding, state, created_at: instant,
        confirmed_at: state === "CONFIRMED" ? instant : null, revoked_at: state === "REVOKED" ? instant : null,
        is_current: true, profile_current: true };
      return view;
    }),
  } satisfies ResearchStrategiesService;
  return { api, receipts };
}

function persistDraft() {
  sessionStorage.setItem("yike.ui.draft.v1.task." + context.session.userId, JSON.stringify(draft));
  sessionStorage.setItem("yike.ui.draft.v1.task-library." + context.session.userId, JSON.stringify([draft]));
}
beforeEach(() => {
  clearLocalDrafts();
  sessionStorage.clear();
  localStorage.clear();
  draft = { ...newTaskDraft(), name: "合成界面策略场景", profileId: crypto.randomUUID(), profileVersion: 1,
    terms: [makeTerm("设备采购")], exclusions: [makeTerm("招聘")], links: "https://example.com/kept-input",
    platforms: ["xhs"], accounts: { xhs: "synthetic-account" },
    executionLimits: { max_records: 37, max_runtime_seconds: 913 } };
  fake = strategyServerFixture();
  context = {
    service: {
      profiles: vi.fn().mockResolvedValue([{ id: draft.profileId, version: 1, status: "CONFIRMED", description: "合成",
        fields: { ...EMPTY_PROFILE, service: "合成设备服务" } }]),
      connections: vi.fn().mockResolvedValue([{ platform: "xhs", status: "CONNECTED", accountId: "synthetic-account", capabilities: ["read", "search"] }]),
      info: vi.fn().mockResolvedValue({ deviceReady: true }),
      startTask: vi.fn(), suggest: vi.fn(), researchStrategies: fake.api,
    } as unknown as YikeService,
    session: { authenticated: true, userId: crypto.randomUUID() }, sessionReady: true,
    route: parseRoute("#/tasks/new?step=confirm"), navigate: vi.fn(), notify: vi.fn(), refreshSession: vi.fn(),
  };
  persistDraft();
});
afterEach(() => { cleanup(); clearLocalDrafts(); vi.restoreAllMocks(); });

function button(name: string): HTMLButtonElement {
  return screen.getByRole("button", { name }) as HTMLButtonElement;
}
function checkbox(): HTMLInputElement {
  return screen.getByRole("checkbox", { name: CHECKBOX }) as HTMLInputElement;
}
async function prepareSnapshot() {
  await waitFor(() => expect(button("准备策略快照").disabled).toBe(false));
  fireEvent.click(button("准备策略快照"));
  await waitFor(() => expect(fake.api.prepare).toHaveBeenCalledOnce());
  await waitFor(() => expect(fake.api.getStrategy).toHaveBeenCalled());
  const receipt = fake.receipts.get(fake.api.prepare.mock.calls[0][0].request_id)!;
  await waitFor(() => expect(document.body.textContent).toContain(receipt.strategy_version_id));
  return receipt;
}
async function confirmSnapshot() {
  await prepareSnapshot();
  expect(checkbox().checked).toBe(false);
  expect(button("确认本次策略").disabled).toBe(true);
  fireEvent.click(checkbox());
  await waitFor(() => expect(button("确认本次策略").disabled).toBe(false));
  fireEvent.click(button("确认本次策略"));
  await waitFor(() => expect(fake.api.confirm).toHaveBeenCalledOnce());
  await screen.findByText("本次策略已确认");
  expect(button("确认并启动").disabled).toBe(true);
}

describe("TaskWizard strategy confirmation with the actual controller", () => {
  it('prepares and confirms a similar-research origin while keeping research execution blocked',async()=>{
    draft.research={version:1,demandTypes:['INQUIRY'],maxSoubei:100,limits:{sources:10,minutes:5,modelCalls:5},
      stopAtAnyLimit:true,evidenceOrder:'SOURCE_MATCH_CONTEXT',provenance:{requestId:crypto.randomUUID(),
       suggestionId:`suggestion_${'e'.repeat(64)}`,userId:context.session.userId!,opportunityId:'synthetic-opportunity',
       profileVersionId:draft.profileId,sourceUrl:'https://example.com/buyer',evidenceVersion:'synthetic-evidence',
       accountScope:{id:'synthetic-tenant',version:1},originalScope:'设备采购',additionalScope:'同类设备需求'}};
    persistDraft();render(<TaskWizardPage/>);
    await confirmSnapshot();
    expect(fake.api.prepare.mock.calls[0][0].configuration.research!.provenance).toEqual(draft.research.provenance);
    expect(context.service.startTask).not.toHaveBeenCalled();
    expect(button('确认并启动').disabled).toBe(true);
  });
  it('creates a native monitor only after strategy confirmation, without a once START', async()=>{
    const account='5cbef3a50000000016026b8f',device=crypto.randomUUID(),connection=crypto.randomUUID();
    draft={...draft,mode:'monitor',exclusions:[],links:'',accounts:{xhs:account},
      schedule:{kind:'interval',times:[],interval:1,start:'09:00',end:'18:00',timezone:'Asia/Shanghai',policyVersion:1},
      executionLimits:{max_records:20,max_runtime_seconds:600}};
    context.route=parseRoute('#/tasks/new?mode=monitor&step=confirm');
    context.service.connections=vi.fn().mockResolvedValue([{platform:'xhs',status:'CONNECTED',accountId:account,capabilities:['search'],
      registration:{connectionId:connection,version:1,deviceId:device,disconnectedAt:null},
      foregroundBinding:{mode:'three-platform-foreground-v1',platform:'XIAOHONGSHU',connectionId:connection,connectionVersion:1,deviceId:device,accountPublicId:account}}]);
    context.service.execution={execute:vi.fn().mockResolvedValue({state:'LIST',requests:[]})};
    const execute=vi.fn(async(command:any)=>command.action==='LIST'?{state:'LIST',supported:true,plans:[],serverTime:null}:{state:'UNKNOWN',requestId:command.requestId});
    context.service.monitorCollection={execute} as any;
    persistDraft();render(<TaskWizardPage/>);
    await prepareSnapshot();fireEvent.click(checkbox());
    fireEvent.click(button('确认本次策略'));await screen.findByText('本次策略已确认');
    await waitFor(()=>expect(button('确认并启动').disabled).toBe(false));
    fireEvent.click(button('确认并启动'));
    await waitFor(()=>expect(execute.mock.calls.some(([c])=>c.action==='CREATE')).toBe(true));
    const create=execute.mock.calls.find(([c])=>c.action==='CREATE')![0];
    expect(create).toMatchObject({profileVersionId:draft.profileId,humanConfirmed:true,targets:[{platform:'XIAOHONGSHU',connection_id:connection,connection_version:1}]});
    expect(vi.mocked(context.service.execution.execute).mock.calls.every(([c])=>c.action==='LIST')).toBe(true);
    await waitFor(()=>expect(button('确认并启动').disabled).toBe(true));
    fireEvent.click(button('确认并启动'));
    expect(execute.mock.calls.filter(([c])=>c.action==='CREATE')).toHaveLength(1);
  });
  it("does not prepare from direct P19 render and cannot use the local checkbox to bypass new confirmation", async () => {
    render(<StrictMode><TaskWizardPage /></StrictMode>);
    await waitFor(() => expect(context.service.profiles).toHaveBeenCalled());
    expect(fake.api.prepare).not.toHaveBeenCalled();
    expect(button("准备策略快照")).toBeTruthy();
    expect(checkbox().disabled).toBe(true);
    fireEvent.click(checkbox());
    expect(button("确认并启动").disabled).toBe(true);
    fireEvent.click(button("确认并启动"));
    expect(context.service.startTask).not.toHaveBeenCalled();
    expect(fake.api.confirm).not.toHaveBeenCalled();
  });

  it("prepares the exact draft and technical budgets, then requires an explicit confirmation without starting a task", async () => {
    render(<TaskWizardPage />);
    await confirmSnapshot();
    const request = fake.api.prepare.mock.calls[0][0];
    const receipt = fake.receipts.get(request.request_id)!;
    expect(request).toMatchObject({ draft_id: draft.id, draft_revision: draft.revision,
      profile_version_id: draft.profileId, ...draft.executionLimits,
      configuration: { name: draft.name, source: draft.source, links: [draft.links], keywords: ["设备采购"],
        exclusions: ["招聘"], mode: "once", schedule: null, research: null }, platforms: ["XIAOHONGSHU"] });
    expect(fake.api.confirm.mock.calls[0][0]).toMatchObject({ human_confirmed: true,
      strategy_version_id: receipt.strategy_version_id, configuration_sha256: receipt.configuration_sha256 });
    expect(context.service.startTask).not.toHaveBeenCalled();
    expect(context.navigate).not.toHaveBeenCalled();
  });

  it.each(["search", "links"] as const)("shows all bound fields read-only, including inactive inputs for %s", async source => {
    draft = { ...draft, source, mode:'monitor', research: { version: 1, demandTypes: ["INQUIRY", "COMPARISON", "REPLACEMENT", "CHANGE"],
      maxSoubei: 211, limits: { sources: 43, minutes: 17, modelCalls: 29 }, stopAtAnyLimit: true, evidenceOrder: "SOURCE_MATCH_CONTEXT" },
      schedule: { kind: "interval", times: ["08:13", "19:27"], interval: 2.5,
        start: "07:21", end: "22:49", timezone: "Asia/Shanghai", policyVersion: 1 } };
    persistDraft();
    render(<TaskWizardPage />);
    const receipt = await prepareSnapshot();
    const summary = screen.getByText("全部绑定配置");
    fireEvent.click(summary);
    const details = summary.closest("details")!;
    expect(details).not.toBeNull();
    expect(details.querySelectorAll("input, textarea, select")).toHaveLength(0);
    const text = details.textContent!;
    for (const value of [draft.id, draft.name, String(draft.revision), draft.profileId, receipt.strategy_version_id,
      receipt.profile_sha256, receipt.configuration_sha256, "设备采购", "招聘", draft.links,
      "211", "43", "17", "29", "SOURCE_MATCH_CONTEXT",
      "08:13", "19:27", "2.5", "07:21", "22:49", "Asia/Shanghai", "37", "913", "research-strategy-v1",
      receipt.request_id, receipt.recorded_at, receipt.state, "小红书"])
      expect(text, `missing bound preview value: ${value}`).toContain(value);
    for (const demand of [/INQUIRY|询价|询盘/, /COMPARISON|比较|对比/, /REPLACEMENT|替换|替代|更换/, /CHANGE|变化|变更/])
      expect(text).toMatch(demand);
    expect(text).toMatch(/stopAtAnyLimit|任一.*上限|任一.*停止/);
    expect(document.body.textContent).toContain("保留但本次不执行");
    expect(text).toContain("持续监控");
    expect(context.service.startTask).not.toHaveBeenCalled();
  });

  it.each(["501", "missing-method"] as const)("fails closed for a present but %s strategy service without using legacy start", async failure => {
    if (failure === "501") fake.api.prepare.mockRejectedValueOnce(new ServiceError("NOT_IMPLEMENTED", "策略服务尚未启用", 501));
    else context.service.researchStrategies = {} as ResearchStrategiesService;
    render(<TaskWizardPage />);
    await waitFor(() => expect(button("准备策略快照").disabled).toBe(false));
    fireEvent.click(button("准备策略快照"));
    await waitFor(() => expect(button("核对并重试原策略请求").disabled).toBe(false));
    if (failure === "501") expect(screen.getByText("策略服务尚未启用")).toBeTruthy();
    fireEvent.click(checkbox());
    expect(button("确认并启动").disabled).toBe(true);
    expect(button("确认本次策略").disabled).toBe(true);
    fireEvent.click(button("确认并启动"));
    expect(context.service.startTask).not.toHaveBeenCalled();
  });

  it("queries a lost prepare response and recovers the original receipt without a second prepare", async () => {
    const ordinary = fake.api.prepare.getMockImplementation()!;
    fake.api.prepare.mockImplementationOnce(async request => {
      await ordinary(request);
      throw new ServiceError("SERVICE_TIMEOUT", "策略响应丢失");
    });
    render(<TaskWizardPage />);
    await waitFor(() => expect(button("准备策略快照").disabled).toBe(false));
    fireEvent.click(button("准备策略快照"));
    await screen.findByText("策略响应丢失");
    expect(button("确认并启动").disabled).toBe(true);
    const original = fake.api.prepare.mock.calls[0][0];
    fireEvent.click(button("查询原策略请求"));
    await waitFor(() => expect(fake.api.getReceipt).toHaveBeenCalledWith(original.request_id));
    await waitFor(() => expect(document.body.textContent).toContain(fake.receipts.get(original.request_id)!.strategy_version_id));
    expect(fake.api.prepare).toHaveBeenCalledOnce();
    expect(fake.api.confirm).not.toHaveBeenCalled();
    expect(checkbox().checked).toBe(false);
    expect(button("确认并启动").disabled).toBe(true);
  });

  it("retries an unknown prepare only after querying 404 and keeps its exact request UUID", async () => {
    fake.api.prepare.mockRejectedValueOnce(new ServiceError("SERVICE_TIMEOUT", "准备超时"));
    render(<TaskWizardPage />);
    await waitFor(() => expect(button("准备策略快照").disabled).toBe(false));
    fireEvent.click(button("准备策略快照"));
    await screen.findByText("准备超时");
    const original = structuredClone(fake.api.prepare.mock.calls[0][0]);
    fireEvent.click(button("核对并重试原策略请求"));
    await waitFor(() => expect(fake.api.prepare).toHaveBeenCalledTimes(2));
    expect(fake.api.getReceipt).toHaveBeenCalledWith(original.request_id);
    expect(fake.api.getReceipt.mock.invocationCallOrder[0]).toBeLessThan(fake.api.prepare.mock.invocationCallOrder[1]);
    expect(fake.api.prepare.mock.calls[1][0]).toEqual(original);
    expect(fake.api.confirm).not.toHaveBeenCalled();
    expect(context.service.startTask).not.toHaveBeenCalled();
  });

  it("requires fresh user confirmation after remount even when the original confirmed receipt is recovered", async () => {
    const first = render(<TaskWizardPage />);
    await confirmSnapshot();
    first.unmount();
    render(<TaskWizardPage />);
    expect(checkbox().checked).toBe(false);
    expect(button("确认并启动").disabled).toBe(true);
    fireEvent.click(button("查询原策略请求"));
    await waitFor(() => expect(fake.api.getReceipt).toHaveBeenCalled());
    await waitFor(() => expect(button("查询原策略请求").disabled).toBe(false));
    expect(checkbox().checked).toBe(false);
    expect(button("确认并启动").disabled).toBe(true);
    expect(fake.api.confirm).toHaveBeenCalledOnce();
    fireEvent.click(checkbox());
    fireEvent.click(button("确认本次策略"));
    await screen.findByText("本次策略已确认");
    expect(button("确认并启动").disabled).toBe(true);
    expect(fake.api.confirm).toHaveBeenCalledOnce();
    expect(context.service.startTask).not.toHaveBeenCalled();
  });

  it("invalidates confirmation after an actual task edit and does not prepare again from navigation", async () => {
    const page = render(<TaskWizardPage />);
    await confirmSnapshot();
    context = { ...context, route: parseRoute("#/tasks/new") };
    page.rerender(<TaskWizardPage />);
    fireEvent.change(screen.getByRole("textbox", { name: "任务名称" }), { target: { value: "修改后的合成策略" } });
    context = { ...context, route: parseRoute("#/tasks/new?step=confirm") };
    page.rerender(<TaskWizardPage />);
    expect(checkbox().checked).toBe(false);
    expect(screen.queryByText("本次策略已确认")).toBeNull();
    fireEvent.click(checkbox());
    expect(button("确认本次策略").disabled).toBe(true);
    expect(button("确认并启动").disabled).toBe(true);
    expect(fake.api.prepare).toHaveBeenCalledOnce();
    fireEvent.click(button("准备策略快照"));
    await waitFor(() => expect(fake.api.prepare).toHaveBeenCalledTimes(2));
    const updated = fake.api.prepare.mock.calls[1][0];
    expect(updated.draft_revision).toBe(draft.revision + 1);
    expect(updated.configuration.name).toBe("修改后的合成策略");
    await waitFor(() => expect(document.body.textContent).toContain(fake.receipts.get(updated.request_id)!.strategy_version_id));
    expect(checkbox().checked).toBe(false);
    expect(button("确认本次策略").disabled).toBe(true);
    expect(fake.api.confirm).toHaveBeenCalledOnce();
    expect(context.service.startTask).not.toHaveBeenCalled();
  });

  it("wires an actual execution-cap edit to a new revision while preserving the other cap and all research inputs", async () => {
    draft = { ...draft, research: { version: 1, demandTypes: ["INQUIRY", "REPLACEMENT"],
      maxSoubei: 211, limits: { sources: 43, minutes: 17, modelCalls: 29 },
      stopAtAnyLimit: true, evidenceOrder: "SOURCE_MATCH_CONTEXT" } };
    const original = structuredClone(draft);
    persistDraft();
    const page = render(<TaskWizardPage />);
    await confirmSnapshot();
    const firstRequest = structuredClone(fake.api.prepare.mock.calls[0][0]);

    fireEvent.click(button("返回修改"));
    expect(context.navigate).toHaveBeenCalled();
    context = { ...context, route: parseRoute("#/tasks/new") };
    page.rerender(<TaskWizardPage />);
    fireEvent.click(screen.getByText((_text, element) =>
      element?.tagName === "SUMMARY" && element.textContent?.startsWith("执行保护上限") === true));
    fireEvent.change(screen.getByRole("spinbutton", { name: "最多处理记录数" }), { target: { value: "52" } });
    await waitFor(() => {
      const saved = JSON.parse(sessionStorage.getItem("yike.ui.draft.v1.task." + context.session.userId)!);
      expect(saved).toMatchObject({ revision: original.revision + 1,
        executionLimits: { max_records: 52, max_runtime_seconds: original.executionLimits.max_runtime_seconds },
        research: original.research, schedule: original.schedule, terms: original.terms,
        exclusions: original.exclusions, links: original.links });
    });

    context = { ...context, route: parseRoute("#/tasks/new?step=confirm") };
    page.rerender(<TaskWizardPage />);
    expect(checkbox().checked).toBe(false);
    expect(screen.queryByText("本次策略已确认")).toBeNull();
    expect(button("确认本次策略").disabled).toBe(true);
    fireEvent.click(button("准备策略快照"));
    await waitFor(() => expect(fake.api.prepare).toHaveBeenCalledTimes(2));
    const nextRequest = fake.api.prepare.mock.calls[1][0];
    expect(nextRequest).toMatchObject({ draft_id: original.id, draft_revision: original.revision + 1,
      max_records: 52, max_runtime_seconds: original.executionLimits.max_runtime_seconds,
      configuration: firstRequest.configuration, platforms: firstRequest.platforms });
    expect(nextRequest.request_id).not.toBe(firstRequest.request_id);
    await waitFor(() => expect(document.body.textContent).toContain(fake.receipts.get(nextRequest.request_id)!.strategy_version_id));
    expect(checkbox().checked).toBe(false);
    expect(fake.api.confirm).toHaveBeenCalledOnce();
    expect(button("确认并启动").disabled).toBe(true);
    expect(context.service.startTask).not.toHaveBeenCalled();
    expect(localStorage.getItem(operationLedgerKey("task-operations", context.session.userId!))).toBeNull();
    expect(localStorage.getItem(operationLedgerKey("unknown-task-starts", context.session.userId!))).toBeNull();
  });

  it("queries an unknown revoke without reactivating the former confirmed strategy", async () => {
    render(<TaskWizardPage />);
    await confirmSnapshot();
    const ordinary = fake.api.revoke.getMockImplementation()!;
    fake.api.revoke.mockImplementationOnce(async request => {
      await ordinary(request);
      throw new ServiceError("SERVICE_TIMEOUT", "撤销响应丢失");
    });
    fireEvent.click(button("撤销本次策略"));
    await screen.findByText("撤销响应丢失");
    expect(button("确认并启动").disabled).toBe(true);
    const request = fake.api.revoke.mock.calls[0][0];
    fireEvent.click(button("查询原策略请求"));
    await waitFor(() => expect(fake.api.getReceipt).toHaveBeenCalledWith(request.request_id));
    await waitFor(() => expect(button("查询原策略请求").disabled).toBe(false));
    expect(button("确认并启动").disabled).toBe(true);
    expect(button("确认本次策略").disabled).toBe(true);
    expect(fake.api.revoke).toHaveBeenCalledOnce();
    expect(context.service.startTask).not.toHaveBeenCalled();
  });

  it("never dispatches either old start protocol or writes its ledger even after new strategy confirmation", async () => {
    const operationStart = vi.fn();
    context.service.taskOperations = { start: operationStart } as unknown as NonNullable<YikeService["taskOperations"]>;
    render(<TaskWizardPage />);
    await confirmSnapshot();
    expect(document.body.textContent).toMatch(/签名执行.*尚未|05F/);
    fireEvent.click(button("确认并启动"));
    expect(button("确认并启动").disabled).toBe(true);
    expect(context.service.startTask).not.toHaveBeenCalled();
    expect(operationStart).not.toHaveBeenCalled();
    expect(localStorage.getItem(operationLedgerKey("task-operations", context.session.userId!))).toBeNull();
    expect(localStorage.getItem(operationLedgerKey("unknown-task-starts", context.session.userId!))).toBeNull();
    expect(context.navigate).not.toHaveBeenCalled();
  });
});
