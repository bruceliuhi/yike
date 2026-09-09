import { z } from "zod";
import { taskDraftSchema } from "../../app/taskDraft";
import { newTaskDraft, type TaskDraft } from "../../domain/models";
import { researchDraftSchema } from "../../domain/researchUsage";
const sourceId = z.string().min(1).max(512).refine(id => id.trim() === id);
export const templateSources = z
  .array(sourceId)
  .min(1)
  .max(50)
  .refine((values) => new Set(values).size === values.length);
// A reusable template carries editable limits, never a prior quote, request,
// source-bound suggestion or run snapshot. Keep valid unfinished inputs too;
// the normal estimate/start validation still applies to each new draft.
const researchConditions = researchDraftSchema
  .pick({
    version: true,
    demandTypes: true,
    maxSoubei: true,
    limits: true,
    stopAtAnyLimit: true,
    evidenceOrder: true,
  })
  .extend({ limits: researchDraftSchema.shape.limits.strip() })
  .strip();
// Explicitly omit identity, revision, saving metadata and every runtime field.
const conditions = taskDraftSchema.pick({
  name: true,
  profileId: true,
  profileVersion: true,
  terms: true,
  exclusions: true,
  removed: true,
  source: true,
  links: true,
  platforms: true,
  accounts: true,
  mode: true,
  schedule: true,
  suggestionProfile: true,
}).extend({
  research: researchConditions.optional(),
  executionLimits: taskDraftSchema.shape.executionLimits,
});
export const localTemplateSchema = z.object({
  id: sourceId,
  name: z.string().trim().min(1).max(60),
  sourceDraftIds: templateSources,
  savedAt: z.string().datetime(),
  conditions,
});
export type LocalTaskTemplate = z.infer<typeof localTemplateSchema>;
export const localTemplatesSchema = z
  .array(localTemplateSchema)
  .max(50)
  .refine((rows) => new Set(rows.map((row) => row.id)).size === rows.length);
export function draftSourceIds(draft: TaskDraft): string[] {
  const ancestors = draft.templateSourceDraftIds || [];
  return templateSources.parse([...new Set([...ancestors, draft.id])]);
}
export function templateFromDraft(
  draft: TaskDraft,
  name: string,
): LocalTaskTemplate {
  const value = {
    id: crypto.randomUUID(),
    name,
    sourceDraftIds: draftSourceIds(draft),
    savedAt: new Date().toISOString(),
    conditions: conditions.parse(draft),
  };
  return localTemplateSchema.parse(value);
}
export function draftFromTemplate(template: LocalTaskTemplate): TaskDraft {
  const checked = localTemplateSchema.parse(template);
  return {
    ...newTaskDraft(checked.conditions.mode),
    ...structuredClone(checked.conditions),
    templateSourceDraftIds: [...checked.sourceDraftIds],
  };
}
