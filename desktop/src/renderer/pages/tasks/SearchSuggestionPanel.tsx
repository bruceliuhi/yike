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
const sourceTypeLabels = {SOCIAL_POST:'需求主帖',COMMENT:'讨论评论',PROCUREMENT:'采购公告',COMPANY_UPDATE:'企业公开动态',INDUSTRY_SITE:'行业网站'};
const terminal = (receipt: SuggestionReceipt) => receipt.state === "SUCCEEDED" || receipt.state === "FAILED" || receipt.state === "NOT_SUBMITTED";
const rejectionReasons: Record<string,string> = {
  capability_unavailable:"建议服务当前不可用", disclosure_mismatch:"业务介绍或模型配置已变化，需要重新核对",
  profile_unavailable:"所选画像当前不可用，请重新确认", suggestion_busy:"建议服务正忙，请稍后再试",
  suggestion_rate_limited:"提交过于频繁，请稍后再试", suggestion_quota_exceeded:"本小时建议生成额度已用完，请稍后再试",
};
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
  onApplyStrategy?(receipt: SuggestionReceipt): boolean;
  hasStrategy?: boolean;
}

export function SearchSuggestionPanel(props: SearchSuggestionPanelProps) {
  const [preview, setPreview] = useState<SuggestionPreview | null>(null);
  const [previewBinding, setPreviewBinding] = useState("");
  const [record, setRecord] = useState<SearchSuggestionRecord | null>(null);
  const [error, setError] = useState("");
  const [storageBlocked, setStorageBlocked] = useState(false);
  const [busy, setBusy] = useState(false);
  const controller = useRef<AbortController | null>(null);
  const generation = useRef(0);
  const viewBinding = `${props.scope?.userId || ""}:${props.scope?.accountScopeId || ""}:${props.scope?.accountScopeVersion ?? ""}:${props.draftId}:${props.profileVersionId}`;
  const currentBinding = () => !!record && !!props.scope &&
    record.scope.userId === props.scope.userId && record.scope.accountScopeId === props.scope.accountScopeId &&
    record.scope.accountScopeVersion === props.scope.accountScopeVersion &&
    record.request.draft_id === props.draftId && record.request.profile_version_id === props.profileVersionId;
  const recordInScope = !!record && !!props.scope && record.scope.userId === props.scope.userId &&
    record.scope.accountScopeId === props.scope.accountScopeId &&
    record.scope.accountScopeVersion === props.scope.accountScopeVersion;

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
      if (!receipt) {
        const remaining = TOTAL_WAIT_MS - (Date.now() - started);
        if (remaining <= 0) {
          setError("等待已到45秒，模型请求可能仍在处理；已保留原请求，只能继续核对，不能新建重试。");
          return;
        }
        receipt = await boundedRequest(signal => props.service.getReceipt(base.request, signal), {
          signal: abort.signal, timeoutMs: Math.min(REQUEST_MS, remaining), timeoutMessage: "原搜索建议回执核对超时。",
        });
      }
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
    const cleanupEffect = () => { generation.current++; controller.current?.abort(); };
    setPreview(null); setPreviewBinding(""); setRecord(null); setError(""); setStorageBlocked(false); setBusy(false);
    if (!props.scope) return cleanupEffect;
    const loaded = loadSearchSuggestion(props.scope);
    if (loaded.kind === "error") { setStorageBlocked(true); setError(loaded.message); return cleanupEffect; }
    if (loaded.kind === "empty") return cleanupEffect;
    setRecord(loaded.record);
    setBusy(true);
    void waitForReceipt(loaded.record).catch((reason) => {
      if (id === generation.current && !(reason instanceof RequestCancelled))
        setError(`原搜索建议结果尚无法核验：${errorMessage(reason)} 不会自动重新提交。`);
    }).finally(() => { if (id === generation.current) setBusy(false); });
    return cleanupEffect;
  }, [props.service, props.scope?.userId, props.scope?.accountScopeId, props.scope?.accountScopeVersion,
    props.draftId, props.profileVersionId]);

  const requestPreview = async () => {
    if (busy) return;
    if (!props.scope) { setError("请先登录有效客户工作空间。手工搜索词仍可继续编辑。"); return; }
    if (!props.profileConfirmed || !UUID.test(props.profileVersionId) || !UUID.test(props.draftId)) {
      setError("请选择已确认画像并使用有效草稿后再生成。手工搜索词仍可继续编辑。"); return;
    }
    const durable = loadSearchSuggestion(props.scope);
    if (storageBlocked || durable.kind === "error") {
      setStorageBlocked(true);
      setError(durable.kind === "error" ? durable.message : "搜索建议本机存储异常，不能发送新请求。");
      return;
    }
    if (recordInScope && record) {
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
      const value = await boundedRequest(signal => props.service.preview(props.profileVersionId, signal), {
        signal: controller.current?.signal, timeoutMs: REQUEST_MS, timeoutMessage: "搜索建议说明读取超时，尚未发送业务介绍。",
      });
      if (id === generation.current && value.profile_version_id === props.profileVersionId) {
        setPreviewBinding(viewBinding); setPreview(value);
      }
    } catch (reason) { if (id === generation.current && !(reason instanceof RequestCancelled)) setError(errorMessage(reason)); }
    finally { if (id === generation.current) setBusy(false); }
  };

  const submit = async () => {
    if (!preview || previewBinding !== viewBinding || !props.scope || busy) return;
    const request: SuggestionRequest = {
      request_id: crypto.randomUUID(), draft_id: props.draftId,
      profile_version_id: props.profileVersionId, draft_revision: props.draftRevision,
      disclosure: { accepted: true, profile_sha256: preview.profile_sha256,
        model_provider: preview.model_provider, model_name: preview.model_name,
        policy_version: preview.disclosure_policy_version },
    };
    const base: SearchSuggestionRecord = { schemaVersion: 1, scope: props.scope, request, receipt: null };
    try { persist(base); } catch (reason) { setStorageBlocked(true); setError(errorMessage(reason)); return; }
    const id = generation.current;
    setPreview(null); setPreviewBinding(""); setBusy(true); setError("");
    try {
      const receipt = await boundedRequest(signal => props.service.submit(request, signal), {
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
    setBusy(false); setPreview(null); setPreviewBinding("");
    setError("已停止本地等待；这不表示模型请求或费用已撤销。原请求仍保留供核对。");
  };
  const apply = async (mode: "append" | "replace_unedited" | "strategy") => {
    if (!record || !props.scope || busy) return;
    const id = generation.current; setBusy(true); setError("");
    try {
      const receipt = await boundedRequest(signal => props.service.getReceipt(record.request, signal), {
        signal: controller.current?.signal, timeoutMs: REQUEST_MS, timeoutMessage: "采用前核对回执超时，未修改当前草稿。",
      });
      if (id !== generation.current) return;
      persist({ ...record, receipt });
      if (!sameRequest(receipt, record.request) || receipt.state !== "SUCCEEDED" || !receipt.profile_current ||
          receipt.profile_version_id !== props.profileVersionId || receipt.draft_id !== props.draftId)
        throw new Error("原结果已过期或不属于当前草稿/画像，只能只读核对，不能采用。");
      if (!receipt.result || receipt.result.keywords.length > 20 || receipt.result.exclusions.length > 20)
        throw new Error("搜索建议词项无效或超过20个，未修改当前草稿。");
      if(mode==='strategy') {
        if(!props.onApplyStrategy?.(receipt))setError('当前已有任务策略或结果不适用；保留原策略，请先在表单核对或明确移除。');
        return; // Keep the receipt so keyword adoption remains a separate explicit action.
      }
      if (props.onApply(receipt, mode) && clearSearchSuggestion(props.scope, record.request.request_id))
        setRecord(null);
    } catch (reason) { if (id === generation.current) setError(errorMessage(reason)); }
    finally { if (id === generation.current) setBusy(false); }
  };
  const finish = () => {
    if (!record || !props.scope || !record.receipt || !terminal(record.receipt)) return;
    generation.current++;
    controller.current?.abort();
    controller.current = new AbortController();
    setBusy(false);
    if (clearSearchSuggestion(props.scope, record.request.request_id)) { setRecord(null); setError(""); setStorageBlocked(false); }
    else setError("未能安全结束原搜索建议记录。");
  };

  const result = recordInScope && record?.receipt?.state === "SUCCEEDED" ? record.receipt.result : null;
  return <>
    <div className="search-heading"><div><h2>搜索条件</h2><Badge tone="blue"><Sparkle size={12} /> AI 建议</Badge></div>
      {busy ? <Button variant="ghost" onClick={cancel}><X />停止本地等待</Button>
        : <Button variant="ghost" onClick={() => void requestPreview()}><ArrowClockwise />
          {recordInScope ? "核对原请求" : props.hasTerms ? "重新生成" : "生成建议"}</Button>}
    </div>
    {error && <Notice tone="warning">{error}</Notice>}
    {record && record.scope.userId === props.scope?.userId && record.scope.accountScopeId === props.scope?.accountScopeId &&
      record.scope.accountScopeVersion === props.scope?.accountScopeVersion && <Notice tone={record.receipt?.state === "FAILED" ? "warning" : "info"}>
      原请求 {record.request.request_id} · {record.receipt?.state || "回执待核对"}
      {record.receipt?.state === "NOT_SUBMITTED" && <p>
        服务端已确认未受理，未调用模型。{rejectionReasons[record.receipt.error_code || ""]}
        。结束原请求后，可重新核对业务介绍并决定是否生成；不会自动重试。
      </p>}
      {!currentBinding() && " · 历史草稿/画像，只读核对"}
      {record.receipt && terminal(record.receipt) && <Button variant="ghost" onClick={finish}>
        {record.receipt.state === "NOT_SUBMITTED" ? "结束未受理请求" : "结束原请求"}
      </Button>}
    </Notice>}
    {preview && previewBinding === viewBinding && <Modal title="确认发送业务介绍" onClose={() => { setPreview(null); setPreviewBinding(""); }} footer={<>
      <Button onClick={() => setPreview(null)}>暂不发送</Button>
      <Button variant="primary" onClick={() => void submit()}>我已核对，发送并生成</Button>
    </>}>
      <p>以下完整业务介绍将发送给受控模型，用于生成搜索关键词、排除词与行业策略建议；不会自动采集或发送。</p>
      <h3>完整业务介绍</h3><p style={{ whiteSpace: "pre-wrap" }}>{preview.description}</p>
      <p className="muted">模型：{preview.model_provider} / {preview.model_name} · 披露规则 {preview.disclosure_policy_version}</p>
    </Modal>}
    {result && <Modal title="核对搜索建议" onClose={() => undefined} footer={<>
      <Button onClick={finish}>保留当前并结束</Button>
      <Button onClick={() => void apply("replace_unedited")} disabled={!currentBinding() || !record?.receipt?.profile_current}>替换未修改的建议</Button>
      <Button variant="primary" onClick={() => void apply("append")} disabled={!currentBinding() || !record?.receipt?.profile_current}>合并新增建议</Button>
    </>}>
      {result.strategy&&<section aria-label="行业搜索策略">
        <h3>行业搜索策略</h3><Badge tone="blue">策略建议，尚未执行</Badge>
        <dl className="detail-list">
          <div><dt>画像中的买方角色</dt><dd>{result.strategy.buyerRole??'画像未说明'}</dd></div>
          <div><dt>画像中的销售方式</dt><dd>{result.strategy.salesMotion??'画像未说明'}</dd></div>
        </dl>
        <h4>建议查看的内容类型</h4><ul>{result.strategy.sourceTypes.map(type=><li key={type}>{sourceTypeLabels[type]}</li>)}</ul>
        <p className="muted">内容类型不代表平台已接入。词项合并/替换只更新搜索词；任务策略需单独采用，不会开启新平台、增加预算或自动联系。</p>
        {props.onApplyStrategy&&<Button disabled={busy||props.hasStrategy||!currentBinding()||!record?.receipt?.profile_current}
          onClick={()=>void apply('strategy')}>{props.hasStrategy?'已有任务策略，请在表单编辑':'采用任务策略'}</Button>}
        <h4>寻找这些购买信号</h4><ul>{result.strategy.intentSignals.map((value,index)=><li key={index}>{value}</li>)}</ul>
        <h4>留意这些反例</h4>{result.strategy.counterSignals.length?<ul>{result.strategy.counterSignals.map((value,index)=><li key={index}>{value}</li>)}</ul>:<p>暂未提出，仍需人工判断。</p>}
        <h4>策略的画像依据</h4><ul>{result.strategy.basis.map((value,index)=><li key={index}>{value}</li>)}</ul>
        <p className="muted">策略版本：{result.strategy.version}</p>
      </section>}
      <h3>搜索关键词</h3><div className="suggestion-list">{result.keywords.map(v => <span key={v}>{v}</span>)}</div>
      <h3>排除词</h3><div className="suggestion-list">{result.exclusions.map(v => <span key={v}>{v}</span>)}</div>
      <h3>建议原因</h3><p>{result.rationale}</p>
      <h3>依据</h3><ul>{result.evidence.map(v => <li key={v}>{v}</li>)}</ul>
      <h3>未知信息</h3>{result.unknowns.length ? <ul>{result.unknowns.map(v => <li key={v}>{v}</li>)}</ul> : <p>无</p>}
      {!record?.receipt?.profile_current && <Notice tone="warning">画像版本已变化；结果仅供历史核对，不能采用。</Notice>}
    </Modal>}
  </>;
}
