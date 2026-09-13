import { useEffect, useRef, useState } from "react";
import { useApp } from "../../app/context";
import { useAction } from "../../app/hooks";
import { useOperationLedger } from "../../app/operationLedger";
import { boundedRequest } from "../../app/boundedRequest";
import { Button, Modal, Notice } from "../../components/ui";
import type { TaskAction, TaskRun } from "../../domain/models";
import {
  actionEntry,
  hashText,
  parseActionReceipt,
  readActionEntry,
  taskActionFingerprint,
  taskActionsFor,
  taskRunSchema,
  type TaskActionBinding,
  type TaskActionReceipt,
} from "../../domain/taskOperations";
import { requireTaskOperations } from "../../services/taskOperations";
import { useTaskScope } from "./useTaskScope";
import "./tasks.css";

const labels: Record<TaskAction, string> = {
  pause: "暂停",
  resume: "恢复",
  retry: "重试",
  cancel: "取消",
};
const hints: Record<TaskAction, string> = {
  pause: "暂停后停止安排新执行，正在运行的阶段以服务端确认结果为准。",
  resume: "恢复前重新检查当前任务、账号、设备及调度条件。",
  retry: "仅重试服务端确认可重试的当前任务，不另建新任务。",
  cancel: "取消当前任务后不再安排执行，已经采集的记录不会删除。",
};
export function useTaskActions(runs: TaskRun[], onRun: (run: TaskRun) => void) {
  const { service, session, route, notify } = useApp();
  const scope = useTaskScope(route.path);
  const currentRuns = useRef(runs);
  currentRuns.current = runs;
  const [entries, setEntries] = useOperationLedger(
    "task-operations",
    session.userId,
  );
  const [pending, setPending] = useState<{
    run: TaskRun;
    action: TaskAction;
    identity: object;
  } | null>(null);
  const action = useAction();
  const checks = useAction();
  useEffect(() => {
    setPending(null);
    action.setError("");
    checks.setError("");
  }, [scope.identity]);
  const records = Object.entries(entries).map(([key]) => ({
    key,
    binding: readActionEntry(key),
  }));
  const blockedTaskIds = new Set(
    records.map((row) => row.binding?.taskId).filter(Boolean),
  );
  const settle = (receipt: TaskActionReceipt, key: string) => {
    if (receipt.status === "APPLIED" || receipt.status === "REJECTED") {
      setEntries((old) => {
        const next = { ...old };
        delete next[key];
        return next;
      });
      if (scope.current()) {
        if (receipt.status === "APPLIED") {
          onRun(receipt.run);
          notify(`${labels[receipt.action]}操作已确认完成。`, "success");
        } else
          notify(
            receipt.message || "原操作已确认未执行，请刷新任务后再决定下一步。",
            "info",
          );
        setPending(null);
      }
    } else if (scope.current())
      notify("操作结果尚待确认，请核对原操作，勿重复提交。", "info");
  };
  const open = (run: TaskRun, next: TaskAction) => {
    if (
      !session.authenticated ||
      blockedTaskIds.has(run.id) ||
      !taskActionsFor(run.status).includes(next)
    )
      return;
    action.setError("");
    setPending({
      run: structuredClone(run),
      action: next,
      identity: scope.identity,
    });
  };
  const perform = async () => {
    if (
      !pending ||
      pending.identity !== scope.identity ||
      !scope.current() ||
      !session.authenticated ||
      blockedTaskIds.has(pending.run.id)
    )
      return;
    const snapshot = pending;
    await action.run(async () => {
      try {
        const operations = requireTaskOperations(service.taskOperations);
        const original = taskActionFingerprint(snapshot.run);
        const fresh = taskRunSchema.parse(
          await boundedRequest(() => operations.task(snapshot.run.id), {
            timeoutMessage: "任务状态检查超时，尚未提交操作，请刷新后重试。",
          }),
        );
        const current = currentRuns.current.find(
          (run) => run.id === snapshot.run.id,
        );
        if (!scope.current()) return;
        if (
          !current ||
          taskActionFingerprint(current) !== original ||
          taskActionFingerprint(fresh) !== original ||
          !taskActionsFor(fresh.status).includes(snapshot.action)
        )
          throw new Error("任务状态已变化，请关闭确认窗口并刷新任务后重试。");
        const expectedHash = await hashText(original);
        if (!scope.current()) return;
        const binding: TaskActionBinding = {
          taskId: snapshot.run.id,
          action: snapshot.action,
          expectedHash,
          requestId: crypto.randomUUID(),
        };
        const key = actionEntry(binding);
        setEntries((old) => {
          if (
            Object.keys(old).some(
              (value) => readActionEntry(value)?.taskId === binding.taskId,
            )
          )
            throw new Error("该任务已有操作待核对，当前没有重复提交。");
          return { ...old, [key]: "PENDING" };
        });
        try {
          settle(
            parseActionReceipt(
              await boundedRequest(() => operations.action(binding), {
                timeoutMessage:
                  "任务操作等待超时，结果尚未确认，请核对原操作。",
              }),
              binding,
            ),
            key,
          );
        } catch {
          if (scope.current())
            throw new Error(
              "任务操作结果尚未确认，已保留原请求，请核对原操作。",
            );
        }
      } catch (error) {
        if (scope.current()) throw error;
      }
    });
  };
  const reconcile = async (key: string, binding: TaskActionBinding) => {
    await checks.run(async () => {
      try {
        settle(
          parseActionReceipt(
            await boundedRequest(
              () =>
                requireTaskOperations(service.taskOperations).reconcileAction(
                  binding,
                ),
              { timeoutMessage: "任务操作核对超时，原请求保护继续保留。" },
            ),
            binding,
          ),
          key,
        );
      } catch (error) {
        if (scope.current()) throw error;
      }
    });
  };
  return {
    open,
    busy: action.busy || checks.busy,
    blockedTaskIds,
    dialog: pending && pending.identity === scope.identity && (
      <Modal
        title={`${labels[pending.action]}任务？`}
        size="small"
        onClose={() => {
          if (!action.busy) setPending(null);
        }}
        footer={
          <>
            <Button disabled={action.busy} onClick={() => setPending(null)}>
              取消
            </Button>
            <Button
              variant={pending.action === "cancel" ? "danger" : "primary"}
              loading={action.busy}
              disabled={blockedTaskIds.has(pending.run.id)}
              onClick={() => void perform()}
            >
              确认
            </Button>
          </>
        }
      >
        <p>{pending.run.name}</p>
        <p className="field-hint">{hints[pending.action]}</p>
        {blockedTaskIds.has(pending.run.id) && (
          <Notice tone="warning">该任务原操作尚未确定，请返回列表核对。</Notice>
        )}
        {action.error && <Notice tone="error">{action.error}</Notice>}
      </Modal>
    ),
    recovery: session.authenticated && !!records.length && (
      <section className="task-recovery" aria-label="任务操作核对">
        <h2>任务操作待确认</h2>
        {[...records].sort((a,b)=>a.key.localeCompare(b.key)).map(
          ({ key, binding },index) =>
            binding && (
              <div className="task-recovery-row" key={key}>
                <div>
                  <strong>
                    {runs.find((run) => run.id === binding.taskId)?.name || "待核对任务"}{records.length>1?` · 记录 ${index+1}`:''}
                  </strong>
                  <p className="field-hint">
                    {labels[binding.action]}结果待确认
                  </p>
                </div>
                <Button
                  disabled={action.busy}
                  loading={checks.busy}
                  onClick={() => void reconcile(key, binding)}
                >
                  核对原操作
                </Button>
              </div>
            ),
        )}
        {checks.error && <Notice tone="error">{checks.error}</Notice>}
      </section>
    ),
  };
}
