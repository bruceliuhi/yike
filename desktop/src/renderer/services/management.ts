import type {
  AccountState,
  ManagementInput,
  ManagementPlan,
  ManagementReceipt,
  ManagementExport,
  UpdateState,
} from "../domain/management";
import { ServiceError } from "./contracts";

export interface ManagementService {
  account(): Promise<AccountState>;
  updates(): Promise<UpdateState>;
  exportData(
    kind: "csv" | "backup-json",
  ): Promise<ManagementExport>;
  prepare(
    input: ManagementInput,
    inputHash: string,
    backupContent?: string,
  ): Promise<ManagementPlan>;
  execute(planId: string, requestId: string): Promise<ManagementReceipt>;
  operation(requestId: string): Promise<ManagementReceipt>;
  cancel(requestId: string): Promise<ManagementReceipt>;
}
const unavailable = async (): Promise<never> => {
  throw new ServiceError(
    "MANAGEMENT_UNAVAILABLE",
    "账号与数据管理服务尚未接通，当前没有执行更改。",
    501,
  );
};
export const unavailableManagement: ManagementService = {
  account: unavailable,
  updates: unavailable,
  exportData: unavailable,
  prepare: unavailable,
  execute: unavailable,
  operation: unavailable,
  cancel: unavailable,
};
export async function managementRequest<T>(
  operation: () => Promise<T>,
): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    return await Promise.race([
      operation(),
      new Promise<never>((_, reject) => {
        timer = setTimeout(
          () =>
            reject(
              new ServiceError(
                "MANAGEMENT_TIMEOUT",
                "请求超时，结果尚未确认。请核对原操作，勿重复提交。",
              ),
            ),
          30_000,
        );
      }),
    ]);
  } finally {
    if (timer) clearTimeout(timer);
  }
}
