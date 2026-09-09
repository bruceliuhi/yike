import { useApp } from "../../app/context";
import { useAction } from "../../app/hooks";
import { useOperationLedger } from "../../app/operationLedger";
import {
  receiptSchema,
  type AccountState,
  type ManagementInput,
  type ManagementPlan,
  type ManagementReceipt,
} from "../../domain/management";
import { ServiceError } from "../../services/contracts";
import {
  managementRequest,
  unavailableManagement,
} from "../../services/management";
import { useManagementScope } from "./useManagementScope";

export const labels: Record<ManagementInput["kind"], string> = {
  "bind-device": "绑定设备",
  "unbind-device": "解绑设备",
  restore: "恢复客户数据",
  "download-update": "下载安装包",
  "install-update": "安装更新并重启",
  rollback: "回退版本",
};

export function useManagedOperation(
  account: AccountState | undefined,
  changed: () => void,
) {
  const { service, session, notify } = useApp();
  const management = service.management ?? unavailableManagement;
  const [pending, setPending] = useOperationLedger(
    "management-operations",
    session.userId,
  );
  const action = useAction();
  const scope = useManagementScope(account);
  const settle = (
    value: ManagementReceipt,
    requestId: string,
    kind: string,
  ) => {
    const receipt = receiptSchema.parse(value);
    if (
      !account ||
      receipt.requestId !== requestId ||
      receipt.kind !== kind ||
      receipt.spaceId !== account.spaceId
    )
      throw new Error("操作回执与当前客户空间或请求不匹配，请核对原操作。");
    if (["SUCCEEDED", "FAILED", "CANCELLED"].includes(receipt.status)) {
      setPending((old) => {
        const next = { ...old };
        delete next[requestId];
        return next;
      });
      if (scope.current()) {
        notify(
          receipt.status === "SUCCEEDED"
            ? `${labels[receipt.kind]}已完成。`
            : receipt.status === "CANCELLED"
              ? "原操作已取消。"
              : receipt.message || "原操作已确认失败，没有完成更改。",
          receipt.status === "FAILED"
            ? "error"
            : receipt.status === "SUCCEEDED"
              ? "success"
              : "info",
        );
        changed();
      }
    } else if (scope.current())
      notify("操作结果待确认，请核对原操作后再继续。", "info");
    return receipt;
  };
  return {
    pending,
    action,
    execute: (plan: ManagementPlan) =>
      action.run(async () => {
        if (!session.authenticated || !account)
          throw new Error("请先登录并读取客户空间。");
        if (Object.keys(pending).length)
          throw new Error("请先核对待确认操作。");
        const requestId = crypto.randomUUID();
        // Durable request identity precedes dispatch; closing/logout cannot unlock it.
        setPending((old) => {
          if (Object.keys(old).length) throw new Error("请先核对待确认操作。");
          return { ...old, [requestId]: plan.kind };
        });
        try {
          return settle(
            await managementRequest(() =>
              management.execute(plan.id, requestId),
            ),
            requestId,
            plan.kind,
          );
        } catch (error) {
          // Even an HTTP failure may follow a committed write. Only the same-request
          // authoritative receipt can unlock a submitted operation.
          if (scope.current())
            throw new ServiceError(
              "MANAGEMENT_UNKNOWN",
              "操作结果尚未确认，已保留原请求。请使用“核对原操作”，不要重复提交。",
            );
        }
      }),
    reconcile: (requestId: string, kind: string, cancel = false) =>
      action.run(() =>
        scope.run(async () =>
          settle(
            await managementRequest(() =>
              cancel
                ? management.cancel(requestId)
                : management.operation(requestId),
            ),
            requestId,
            kind,
          ),
        ),
      ),
  };
}
