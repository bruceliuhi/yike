import { useEffect, useRef } from "react";
import { useApp } from "../../app/context";
import { useAction } from "../../app/hooks";
import { useOperationLedger } from "../../app/operationLedger";
import { boundedRequest } from "../../app/boundedRequest";
import {
  bindingFromKey,
  followupKey,
  readReceipt,
  type FollowupBinding,
  type FollowupMutation,
} from "../../domain/followup";
import { requireFollowup } from "../../services/followup";
export function useFollowupOperation() {
  const { service, session, notify } = useApp();
  const action = useAction();
  const [pending, setPending] = useOperationLedger(
    "followup-operations",
    session.userId,
  );
  const mounted = useRef(true);
  const identity = useRef({
    service,
    user: session.userId,
    authenticated: session.authenticated,
  });
  identity.current = {
    service,
    user: session.userId,
    authenticated: session.authenticated,
  };
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  const current = () =>
    mounted.current &&
    identity.current.service === service &&
    identity.current.user === session.userId &&
    identity.current.authenticated === session.authenticated;
  const settle = (value: unknown, binding: FollowupBinding) => {
    const receipt = readReceipt(value, binding);
    if (receipt.status === "SUCCEEDED" || receipt.status === "FAILED")
      setPending((old) => {
        const next = { ...old };
        delete next[followupKey(binding)];
        return next;
      });
    return receipt;
  };
  return {
    pending,
    action,
    current,
    run: (mutation: FollowupMutation, legacy?: () => Promise<void>) =>
      action.run(async () => {
        if (!session.authenticated || !current())
          throw new Error("请先登录客户空间。");
        const key = followupKey(mutation.binding);
        setPending((old) => {
          if (Object.keys(old).length)
            throw new Error("请先核对未完成的跟进操作，不能重复保存。");
          return { ...old, [key]: "PENDING" };
        });
        if (legacy) {
          await boundedRequest(() => legacy(), {
            timeoutMessage: "保存结果未确认，请核对已有登记，不要重复保存。",
          });
          setPending((old) => {
            const next = { ...old };
            delete next[key];
            return next;
          });
          return "SUCCEEDED" as const;
        }
        const raw = await boundedRequest(
          () => requireFollowup(service.followup).mutate(mutation),
          { timeoutMessage: "保存结果未确认，请核对原操作，不要重复保存。" },
        );
        const checked = readReceipt(raw, mutation.binding);
        if (
          checked.status === "SUCCEEDED" &&
          mutation.values &&
          checked.record &&
          Object.entries(mutation.values).some(
            ([key, value]) =>
              checked.record![key as keyof typeof checked.record] !== value,
          )
        )
          throw new Error("保存回执内容与提交快照不一致，原操作保护仍保留。");
        const receipt = settle(checked, mutation.binding);
        if (
          current() &&
          (receipt.status === "PENDING" || receipt.status === "UNKNOWN")
        )
          notify("操作结果待确认，请核对原操作。", "info");
        return receipt.status;
      }),
    reconcile: (key: string) =>
      action.run(async () => {
        if (!session.authenticated || !current()) return;
        const binding = bindingFromKey(key);
        if (binding.action === "legacy-create")
          throw new Error(
            "此人工登记使用旧接口，没有原请求查询能力。请核对已有登记并由服务管理员确认，当前不会重复保存。",
          );
        const receipt = settle(
          await boundedRequest(
            () => requireFollowup(service.followup).operation(binding),
            { timeoutMessage: "原跟进操作核对超时，保护继续保留。" },
          ),
          binding,
        );
        if (current())
          notify(
            receipt.status === "SUCCEEDED"
              ? "原跟进操作已确认完成。"
              : receipt.status === "FAILED"
                ? "原操作已确认失败，可重新核对后保存。"
                : "结果仍待确认，保护继续保留。",
            receipt.status === "SUCCEEDED" ? "success" : "info",
          );
        return receipt.status;
      }),
  };
}
