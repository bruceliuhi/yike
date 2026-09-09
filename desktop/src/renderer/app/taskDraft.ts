import { z } from "zod";
import { useLocalDraft } from "./hooks";
import { newTaskDraft, type TaskDraft } from "../domain/models";
const term = z.object({
  id: z.string(),
  value: z.string(),
  origin: z.enum(["ai", "manual"]),
  edited: z.boolean(),
});
export const taskDraftSchema = z.object({
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
) {
  return useLocalDraft<TaskDraft>(
    "task." + (userId || "guest"),
    () => newTaskDraft(mode),
    (value) => taskDraftSchema.safeParse(value).success,
  );
}
export function useTaskLibrary(userId?: string) {
  return useLocalDraft<TaskDraft[]>(
    "task-library." + (userId || "guest"),
    [],
    (value) => z.array(taskDraftSchema).safeParse(value).success,
  );
}
