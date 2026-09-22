// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { SearchSuggestionPanel } from "../../src/renderer/pages/tasks/SearchSuggestionPanel";
import type { SuggestionPreview, SuggestionReceipt, SuggestionRequest } from "../../src/shared/searchSuggestions";
import type { SearchSuggestionsService } from "../../src/renderer/services/searchSuggestions";
import { saveSearchSuggestion } from "../../src/renderer/pages/tasks/searchSuggestionStorage";

const draftId = "11111111-1111-4111-8111-111111111111";
const profileId = "22222222-2222-4222-8222-222222222222";
const scope = { userId: "user-a", accountScopeId: "space-a", accountScopeVersion: 1 };
const preview: SuggestionPreview = {
  profile_version_id: profileId, profile_sha256: "a".repeat(64),
  description: "为制造业客户提供设备预测性维护服务，目标客户为华东工厂。",
  model_provider: "controlled-provider", model_name: "controlled-model",
  disclosure_policy_version: "profile-description-v1",
};
const receipt = (request: SuggestionRequest, profileCurrent = true): SuggestionReceipt => ({
  request_id: request.request_id, draft_id: request.draft_id,
  profile_version_id: request.profile_version_id, draft_revision: request.draft_revision,
  profile_sha256: request.disclosure.profile_sha256,
  model_provider: request.disclosure.model_provider, model_name: request.disclosure.model_name,
  disclosure_policy_version: "profile-description-v1", rule_version: "search-suggestion-v1",
  state: "SUCCEEDED", profile_current: profileCurrent,
  result: { keywords: ["设备预测性维护"], exclusions: ["招聘"], rationale: "命中业务与客户场景",
    evidence: ["业务介绍明确包含设备维护"], unknowns: ["预算范围未知"] },
  usage: { prompt_tokens: 10, completion_tokens: 5, total_tokens: 15 }, error_code: null,
  created_at: "2026-09-11T00:00:00Z", updated_at: "2026-09-11T00:00:01Z",
});
const props = (service: SearchSuggestionsService) => ({
  service, scope, draftId, draftRevision: 3, profileVersionId: profileId,
  profileConfirmed: true, hasTerms: false, onApply: vi.fn(() => true),
});

