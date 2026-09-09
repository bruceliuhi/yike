import type { TaskDraft, TaskRun } from "../domain/models";
import type {
  TaskActionBinding,
  TaskActionReceipt,
  TaskStartBinding,
  TaskStartLookup,
  TaskStartReceipt,
} from "../domain/taskOperations";
import { ServiceError } from "./contracts";

/** Optional authenticated execution adapter. All queries are server tenant scoped. */
export interface TaskOperationsService {
  start(draft: TaskDraft, binding: TaskStartBinding): Promise<TaskStartReceipt>;
  reconcileStart(original: TaskStartLookup): Promise<TaskStartReceipt>;
  task(id: string): Promise<TaskRun>;
  action(binding: TaskActionBinding): Promise<TaskActionReceipt>;
  reconcileAction(original: TaskActionBinding): Promise<TaskActionReceipt>;
}
export function requireTaskOperations(
  service?: TaskOperationsService,
): TaskOperationsService {
  if (!service)
    throw new ServiceError(
      "TASK_OPERATIONS_UNAVAILABLE",
      "任务执行与原请求核对服务尚未接通，当前没有新增执行。",
      501,
    );
  return service;
}
