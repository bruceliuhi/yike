import { useEffect, useRef, useState } from "react";
import { ArrowClockwise, Sparkle, X } from "@phosphor-icons/react";
import { boundedRequest, RequestCancelled } from "../../app/boundedRequest";
import { Badge, Button, Modal, Notice } from "../../components/ui";
import type { SuggestionReceipt, SuggestionRequest, SuggestionPreview } from "../../../shared/searchSuggestions";
import type { SearchSuggestionsService } from "../../services/searchSuggestions";
import { errorMessage } from "../../services/contracts";
import {
  clearSearchSuggestion,
  loadSearchSuggestion,
  saveSearchSuggestion,
  type SearchSuggestionRecord,
  type SearchSuggestionScope,
} from "./searchSuggestionStorage";

const REQUEST_MS = 10_000;
const TOTAL_WAIT_MS = 45_000;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const terminal = (receipt: SuggestionReceipt) => receipt.state === "SUCCEEDED" || receipt.state === "FAILED";
const sameRequest = (receipt: SuggestionReceipt, request: SuggestionRequest) =>
  receipt.request_id === request.request_id && receipt.draft_id === request.draft_id &&
  receipt.profile_version_id === request.profile_version_id && receipt.draft_revision === request.draft_revision &&
  receipt.profile_sha256 === request.disclosure.profile_sha256 &&
  receipt.model_provider === request.disclosure.model_provider &&
  receipt.model_name === request.disclosure.model_name &&
  receipt.disclosure_policy_version === request.disclosure.policy_version;

export interface SearchSuggestionPanelProps {
  service: SearchSuggestionsService;
  scope: SearchSuggestionScope | null;
  draftId: string;
  draftRevision: number;
  profileVersionId: string;
  profileConfirmed: boolean;
  hasTerms: boolean;
  onApply(receipt: SuggestionReceipt, mode: "append" | "replace_unedited"): boolean;
}

