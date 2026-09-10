import {
  taskFeedQuerySchema,
  taskFeedGetSchema,
  taskFeedPageSchema,
  taskFeedDetailSchema,
  type TaskFeedQuery,
  type TaskFeedPage,
  type TaskFeedItem,
} from "../../shared/taskFeed";
import type { ApiOperation } from "../../shared/contracts";
import { ServiceError } from "./contracts";
type Transport = (
  operation: ApiOperation,
  path: string,
  method?: string,
  payload?: unknown,
  signal?: AbortSignal,
) => Promise<unknown>;
export interface TaskFeedService {
  list(query?: TaskFeedQuery, signal?: AbortSignal): Promise<TaskFeedPage>;
  get(taskId: string, signal?: AbortSignal): Promise<TaskFeedItem>;
}
export function createTaskFeedService(transport: Transport): TaskFeedService {
  return {
    async list(query = {}, signal) {
      const payload = taskFeedQuerySchema.parse(query),
        params = new URLSearchParams();
      for (const [key, value] of Object.entries(payload))
        params.set(key, String(value));
      const page = taskFeedPageSchema.parse(
        await transport(
          "taskFeed.list",
          `/execution-task-feed${params.size ? "?" + params : ""}`,
          "GET",
          payload,
          signal,
        ),
      );
      if (
        page.items.length > (payload.limit ?? 20) ||
        (page.next_cursor && page.next_cursor === payload.cursor)
      )
        throw new ServiceError(
          "INVALID_SERVICE_RESPONSE",
          "任务列表未核实，请重新读取。",
        );
      return page;
    },
    async get(taskId, signal) {
      const payload = taskFeedGetSchema.parse({ taskId });
      const result = taskFeedDetailSchema.parse(
        await transport(
          "taskFeed.get",
          `/execution-task-feed/${taskId}`,
          "GET",
          payload,
          signal,
        ),
      );
      if (result.item.task_id !== taskId)
        throw new ServiceError(
          "INVALID_SERVICE_RESPONSE",
          "任务详情与当前任务不一致，请重新读取。",
        );
      return result.item;
    },
  };
}
