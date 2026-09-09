import { z } from "zod";
import { useLocalDraft } from "./hooks";
import { newTaskDraft, type TaskDraft } from "../domain/models";
import { defaultResearchSettings, researchDraftSchema } from "../domain/researchUsage";
const term = z.object({
  id: z.string(),
  value: z.string(),
  origin: z.enum(["ai", "manual"]),
  edited: z.boolean(),
});
export const taskDraftSchema = z.object({
  research: researchDraftSchema.optional(),
  templateSourceDraftIds: z
    .array(z.string().min(1).max(512).refine(id => id.trim() === id))
    .max(50)
    .refine((ids) => new Set(ids).size === ids.length)
    .optional(),
  id: z.string(),
  revision: z.number(),
  name: z.string(),
  profileId: z.string(),
  profileVersion: z.number().nullable(),
  terms: z.array(term),
  exclusions: z.array(term),
  removed: z.array(z.string()),
  source: z.enum(["search", "links"]),
  links: z.string(),
  platforms: z.array(z.enum(["xhs", "douyin", "bilibili", "zhihu", "web"])),
  accounts: z.record(z.string(), z.string()),
  mode: z.enum(["once", "monitor"]),
  schedule: z.object({
    kind: z.enum(["daily", "interval"]),
    times: z.array(z.string()),
    interval: z.number(),
    start: z.string(),
    end: z.string(),
    timezone: z.string(),
  }),
  savedAt: z.string().nullable(),
  suggestionProfile: z.string().nullable(),
});
export function useTaskDraft(
  userId?: string,
  mode: "once" | "monitor" = "once",
  scope?: { id: string; version: number },
) {
  return useLocalDraft<TaskDraft>(
    "task." + taskDraftOwner(userId, scope),
    () => ({ ...newTaskDraft(mode), research: defaultResearchSettings() }),
    (value) => taskDraftSchema.safeParse(value).success,
  );
}
export function taskDraftOwner(userId?: string, scope?: { id: string; version: number }) {
  return scope ? JSON.stringify([userId || "guest", scope.id, scope.version]) : userId || "guest";
}
export function useTaskLibrary(userId?: string, scope?: { id: string; version: number }) {
  return useLocalDraft<TaskDraft[]>(
    "task-library." + taskDraftOwner(userId, scope),
    [],
    (value) => z.array(taskDraftSchema).safeParse(value).success,
  );
}
