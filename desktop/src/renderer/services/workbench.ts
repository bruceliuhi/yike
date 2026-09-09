import { z } from "zod";

export type WorkbenchQueue = "review" | "contact" | "reply" | "followup";
const item = z.object({
  id: z.string().min(1).max(512),
  targetId: z.string().min(1).max(512),
  title: z.string().min(1).max(1000),
  detail: z.string().max(2000),
  sample: z.literal(false),
});
export interface WorkbenchSnapshot {
  queue: WorkbenchQueue;
  items: z.infer<typeof item>[];
  total: number;
}
export interface WorkbenchService {
  /** Tenant-authorized complete snapshot. review targets candidates; other queues target opportunities. */
  queue(kind: WorkbenchQueue): Promise<WorkbenchSnapshot>;
}
export function parseWorkbenchSnapshot(value: unknown, queue: WorkbenchQueue) {
  const result = z
    .object({
      queue: z.literal(queue),
      items: z.array(item).max(1000),
      total: z.number().int().nonnegative(),
    })
    .parse(value);
  if (
    result.items.length !== result.total ||
    new Set(result.items.map((row) => row.id)).size !== result.items.length ||
    result.items.some((row) =>
      [row.id, row.targetId].some(
        (id) => id === "sample" || id.startsWith("sample:"),
      ),
    )
  )
    throw new Error("待办记录不完整或混入样例，请刷新重试。");
  return result;
}
