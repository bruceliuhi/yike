import { useEffect, useState } from "react";
import { useApp } from "../../app/context";
import { useAction } from "../../app/hooks";
import { useOperationLedger } from "../../app/operationLedger";
import { boundedRequest } from "../../app/boundedRequest";
import { Button, Notice } from "../../components/ui";
import {
  parseStartReceipt,
  readStartEntry,
  type TaskStartLookup,
} from "../../domain/taskOperations";
import type { TaskRun } from "../../domain/models";
import { requireTaskOperations } from "../../services/taskOperations";
import { useTaskScope } from "./useTaskScope";
import "./tasks.css";

export function PendingTaskStarts({
  draftId,
  mode,
  onSettled,
  onAccepted,
}: {
  draftId?: string;
  mode?: "once" | "monitor";
  onSettled?: (
    status: "ACCEPTED" | "REJECTED",
    original: TaskStartLookup,
  ) => void;
  onAccepted?: (run: TaskRun) => void;
}) {
  const { service, session, notify, navigate } = useApp();
  const [entries, setEntries] = useOperationLedger(
    "unknown-task-starts",
    session.userId,
  );
  const [resolved, setResolved] = useState<{
    run: TaskRun;
    identity: object;
  } | null>(null);
  const action = useAction();
  const scope = useTaskScope(draftId || mode || "all");
  useEffect(() => {
    setResolved(null);
    action.setError("");
  }, [scope.identity]);
  const records = Object.entries(entries)
    .map(([id, value]) => ({ id, value, binding: readStartEntry(id, value) }))
    .filter(
      (row) =>
        (!draftId || row.id === draftId) &&
        (!mode || !row.binding?.mode || row.binding.mode === mode),
    );
  const owns = (binding?: TaskStartLookup) => !binding?.usageReservation || (
    binding.usageReservation.accountScopeId === session.accountScope?.id &&
    binding.usageReservation.accountScopeVersion === session.accountScope?.version);
  if (!session.authenticated || (!records.length && !resolved)) return null;
  const reconcile = async (id: string, originalValue: string) => {
    const original = readStartEntry(id, originalValue);
    if (!original || !owns(original)) return;
    await action.run(async () => {
      try {
        const receipt = parseStartReceipt(
          await boundedRequest(
            () =>
              requireTaskOperations(service.taskOperations).reconcileStart(
                original,
              ),
            {
              timeoutMessage: "原启动请求核对超时，保护继续保留，请稍后核对。",
            },
          ),
          original,
        );
        if (!scope.current()) return;
        if (receipt.status === "ACCEPTED" || receipt.status === "REJECTED") {
          setEntries((old) => {
            const next = { ...old };
            if (next[id] === originalValue) delete next[id];
            return next;
          });
          if (!scope.current()) return;
          onSettled?.(receipt.status, original);
          if (receipt.status === "ACCEPTED") {
            setResolved({ run: receipt.run, identity: scope.identity });
            notify("原请求已确认创建任务，没有再次启动。", "success");
            onAccepted?.(receipt.run);
          } else
            notify(
              receipt.message ||
                "原请求已确认未创建任务，请重新检查配置后再启动。",
              "info",
            );
        } else if (scope.current())
          notify("原启动请求结果仍未确定，保护继续保留。", "info");
      } catch (error) {
        if (scope.current()) throw error;
      }
    });
  };
  return (
    <section className="task-recovery" aria-label="启动结果核对">
      {!!records.length && (
        <>
          <h2>启动结果待确认</h2>
          <p className="field-hint">仅查询原请求，不会重新创建任务。</p>
        </>
      )}
      {records.map((row) => (
        <div className="task-recovery-row" key={row.id}>
          <div>
            <strong>原请求</strong>
            {row.binding ? <details><summary>请求详情</summary>
              <p className="task-request-id">{row.binding.requestId}</p>
              <p>配置版本 {row.binding.revision}</p>
            </details> : <p className="task-request-id">请求记录无法读取</p>}
            {row.binding && (
              <span className="field-hint">
                {!owns(row.binding) ? "请切回原客户空间核对 · " : ""}
                {row.binding.mode
                  ? (row.binding.mode === "monitor" ? "持续监控" : "单次采集")
                  : "旧版记录"}
              </span>
            )}
          </div>
          <Button
            loading={action.busy}
            disabled={!row.binding || !owns(row.binding)}
            onClick={() => void reconcile(row.id, row.value)}
          >
            核对原启动结果
          </Button>
        </div>
      ))}
      {action.error && <Notice tone="error">{action.error}</Notice>}
      {resolved && resolved.identity === scope.identity && (
        <Notice
          tone="success"
          action={
            <Button
              onClick={() =>
                navigate(
                  resolved.run.mode === "monitor"
                    ? `/monitors/${encodeURIComponent(resolved.run.id)}`
                    : "/collection",
                )
              }
            >
              查看任务
            </Button>
          }
        >
          已核对任务：{resolved.run.name}
        </Notice>
      )}
    </section>
  );
}
