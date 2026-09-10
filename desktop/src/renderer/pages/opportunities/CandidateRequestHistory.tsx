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
  PENDING: { label: "结果待确认", hint: "尚未收到确定回执，请先核对原请求，避免重复操作。" },
  PROCESSING: { label: "处理中", hint: "服务仍在处理，可核对最新进度，无需重新提交。" },
  UNKNOWN: { label: "结果未知", hint: "暂时无法确认执行结果，请先核对原请求。" },
  FAILED: { label: "判断失败", hint: "可先核对失败结果，再确认是否重新判断。" },
  RECORDED: { label: "已取得回执", hint: "已收到原操作回执，具体结论以对应记录为准。" },
};

export function CandidateRequestHistory({ operations, busy, onReconcile, onRetry }: {
  operations: CandidateRequestOperation[];
  busy: boolean;
  onReconcile: (key: string) => void;
  onRetry: (key: string) => void;
}) {
  return (
    <section aria-label="候选原请求记录" className="card candidate-request-history">
      <h3>操作进度与结果核对</h3>
      <p className="muted">切换筛选后仍可核对。核对操作不会重新判断或重复入库。</p>
      {operations.map(operation => (
        <div key={operation.key} className="candidate-request-row">
          <span className="candidate-request-title">
            {actions[operation.action]} · {states[operation.state].label}
          </span>
          <p className="muted candidate-request-hint">{states[operation.state].hint}</p>
          <details className="candidate-request-reference">
            <summary>查看请求编号</summary>
            <p>{operation.requestId}</p>
          </details>
          <div className="action-row candidate-request-actions">
            <Button disabled={busy} onClick={() => onReconcile(operation.key)}>核对原请求</Button>
            {operation.action === "ASSESS" && ["FAILED", "UNKNOWN"].includes(operation.state) &&
              !operations.some(child => child.retryOf[0] === (operation.invocationId ?? operation.requestId)) && (
                <Button disabled={busy} onClick={() => onRetry(operation.key)}>确认后重新判断</Button>
              )}
          </div>
        </div>
      ))}
    </section>
  );
}
