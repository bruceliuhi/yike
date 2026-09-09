import { z } from "zod";
import { explicitInstant } from "./opportunityLibrary";

const id = z
  .string()
  .trim()
  .min(1)
  .max(128)
  .refine((value) => !/[\u0000-\u001f\u007f]/.test(value));
const revision = z.number().int().positive().max(Number.MAX_SAFE_INTEGER);
/** Original, immutable scope for a new terminal-run follow-up draft. It is
 * provenance for deduplication, not authority to restart or reuse a quotation. */
export const coverageProvenanceSchema = z
  .object({
    kind: z.literal("NEW_DRAFT"),
    snapshotId: id,
    taskId: id,
    runId: id,
    unitId: id,
    profileId: id,
    profileVersion: revision,
    configurationRevision: revision,
    windowId: id,
    accountScopeId: id,
    scopeVersion: revision,
    userId: id,
    expiresAt: z.string().refine(explicitInstant),
    deduplicationVersion: id,
    budgetRevision: revision.nullable(),
    scopeSummary: z.string().trim().min(1).max(4000),
  })
  .strict();
export type CoverageProvenance = z.infer<typeof coverageProvenanceSchema>;
