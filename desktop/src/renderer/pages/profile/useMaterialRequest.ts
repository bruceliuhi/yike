import { useLayoutEffect, useMemo, useRef, useState } from "react";
import { useApp } from "../../app/context";
import { useAction } from "../../app/hooks";
import { boundedRequest } from "../../app/boundedRequest";
import {
  parseMaterialReceipt,
  type MaterialChange,
  type MaterialPending,
  type MaterialReceipt,
} from "../../domain/materials";
import type { MaterialService } from "../../services/materials";
import {
  finishMaterialOperation,
  materialOwner,
  readMaterialOperations,
  storeMaterialOperation,
  type HistoricalMaterialOperation,
} from "./materialOperationStorage";

/** Stores opaque identities only; clearing editable drafts must not permit a second write. */
export function useMaterialRequest(
  api: MaterialService,
  profileVersionId: string,
  receive: (receipt: MaterialReceipt) => void,
) {
  const { session, notify } = useApp();
  const identity = useMemo(() => ({}), [api, profileVersionId, session.authenticated, session.userId, session.accountScope?.id, session.accountScope?.version]);
  const active = useRef(identity);
  active.current = identity;
  const read = () => readMaterialOperations(materialOwner(session), profileVersionId);
  const [pending, setPending] = useState<MaterialPending | null>(null);
  const [historical, setHistorical] = useState<HistoricalMaterialOperation[]>([]);
  const [storageError, setStorageError] = useState("");
  const [progress, setProgress] = useState<number | null>(null);
  const action = useAction();
  const live = useRef(true);
  const current = () => live.current && active.current === identity;
  const abort = useRef<AbortController | null>(null);
  const load = () => {
    try {
      const stored = read();
      setPending(stored.pending);
      setHistorical(stored.historical);
      setStorageError("");
    } catch {
      setStorageError(
        "原资料操作记录无法读取，请恢复本机存储后重试；当前不会提交新操作。",
      );
    }
  };
  useLayoutEffect(() => {
    live.current = true;
    load();
    const changed = (event: StorageEvent) => {
      if (event.key === null || event.key.startsWith("yike.ui.material-operation.")) load();
    };
    window.addEventListener("storage", changed);
    return () => {
      live.current = false;
      abort.current?.abort();
      window.removeEventListener("storage", changed);
    };
  }, [identity]);
  const settle = (
    value: unknown,
    binding: MaterialPending,
    change?: MaterialChange,
  ) => {
    if (!current()) return;
    const receipt = parseMaterialReceipt(value, binding, change);
    if (["SUCCEEDED", "FAILED"].includes(receipt.status)) {
      finishMaterialOperation(materialOwner(session), binding);
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
      if (!current()) return;
      if (!session.authenticated || !session.userId)
        throw new Error("请先登录客户空间。");
      let binding: MaterialPending;
      try {
        binding = {
          requestId: crypto.randomUUID(),
          profileVersionId,
          materialId: change.materialId,
          kind: change.kind,
          expectedVersion: change.expectedVersion,
        };
        storeMaterialOperation(materialOwner(session), binding);
      } catch {
        throw new Error("存在待确认资料操作或本机记录不可写，请先核对原操作。");
      }
      setPending(binding);
      setProgress(null);
      const controller = new AbortController();
      abort.current = controller;
      try {
        const receipt = await boundedRequest(
          (signal) => {
            if (!current()) throw new Error("客户空间已变化，资料操作未提交。");
            return api.mutate(
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
            );
          },
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
      if (!current()) return;
      const binding = read().pending;
      if (!binding) {
        load();
        return;
      }
      const controller = new AbortController();
      abort.current = controller;
      try {
        const receipt = await boundedRequest(
          () => {
            if (!current()) throw new Error("客户空间已变化，未查询原资料操作。");
            return api.operation(profileVersionId, binding.requestId);
          },
          { signal: controller.signal, timeoutMessage: "核对超时，原资料操作保护继续保留。" },
        );
        return settle(receipt, binding);
      } catch (error) {
        if (current()) throw error;
      }
    });
  return {
    pending,
    historical,
    storageError,
    progress,
    action,
    run,
    reconcile,
    reloadStorage: load,
  };
}
