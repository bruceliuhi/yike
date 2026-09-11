import { z } from "zod";
import { deviceUuidSchema as uuid } from "./deviceRegistration";
export const taskFeedQuerySchema = z
  .object({
    limit: z.number().int().min(1).max(50).optional(),
    cursor: z.string().min(1).max(1024).optional(),
  })
  .strict();
export const taskFeedGetSchema = z.object({ taskId: uuid }).strict();
const status = z.enum([
  "PENDING",
  "RUNNING",
  "CANCELLING",
  "CANCELED",
  "SUCCEEDED",
]);
const count = z.number().int().min(0).max(2147483647);
const platform = z
  .object({
    platform_run_id: uuid,
    platform: z.enum([
      "XIAOHONGSHU",
      "DOUYIN",
      "BILIBILI",
      "ZHIHU",
      "PUBLIC_WEB",
    ]),
    status,
    execution_generation: count,
    records_used: count,
  })
  .strict();
export const taskFeedItemSchema = z
  .object({
    task_id: uuid,
    run_id: uuid,
    device_id: uuid,
    profile_version_id: uuid,
    profile_version: z.number().int().positive().max(Number.MAX_SAFE_INTEGER).optional(),
    strategy_version_id: uuid,
    start_request_id: uuid,
    name: z.string().min(1).max(60).nullable(),
    mode: z.enum(["once", "monitor"]).nullable(),
    created_at: z.string().datetime({ offset: true }),
    deadline_at: z.string().datetime({ offset: true }),
    status,
    max_records: z.number().int().min(1).max(10000),
    records_used: count,
    stop_confirmed: z.boolean(),
    platform_runs: z.array(platform).min(1).max(5),
  })
  .strict()
  .superRefine((item, ctx) => {
    if (
      item.records_used !==
        item.platform_runs.reduce((n, row) => n + row.records_used, 0) ||
      item.records_used > item.max_records ||
      new Set(item.platform_runs.map((row) => row.platform)).size !==
        item.platform_runs.length ||
      new Set(item.platform_runs.map((row) => row.platform_run_id)).size !==
        item.platform_runs.length ||
      Date.parse(item.deadline_at) <= Date.parse(item.created_at)
    )
      ctx.addIssue({ code: "custom", message: "inconsistent task feed" });
  });
export const taskFeedPageSchema = z
  .object({
    schema_version: z.literal("execution-task-feed-v1"),
    items: z.array(taskFeedItemSchema).max(50),
    next_cursor: z.string().min(1).max(1024).nullable(),
  })
  .strict()
  .superRefine((page, ctx) => {
    if (
      new Set(page.items.map((item) => item.task_id)).size !==
        page.items.length ||
      (page.next_cursor && !page.items.length)
    )
      ctx.addIssue({ code: "custom", message: "inconsistent task page" });
  });
export const taskFeedDetailSchema = z
  .object({
    schema_version: z.literal("execution-task-feed-item-v1"),
    item: taskFeedItemSchema,
  })
  .strict();
export type TaskFeedItem = z.infer<typeof taskFeedItemSchema>;
export type TaskFeedPage = z.infer<typeof taskFeedPageSchema>;
export type TaskFeedQuery = z.infer<typeof taskFeedQuerySchema>;
