import {
  suggestionReceiptSchema,
  suggestionRequestSchema,
  type SuggestionReceipt,
  type SuggestionRequest,
} from "../../../shared/searchSuggestions";

const PREFIX = "yike.search-suggestion.v1";

export interface SearchSuggestionScope {
  userId: string;
  accountScopeId: string;
  accountScopeVersion: number;
}

export interface SearchSuggestionRecord {
  schemaVersion: 1;
  scope: SearchSuggestionScope;
  request: SuggestionRequest;
  receipt: SuggestionReceipt | null;
}

export type SearchSuggestionLoad =
  | { kind: "empty" }
  | { kind: "record"; record: SearchSuggestionRecord }
  | { kind: "error"; message: string };

const cleanPart = (value: string) => encodeURIComponent(value.trim());
export const searchSuggestionStorageKey = (scope: SearchSuggestionScope) =>
  `${PREFIX}.${cleanPart(scope.userId)}.${cleanPart(scope.accountScopeId)}.${scope.accountScopeVersion}`;

const object = (value: unknown): value is Record<string, unknown> =>
  !!value && typeof value === "object" && !Array.isArray(value);
const text = (value: unknown) => typeof value === "string" && !!value.trim();

function validScope(value: unknown): value is SearchSuggestionScope {
  return object(value) && text(value.userId) && text(value.accountScopeId) &&
    Number.isSafeInteger(value.accountScopeVersion) && Number(value.accountScopeVersion) >= 0;
}

function parseRecord(raw: string): SearchSuggestionRecord | null {
  let value: unknown;
  try { value = JSON.parse(raw); } catch { return null; }
  if (!object(value) || value.schemaVersion !== 1 || !validScope(value.scope)) return null;
  const request = suggestionRequestSchema.safeParse(value.request);
  const receipt = value.receipt === null
    ? { success: true as const, data: null }
    : suggestionReceiptSchema.safeParse(value.receipt);
  if (!request.success || !receipt.success) return null;
  if (receipt.data && (receipt.data.request_id !== request.data.request_id ||
      receipt.data.draft_id !== request.data.draft_id ||
      receipt.data.profile_version_id !== request.data.profile_version_id ||
      receipt.data.draft_revision !== request.data.draft_revision ||
      receipt.data.profile_sha256 !== request.data.disclosure.profile_sha256 ||
      receipt.data.model_provider !== request.data.disclosure.model_provider ||
      receipt.data.model_name !== request.data.disclosure.model_name ||
      receipt.data.disclosure_policy_version !== request.data.disclosure.policy_version)) return null;
  return { schemaVersion: 1, scope: value.scope, request: request.data, receipt: receipt.data };
}

function sameScope(a: SearchSuggestionScope, b: SearchSuggestionScope) {
  return a.userId === b.userId && a.accountScopeId === b.accountScopeId &&
    a.accountScopeVersion === b.accountScopeVersion;
}

export function loadSearchSuggestion(scope: SearchSuggestionScope): SearchSuggestionLoad {
  let raw: string | null;
  try { raw = localStorage.getItem(searchSuggestionStorageKey(scope)); }
  catch { return { kind: "error", message: "搜索建议记录无法读取，请检查本机存储。" }; }
  if (raw === null) return { kind: "empty" };
  const record = parseRecord(raw);
  if (!record || !sameScope(record.scope, scope))
    return { kind: "error", message: "搜索建议记录已损坏，未将其当作空记录。" };
  return { kind: "record", record };
}

export function saveSearchSuggestion(record: SearchSuggestionRecord): void {
  const key = searchSuggestionStorageKey(record.scope);
  const raw = JSON.stringify(record);
  const existing = loadSearchSuggestion(record.scope);
  if (existing.kind === "error")
    throw new Error(`${existing.message} 已保留原字节，不能覆盖或发送新请求。`);
  if (existing.kind === "empty" && record.receipt !== null)
    throw new Error("原搜索建议记录已结束，迟到回执不能重建原请求。");
  if (existing.kind === "record" &&
      JSON.stringify(existing.record.request) !== JSON.stringify(record.request))
    throw new Error("已有未结束的搜索建议原请求，不能被另一请求覆盖。");
  try {
    localStorage.setItem(key, raw);
    const stored = localStorage.getItem(key);
    if (stored !== raw || loadSearchSuggestion(record.scope).kind !== "record") throw new Error("readback");
  } catch {
    throw new Error("搜索建议原请求无法可靠保存，尚未发送给模型。");
  }
}

export function clearSearchSuggestion(scope: SearchSuggestionScope, requestId: string): boolean {
  const loaded = loadSearchSuggestion(scope);
  if (loaded.kind !== "record" || loaded.record.request.request_id !== requestId) return false;
  try { localStorage.removeItem(searchSuggestionStorageKey(scope)); }
  catch { return false; }
  return loadSearchSuggestion(scope).kind === "empty";
}
