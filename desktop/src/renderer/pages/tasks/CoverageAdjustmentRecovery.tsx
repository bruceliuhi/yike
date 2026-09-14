import { Button, Notice } from "../../components/ui";
import { useCoverageAdjustment } from "./useCoverageAdjustment";

export function CoverageAdjustmentRecovery({ taskId }: { taskId: string }) {
  const operation = useCoverageAdjustment(taskId);
  if (!operation.pending.length && !operation.error && !operation.applied)
    return null;
  return (
    <section aria-label="上限调整结果核对" className="coverage-plan-recovery">
      {operation.pending.map((key) => (
        <Notice
          key={key}
          tone="warning"
          action={
            <Button
              loading={operation.busy}
              onClick={() => void operation.reconcile(key)}
            >
              核对原上限调整
            </Button>
          }
        >
          搜贝上限调整结果待确认，请先查看结果。
        </Notice>
      ))}
      {operation.error && <Notice tone="warning">{operation.error}</Notice>}
      {operation.applied && (
        <Notice>原上限调整已确认，任务尚未恢复；请刷新运行状态。</Notice>
      )}
    </section>
  );
}
