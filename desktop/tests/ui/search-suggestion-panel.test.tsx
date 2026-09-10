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

  it("does not send on mount and submits once only after full disclosure confirmation", async () => {
    const service = { preview: vi.fn().mockResolvedValue(preview),
      submit: vi.fn(async (request: SuggestionRequest) => receipt(request)), getReceipt: vi.fn() };
    render(<SearchSuggestionPanel {...props(service)} />);
    expect(service.preview).not.toHaveBeenCalled(); expect(service.submit).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "生成建议" }));
    expect(await screen.findByText(preview.description)).toBeTruthy();
    expect(screen.getByText(/controlled-provider \/ controlled-model/)).toBeTruthy();
    expect(service.submit).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "我已核对，发送并生成" }));
    await waitFor(() => expect(service.submit).toHaveBeenCalledOnce());
    expect(await screen.findByText("设备预测性维护")).toBeTruthy();
  });

  it("does not POST when the original request cannot be durably stored", async () => {
    const service = { preview: vi.fn().mockResolvedValue(preview), submit: vi.fn(), getReceipt: vi.fn() };
    render(<SearchSuggestionPanel {...props(service)} />);
    fireEvent.click(screen.getByRole("button", { name: "生成建议" }));
    await screen.findByText(preview.description);
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new DOMException("full", "QuotaExceededError"); });
    fireEvent.click(screen.getByRole("button", { name: "我已核对，发送并生成" }));
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
    expect(screen.queryByRole("dialog", { name: "确认发送业务介绍" })).toBeNull();
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
    expect(service.getReceipt).toHaveBeenCalledWith(request);
    expect(service.submit).not.toHaveBeenCalled();
    expect(screen.getByText(/历史草稿\/画像，只读核对/)).toBeTruthy();
    expect((screen.getByRole("button", { name: "合并新增建议" }) as HTMLButtonElement).disabled).toBe(true);
  });
});