describe("controlled search suggestion panel", () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => { cleanup(); vi.restoreAllMocks(); });

  it('shows only filled business content without model internals or process explanations', async () => {
    const full = {...preview, description: '服务内容："AI软件定制"\n目标客户："企业"\n服务地区："全国"\n项目偏好：""\n排除项：""'};
    const service = {preview: vi.fn().mockResolvedValue(full), submit: vi.fn(async (request: SuggestionRequest) => receipt(request)), getReceipt: vi.fn()};
    render(<SearchSuggestionPanel {...props(service)} />);
    fireEvent.click(screen.getByRole('button', {name: '生成建议'}));
    const dialog = await screen.findByRole('dialog');
    expect(dialog.textContent).toContain('AI软件定制');
    for (const hidden of ['项目偏好：', '排除项：', preview.model_provider, preview.model_name,
      preview.disclosure_policy_version, '受控模型', '披露规则', '不会自动采集或发送']) {
      expect(dialog.textContent).not.toContain(hidden);
    }
    expect(service.submit).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', {name: '确认生成'}));
    await waitFor(() => expect(service.submit).toHaveBeenCalledOnce());
    expect(service.submit.mock.calls[0][0].disclosure).toEqual({accepted:true,
      profile_sha256:full.profile_sha256,model_provider:full.model_provider,
      model_name:full.model_name,policy_version:full.disclosure_policy_version});
    expect(full.description).toContain('排除项：""');
  });

  it('keeps business values and legacy free text intact when simplifying the preview', async () => {
    const full = {...preview, description: '服务内容："支持\\n多行与\\\"引号\\\""\n目标客户："企业"\n服务地区："全国"\n项目偏好："保留原需求"\n排除项："招聘"'};
    const service = {preview: vi.fn().mockResolvedValue(full), submit:vi.fn(), getReceipt:vi.fn()};
    const view = render(<SearchSuggestionPanel {...props(service)} />);
    fireEvent.click(screen.getByRole('button', {name:'生成建议'}));
    const dialog = await screen.findByRole('dialog');
    expect(dialog.textContent).toContain('服务内容：支持\n多行与"引号"');
    expect(dialog.textContent).toContain('排除项：招聘');
    view.unmount();
    const legacy = '自填原文：保留原始格式\n排除项：""\n不能按片段过滤客户自由文本';
    service.preview.mockResolvedValue({...preview,description:legacy});
    render(<SearchSuggestionPanel {...props(service)} />);
    fireEvent.click(screen.getByRole('button', {name:'生成建议'}));
    expect((await screen.findByRole('dialog')).textContent).toContain(legacy);
    expect(service.submit).not.toHaveBeenCalled();
  });

  it('shows actionable search words without rationale or model-generated explanations', async () => {
    const service = {preview:vi.fn().mockResolvedValue(preview),
      submit:vi.fn(async (request:SuggestionRequest)=>receipt(request)),getReceipt:vi.fn()};
    render(<SearchSuggestionPanel {...props(service)} />);
    fireEvent.click(screen.getByRole('button',{name:'生成建议'}));
    await screen.findByRole('dialog');
    fireEvent.click(screen.getByRole('button',{name:/^(确认生成|我已核对，发送并生成)$/}));
    await screen.findByText('设备预测性维护');
    expect(screen.getByText('招聘')).toBeTruthy();
    for(const text of ['建议原因','依据','未知信息','命中业务与客户场景','业务介绍明确包含设备维护','预算范围未知']) {
      expect(screen.queryByText(text)).toBeNull();
    }
    expect(screen.getByRole('button',{name:'合并新增建议'})).toBeTruthy();
  });

  it('keeps unresolved suggestions actionable while request IDs are removed', async()=>{
    const request: SuggestionRequest = {request_id:'44444444-4444-4444-8444-444444444444',draft_id:draftId,
      profile_version_id:profileId,draft_revision:3,disclosure:{accepted:true,profile_sha256:preview.profile_sha256,
        model_provider:preview.model_provider,model_name:preview.model_name,policy_version:preview.disclosure_policy_version}};
    saveSearchSuggestion({schemaVersion:1,scope,request,receipt:null});
    const service={preview:vi.fn(),submit:vi.fn(),getReceipt:vi.fn().mockResolvedValue({...receipt(request),state:'UNKNOWN',result:null,usage:null,error_code:'suggestion_result_unknown'})};
    render(<SearchSuggestionPanel {...props(service)}/>);
    await waitFor(()=>expect(service.getReceipt).toHaveBeenCalled());
    expect(document.body.textContent).not.toContain(request.request_id);
    expect(screen.getByText('结果待核对').closest('details')).toBeNull();
    expect(screen.getByRole('button',{name:'核对原请求'})).toBeTruthy();
    expect(service.submit).not.toHaveBeenCalled();
  });

  it("restores a definite rejection and requires explicit ending plus fresh disclosure, never auto POST", async () => {
    const denied = (request: SuggestionRequest): SuggestionReceipt => ({ ...receipt(request),
      state: "NOT_SUBMITTED", profile_current: false, result: null, usage: null, error_code: "suggestion_quota_exceeded" });
    const service = { preview: vi.fn().mockResolvedValue(preview), submit: vi.fn(async (r: SuggestionRequest) => denied(r)),
      getReceipt: vi.fn(async (r: SuggestionRequest) => denied(r)) };
    const view = render(<SearchSuggestionPanel {...props(service)} />);
    fireEvent.click(screen.getByRole("button", { name: "生成建议" }));
    await screen.findByText(preview.description);
    fireEvent.click(screen.getByRole("button", { name: "确认生成" }));
    expect(await screen.findByText(/已确认未受理，未开始生成/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "合并新增建议" })).toBeNull();
    view.unmount();
    render(<SearchSuggestionPanel {...props(service)} />);
    await waitFor(() => expect(service.getReceipt).toHaveBeenCalledOnce());
    expect(service.submit).toHaveBeenCalledOnce();
    fireEvent.click(await screen.findByRole("button", { name: "结束未受理请求" }));
    expect(service.submit).toHaveBeenCalledOnce();
    fireEvent.click(screen.getByRole("button", { name: "生成建议" }));
    await screen.findByText(preview.description);
    expect(service.submit).toHaveBeenCalledOnce();
    fireEvent.click(screen.getByRole("button", { name: "确认生成" }));
    await waitFor(() => expect(service.submit).toHaveBeenCalledTimes(2));
    expect(service.submit.mock.calls[1][0].request_id).not.toBe(service.submit.mock.calls[0][0].request_id);
  });

  it("does not send on mount and submits once only after full disclosure confirmation", async () => {
    const service = { preview: vi.fn().mockResolvedValue(preview),
      submit: vi.fn(async (request: SuggestionRequest) => receipt(request)), getReceipt: vi.fn() };
    render(<SearchSuggestionPanel {...props(service)} />);
    expect(service.preview).not.toHaveBeenCalled(); expect(service.submit).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "生成建议" }));
    expect(await screen.findByText(preview.description)).toBeTruthy();
    expect(screen.queryByText(/controlled-provider \/ controlled-model/)).toBeNull();
    expect(service.submit).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "确认生成" }));
    await waitFor(() => expect(service.submit).toHaveBeenCalledOnce());
    expect(await screen.findByText("设备预测性维护")).toBeTruthy();
  });

  it("automatically opens the disclosure preview for a fresh task without submitting", async () => {
    const service = { preview: vi.fn().mockResolvedValue(preview),
      submit: vi.fn(async (request: SuggestionRequest) => receipt(request)), getReceipt: vi.fn() };
    render(<SearchSuggestionPanel {...props(service)} autoPreview />);
    expect(await screen.findByRole("dialog", { name: "生成搜索建议" })).toBeTruthy();
    expect(service.preview).toHaveBeenCalledOnce();
    expect(service.submit).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "确认生成" }));
    await waitFor(() => expect(service.submit).toHaveBeenCalledOnce());
  });

  it("does not POST when the original request cannot be durably stored", async () => {
    const service = { preview: vi.fn().mockResolvedValue(preview), submit: vi.fn(), getReceipt: vi.fn() };
    render(<SearchSuggestionPanel {...props(service)} />);
    fireEvent.click(screen.getByRole("button", { name: "生成建议" }));
    await screen.findByText(preview.description);
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new DOMException("full", "QuotaExceededError"); });
    fireEvent.click(screen.getByRole("button", { name: "确认生成" }));
    expect(await screen.findByText(/无法可靠保存/)).toBeTruthy();
    expect(service.submit).not.toHaveBeenCalled();
  });

  it("ignores a late preview after the customer-space scope changes", async () => {
    let finish!: (value: SuggestionPreview) => void;
    const service = { preview: vi.fn(() => new Promise<SuggestionPreview>(resolve => { finish = resolve; })),
      submit: vi.fn(), getReceipt: vi.fn() };
    const view = render(<SearchSuggestionPanel {...props(service)} />);
    fireEvent.click(screen.getByRole("button", { name: "生成建议" }));
    await waitFor(() => expect(service.preview).toHaveBeenCalledOnce());
    view.rerender(<SearchSuggestionPanel {...props(service)} scope={{ ...scope, accountScopeId: "space-b" }} />);
    await act(async () => finish(preview));
    expect(screen.queryByRole("dialog", { name: "生成搜索建议" })).toBeNull();
    expect(service.submit).not.toHaveBeenCalled();
  });

  it("restores by GET of the original request and keeps another draft read-only", async () => {
    const request: SuggestionRequest = {
      request_id: "44444444-4444-4444-8444-444444444444", draft_id: draftId,
      profile_version_id: profileId, draft_revision: 3,
      disclosure: { accepted: true, profile_sha256: preview.profile_sha256,
        model_provider: preview.model_provider, model_name: preview.model_name, policy_version: "profile-description-v1" },
    };
    saveSearchSuggestion({ schemaVersion: 1, scope, request, receipt: null });
    const service = { preview: vi.fn(), submit: vi.fn(), getReceipt: vi.fn().mockResolvedValue(receipt(request)) };
    render(<SearchSuggestionPanel {...props(service)} draftId="55555555-5555-4555-8555-555555555555" />);
    expect(await screen.findByText("设备预测性维护")).toBeTruthy();
    expect(service.getReceipt).toHaveBeenCalledWith(request, expect.any(AbortSignal));
    expect(service.submit).not.toHaveBeenCalled();
    expect(screen.getByText(/历史草稿\/画像，只读核对/)).toBeTruthy();
    expect((screen.getByRole("button", { name: "合并新增建议" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("does not apply when the adopting GET resolves after unmount", async () => {
    let finish!: (value: SuggestionReceipt) => void;
    let original!: SuggestionRequest;
    const service = { preview: vi.fn().mockResolvedValue(preview),
      submit: vi.fn(async (request: SuggestionRequest) => { original = request; return receipt(request); }),
      getReceipt: vi.fn(() => new Promise<SuggestionReceipt>(resolve => { finish = resolve; })) };
    const input = props(service);
    const view = render(<SearchSuggestionPanel {...input} />);
    fireEvent.click(screen.getByRole("button", { name: "生成建议" }));
    await screen.findByText(preview.description);
    fireEvent.click(screen.getByRole("button", { name: "确认生成" }));
    await screen.findByText("设备预测性维护");
    fireEvent.click(screen.getByRole("button", { name: "合并新增建议" }));
    await waitFor(() => expect(service.getReceipt).toHaveBeenCalledOnce());
    view.unmount();
    await act(async () => finish(receipt(original)));
    expect(input.onApply).not.toHaveBeenCalled();
  });

  it("does not POST or replace bytes when storage becomes corrupt before confirmation", async () => {
    const key = "yike.search-suggestion.v1.user-a.space-a.1";
    const service = { preview: vi.fn().mockResolvedValue(preview), submit: vi.fn(), getReceipt: vi.fn() };
    render(<SearchSuggestionPanel {...props(service)} />);
    fireEvent.click(screen.getByRole("button", { name: "生成建议" }));
    await screen.findByText(preview.description);
    localStorage.setItem(key, "corrupt-original-bytes");
    fireEvent.click(screen.getByRole("button", { name: "确认生成" }));
    expect(await screen.findByText(/损坏|原请求/)).toBeTruthy();
    expect(service.submit).not.toHaveBeenCalled();
    expect(localStorage.getItem(key)).toBe("corrupt-original-bytes");
  });

  it("does not apply a late adopting GET after keeping current and ending", async () => {
    let finishGet!: (value: SuggestionReceipt) => void;
    let original!: SuggestionRequest;
    const service = { preview: vi.fn().mockResolvedValue(preview),
      submit: vi.fn(async (request: SuggestionRequest) => { original = request; return receipt(request); }),
      getReceipt: vi.fn(() => new Promise<SuggestionReceipt>(resolve => { finishGet = resolve; })) };
    const input = props(service);
    render(<SearchSuggestionPanel {...input} />);
    fireEvent.click(screen.getByRole("button", { name: "生成建议" }));
    await screen.findByText(preview.description);
    fireEvent.click(screen.getByRole("button", { name: "确认生成" }));
    await screen.findByText("设备预测性维护");
    fireEvent.click(screen.getByRole("button", { name: "合并新增建议" }));
    await waitFor(() => expect(service.getReceipt).toHaveBeenCalledOnce());
    fireEvent.click(screen.getByRole("button", { name: "保留当前并结束" }));
    await act(async () => finishGet(receipt(original)));
    expect(input.onApply).not.toHaveBeenCalled();
    expect(localStorage.length).toBe(0);
  });
});
