import { Button } from "../../components/ui";
import type { CandidateRequestOperation } from "../../domain/candidateRequestOperation";
import "./candidateRequestHistory.css";

const actions: Record<CandidateRequestOperation["action"], string> = {
  ASSESS: "画像判断",
  VERIFY_SOURCE: "来源核验",
  INCLUDE: "确认入库",
  EXCLUDE: "排除线索",
};
const states: Record<CandidateRequestOperation["state"], { label: string; hint: string }> = {
  PENDING: { label: "结果待确认", hint: "请查看处理结果，暂勿重复操作。" },
  PROCESSING: { label: "处理中", hint: "服务仍在处理，可核对最新进度，无需重新提交。" },
  UNKNOWN: { label: "结果待确认", hint: "请稍后查看处理结果。" },
  FAILED: { label: "判断失败", hint: "可先核对失败结果，再确认是否重新判断。" },
  RECORDED: { label: "结果已返回", hint: "可查看处理结果。" },
};

export function CandidateRequestHistory({ operations, busy, onReconcile, onRetry }: {
  operations: CandidateRequestOperation[];
  busy: boolean;
  onReconcile: (key: string) => void;
  onRetry: (key: string) => void;
}) {
  return (
    <section aria-label="候选原请求记录" className="card candidate-request-history">
      <h3>处理记录</h3>
      {operations.some(operation=>operation.state==='FAILED')&&<p role="status">有判断失败，展开查看并处理。</p>}
      {operations.some(operation=>['PENDING','PROCESSING','UNKNOWN'].includes(operation.state))&&<p role="status">有操作尚待确认，可展开查看结果。</p>}
      <details>
      <summary>查看处理记录（{operations.length}）</summary>
      {operations.map((operation, index) => (
        <div key={operation.key} className="candidate-request-row">
          <span className="candidate-request-title">
            {actions[operation.action]} · {states[operation.state].label}
          </span>
          <p className="muted candidate-request-hint">{states[operation.state].hint}</p>
          <div className="action-row candidate-request-actions">
            <Button disabled={busy} onClick={() => onReconcile(operation.key)}>查看处理结果{operations.length > 1 ? ` · 记录 ${index + 1}` : ""}</Button>
            {operation.action === "ASSESS" && ["FAILED", "UNKNOWN"].includes(operation.state) &&
              !operations.some(child => child.retryOf[0] === (operation.invocationId ?? operation.requestId)) && (
                <Button disabled={busy} onClick={() => onRetry(operation.key)}>确认后重新判断{operations.length > 1 ? ` · 记录 ${index + 1}` : ""}</Button>
              )}
          </div>
        </div>
      ))}
      </details>
    </section>
  );
}