export function SearchSuggestionPanel(props: SearchSuggestionPanelProps) {
  const [preview, setPreview] = useState<SuggestionPreview | null>(null);
  const [record, setRecord] = useState<SearchSuggestionRecord | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const controller = useRef<AbortController | null>(null);
  const generation = useRef(0);
  const currentBinding = () => !!record && record.request.draft_id === props.draftId &&
    record.request.profile_version_id === props.profileVersionId;

  const persist = (next: SearchSuggestionRecord) => {
    saveSearchSuggestion(next);
    setRecord(next);
  };
  const waitForReceipt = async (base: SearchSuggestionRecord, initial?: SuggestionReceipt) => {
    const id = generation.current;
    const abort = controller.current!;
    const started = Date.now();
    let receipt = initial;
    while (true) {
      if (!receipt) receipt = await boundedRequest(() => props.service.getReceipt(base.request), {
        signal: abort.signal, timeoutMs: REQUEST_MS, timeoutMessage: "原搜索建议回执核对超时。",
      });
      if (id !== generation.current || abort.signal.aborted) return;
      if (!sameRequest(receipt, base.request)) throw new Error("搜索建议回执与原请求不一致，请核对原请求。");
      const next = { ...base, receipt };
      persist(next);
      if (terminal(receipt) || receipt.state === "UNKNOWN") return;
      if (Date.now() - started >= TOTAL_WAIT_MS) {
        setError("等待已到45秒，模型请求可能仍在处理；已保留原请求，只能继续核对，不能新建重试。");
        return;
      }
      await new Promise<void>((resolve, reject) => {
        const timer = window.setTimeout(resolve, 1000);
        abort.signal.addEventListener("abort", () => { window.clearTimeout(timer); reject(new RequestCancelled()); }, { once: true });
      });
      receipt = undefined;
    }
  };

  useEffect(() => {
    const id = ++generation.current;
    controller.current?.abort();
    controller.current = new AbortController();
    setPreview(null); setRecord(null); setError(""); setBusy(false);
    if (!props.scope) return;
    const loaded = loadSearchSuggestion(props.scope);
    if (loaded.kind === "error") { setError(loaded.message); return; }
    if (loaded.kind === "empty") return;
    setRecord(loaded.record);
    setBusy(true);
    void waitForReceipt(loaded.record).catch((reason) => {
      if (id === generation.current && !(reason instanceof RequestCancelled))
        setError(`原搜索建议结果尚无法核验：${errorMessage(reason)} 不会自动重新提交。`);
    }).finally(() => { if (id === generation.current) setBusy(false); });
    return () => { generation.current++; controller.current?.abort(); };
  }, [props.service, props.scope?.userId, props.scope?.accountScopeId, props.scope?.accountScopeVersion,
    props.draftId, props.profileVersionId]);

  const requestPreview = async () => {
    if (busy) return;
    if (!props.scope) { setError("请先登录有效客户工作空间。手工搜索词仍可继续编辑。"); return; }
    if (!props.profileConfirmed || !UUID.test(props.profileVersionId) || !UUID.test(props.draftId)) {
      setError("请选择已确认画像并使用有效草稿后再生成。手工搜索词仍可继续编辑。"); return;
    }
    if (record) {
      const id = generation.current;
      setBusy(true); setError("");
      void waitForReceipt(record).catch((reason) => {
        if (id === generation.current && !(reason instanceof RequestCancelled))
          setError(`原搜索建议结果尚无法核验：${errorMessage(reason)} 不会自动重新提交。`);
      }).finally(() => { if (id === generation.current) setBusy(false); });
      return;
    }
    const id = generation.current;
    setBusy(true); setError("");
    try {
      const value = await boundedRequest(() => props.service.preview(props.profileVersionId), {
        signal: controller.current?.signal, timeoutMs: REQUEST_MS, timeoutMessage: "搜索建议说明读取超时，尚未发送业务介绍。",
      });
      if (id === generation.current && value.profile_version_id === props.profileVersionId) setPreview(value);
    } catch (reason) { if (id === generation.current && !(reason instanceof RequestCancelled)) setError(errorMessage(reason)); }
    finally { if (id === generation.current) setBusy(false); }
  };

  const submit = async () => {
    if (!preview || !props.scope || busy) return;
    const request: SuggestionRequest = {
      request_id: crypto.randomUUID(), draft_id: props.draftId,
      profile_version_id: props.profileVersionId, draft_revision: props.draftRevision,
      disclosure: { accepted: true, profile_sha256: preview.profile_sha256,
        model_provider: preview.model_provider, model_name: preview.model_name,
        policy_version: preview.disclosure_policy_version },
    };
    const base: SearchSuggestionRecord = { schemaVersion: 1, scope: props.scope, request, receipt: null };
    try { persist(base); } catch (reason) { setError(errorMessage(reason)); return; }
    const id = generation.current;
    setPreview(null); setBusy(true); setError("");
    try {
      const receipt = await boundedRequest(() => props.service.submit(request), {
        signal: controller.current?.signal, timeoutMs: REQUEST_MS,
        timeoutMessage: "提交回执未收到；已保留原请求，只能核对，不能自动重新提交。",
      });
      if (id === generation.current) await waitForReceipt(base, receipt);
    } catch (reason) {
      if (id === generation.current && !(reason instanceof RequestCancelled))
        setError(`原搜索建议结果尚无法核验：${errorMessage(reason)} 不会自动重新提交。`);
    } finally { if (id === generation.current) setBusy(false); }
  };

  const cancel = () => {
    generation.current++; controller.current?.abort(); controller.current = new AbortController();
    setBusy(false); setPreview(null);
    setError("已停止本地等待；这不表示模型请求或费用已撤销。原请求仍保留供核对。");
  };
  const apply = async (mode: "append" | "replace_unedited") => {
    if (!record || !props.scope || busy) return;
    const id = generation.current; setBusy(true); setError("");
    try {
      const receipt = await boundedRequest(() => props.service.getReceipt(record.request), {
        signal: controller.current?.signal, timeoutMs: REQUEST_MS, timeoutMessage: "采用前核对回执超时，未修改当前草稿。",
      });
      if (id !== generation.current) return;
      persist({ ...record, receipt });
      if (!sameRequest(receipt, record.request) || receipt.state !== "SUCCEEDED" || !receipt.profile_current ||
          receipt.profile_version_id !== props.profileVersionId || receipt.draft_id !== props.draftId)
        throw new Error("原结果已过期或不属于当前草稿/画像，只能只读核对，不能采用。");
      if (!receipt.result || receipt.result.keywords.length > 20 || receipt.result.exclusions.length > 20)
        throw new Error("搜索建议词项无效或超过20个，未修改当前草稿。");
      if (props.onApply(receipt, mode) && clearSearchSuggestion(props.scope, record.request.request_id))
        setRecord(null);
    } catch (reason) { if (id === generation.current) setError(errorMessage(reason)); }
    finally { if (id === generation.current) setBusy(false); }
  };
  const finish = () => {
    if (!record || !props.scope || !record.receipt || !terminal(record.receipt)) return;
    if (clearSearchSuggestion(props.scope, record.request.request_id)) { setRecord(null); setError(""); }
    else setError("未能安全结束原搜索建议记录。");
  };

  const result = record?.receipt?.state === "SUCCEEDED" ? record.receipt.result : null;
  return <>
    <div className="search-heading"><div><h2>搜索条件</h2><Badge tone="blue"><Sparkle size={12} /> AI 建议</Badge></div>
      {busy ? <Button variant="ghost" onClick={cancel}><X />停止本地等待</Button>
        : <Button variant="ghost" onClick={() => void requestPreview()}><ArrowClockwise />
          {record ? "核对原请求" : props.hasTerms ? "重新生成" : "生成建议"}</Button>}
    </div>
    {error && <Notice tone="warning">{error}</Notice>}
    {record && <Notice tone={record.receipt?.state === "FAILED" ? "warning" : "info"}>
      原请求 {record.request.request_id} · {record.receipt?.state || "回执待核对"}
      {!currentBinding() && " · 历史草稿/画像，只读核对"}
      {record.receipt && terminal(record.receipt) && <Button variant="ghost" onClick={finish}>结束原请求</Button>}
    </Notice>}
    {preview && <Modal title="确认发送业务介绍" onClose={() => setPreview(null)} footer={<>
      <Button onClick={() => setPreview(null)}>暂不发送</Button>
      <Button variant="primary" onClick={() => void submit()}>我已核对，发送并生成</Button>
    </>}>
      <p>以下完整业务介绍将发送给受控模型，用于生成搜索关键词、排除词与建议原因；不会自动采集或发送。</p>
      <h3>完整业务介绍</h3><p style={{ whiteSpace: "pre-wrap" }}>{preview.description}</p>
      <p className="muted">模型：{preview.model_provider} / {preview.model_name} · 披露规则 {preview.disclosure_policy_version}</p>
    </Modal>}
    {result && <Modal title="核对搜索建议" onClose={() => undefined} footer={<>
      <Button onClick={finish}>保留当前并结束</Button>
      <Button onClick={() => void apply("replace_unedited")} disabled={!currentBinding() || !record?.receipt?.profile_current}>替换未修改的建议</Button>
      <Button variant="primary" onClick={() => void apply("append")} disabled={!currentBinding() || !record?.receipt?.profile_current}>合并新增建议</Button>
    </>}>
      <h3>搜索关键词</h3><div className="suggestion-list">{result.keywords.map(v => <span key={v}>{v}</span>)}</div>
      <h3>排除词</h3><div className="suggestion-list">{result.exclusions.map(v => <span key={v}>{v}</span>)}</div>
      <h3>建议原因</h3><p>{result.rationale}</p>
      <h3>依据</h3><ul>{result.evidence.map(v => <li key={v}>{v}</li>)}</ul>
      <h3>未知信息</h3>{result.unknowns.length ? <ul>{result.unknowns.map(v => <li key={v}>{v}</li>)}</ul> : <p>无</p>}
      {!record?.receipt?.profile_current && <Notice tone="warning">画像版本已变化；结果仅供历史核对，不能采用。</Notice>}
    </Modal>}
  </>;
}
