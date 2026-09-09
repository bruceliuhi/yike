import { useEffect, useRef, useState } from "react";
import { useApp } from "../../app/context";
import { useAction } from "../../app/hooks";
import { boundedRequest } from "../../app/boundedRequest";
import {
  materialPendingSchema,
  parseMaterialReceipt,
  type MaterialChange,
  type MaterialPending,
  type MaterialReceipt,
} from "../../domain/materials";
import type { MaterialService } from "../../services/materials";

/** Stores opaque identities only; clearing editable drafts must not permit a second write. */
export function useMaterialRequest(
  api: MaterialService,
  profileVersionId: string,
  receive: (receipt: MaterialReceipt) => void,
) {
  const { session, notify } = useApp();
  const key =
    "yike.ui.material-operation.v1." +
    encodeURIComponent(session.userId || "guest") +
    "." +
    encodeURIComponent(profileVersionId);
  const read = () => {
    const text = localStorage.getItem(key);
    if (text === null) return null;
    const pending = materialPendingSchema.parse(JSON.parse(text));
    if (pending.profileVersionId !== profileVersionId)
      throw new Error("资料操作记录与当前画像不匹配。");
    return pending;
  };
  const [pending, setPending] = useState<MaterialPending | null>(null);
  const [storageError, setStorageError] = useState("");
  const [progress, setProgress] = useState<number | null>(null);
  const action = useAction();
  const live = useRef(true);
  const currentApi = useRef(api);
  currentApi.current = api;
  const current = () => live.current && currentApi.current === api;
  const abort = useRef<AbortController | null>(null);
  const load = () => {
    try {
      setPending(read());
      setStorageError("");
    } catch {
      setStorageError(
        "原资料操作记录无法读取，请恢复本机存储后重试；当前不会提交新操作。",
      );
    }
  };
  useEffect(() => {
    live.current = true;
    load();
    const changed = (event: StorageEvent) => {
      if (event.key === key || event.key === null) load();
    };
    window.addEventListener("storage", changed);
    return () => {
      live.current = false;
      abort.current?.abort();
      window.removeEventListener("storage", changed);
    };
  }, [key]);
  const settle = (
    value: unknown,
    binding: MaterialPending,
    change?: MaterialChange,
  ) => {
    const receipt = parseMaterialReceipt(value, binding, change);
    if (["SUCCEEDED", "FAILED"].includes(receipt.status)) {
      // Captured key remains that of the original account even if the page closes.
      if (read()?.requestId === binding.requestId) localStorage.removeItem(key);
      if (current()) {
        setPending(null);
        if (receipt.status === "FAILED")
          throw new Error(
            receipt.message || "资料操作已确认未执行，输入保留，请检查后重试。",
          );
        receive(receipt);
      }
    } else if (current()) notify("资料操作结果待确认，请核对原操作。", "info");
    return receipt;
  };
  const run = async (change: MaterialChange) =>
    action.run(async () => {
      if (!session.authenticated || !session.userId)
        throw new Error("请先登录客户空间。");
      let binding: MaterialPending;
      try {
        if (read()) throw new Error("pending");
        binding = {
          requestId: crypto.randomUUID(),
          profileVersionId,
          materialId: change.materialId,
          kind: change.kind,
          expectedVersion: change.expectedVersion,
        };
        localStorage.setItem(key, JSON.stringify(binding));
      } catch {
        throw new Error("存在待确认资料操作或本机记录不可写，请先核对原操作。");
      }
      setPending(binding);
      setProgress(null);
      const controller = new AbortController();
      abort.current = controller;
      try {
        const receipt = await boundedRequest(
          (signal) =>
            api.mutate(
              { requestId: binding.requestId, profileVersionId, change },
              {
                signal,
                onUploadProgress: (percent) => {
                  if (
                    current() &&
                    !signal.aborted &&
                    Number.isFinite(percent) &&
                    percent >= 0 &&
                    percent <= 100
                  )
                    setProgress((previous) =>
                      Math.max(previous ?? 0, Math.floor(percent)),
                    );
                },
              },
            ),
          {
            signal: controller.signal,
            timeoutMessage:
              "资料操作等待超时，结果尚未确认，请核对原操作，勿重复提交。",
          },
        );
        return settle(receipt, binding, change);
      } catch (error) {
        if (current()) throw error;
      } finally {
        if (current()) setProgress(null);
      }
    });
  const reconcile = () =>
    action.run(async () => {
      const binding = read();
      if (!binding) {
        load();
        return;
      }
      const receipt = await boundedRequest(
        () => api.operation(profileVersionId, binding.requestId),
        { timeoutMessage: "核对超时，原资料操作保护继续保留。" },
      );
      return settle(receipt, binding);
    });
  return {
    pending,
    storageError,
    progress,
    action,
    run,
    reconcile,
    reloadStorage: load,
  };
}
