import { Button, Notice } from "../../components/ui";
import type { CandidateReviewOperation } from "../../domain/candidateReviewOperation";

/** Keeps an original request reachable even when its candidate left the current filter. */
export function PendingCandidateReviews({
  records,
  visibleIds,
  busy,
  onReconcile,
}: {
  records: CandidateReviewOperation[];
  visibleIds: string[];
  busy: boolean;
  onReconcile(record: CandidateReviewOperation): void;
}) {
  const hidden = records.filter(
    (record) => !visibleIds.includes(record.candidateId),
  );
  if (!hidden.length) return null;
  return (
    <section aria-label="待核对候选复核">
      {hidden.map((record) => (
        <Notice
          key={record.key}
          tone="warning"
          action={
            <Button disabled={busy} onClick={() => onReconcile(record)}>
              核对原复核结果
            </Button>
          }
        >
          线索 {record.candidateId} 有一次
          {record.action === "INCLUDE" ? "入库" : "排除"}复核待核对。
        </Notice>
      ))}
    </section>
  );
}
