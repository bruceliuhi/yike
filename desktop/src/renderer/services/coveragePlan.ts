import type {
  CoverageAdjustmentBinding,
  CoverageAdjustmentReceipt,
  CoveragePlanPreview,
  CoveragePreviewRequest,
} from "../domain/coveragePlan";

/** Optional authenticated service. Preview is read-only and must revalidate the
 * original run/window, confirmed recoverability and account scope. Adjust only
 * changes the quoted cap atomically at the expected budget revision; it never
 * resumes collection. The original request ID remains authoritative on retries.
 * Quotes and authorization tokens stay in memory, never in the operation ledger. */
export interface CoveragePlanService {
  preview(
    input: CoveragePreviewRequest,
    signal?: AbortSignal,
  ): Promise<CoveragePlanPreview>;
  adjust(input: {
    binding: CoverageAdjustmentBinding;
    preview: CoveragePlanPreview;
  }): Promise<CoverageAdjustmentReceipt>;
  reconcile(
    binding: CoverageAdjustmentBinding,
  ): Promise<CoverageAdjustmentReceipt>;
}
