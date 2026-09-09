import {
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useSyncExternalStore,
} from "react";
import { useApp } from "../../app/context";
import { useAction, useLocalDraft } from "../../app/hooks";
import { errorMessage } from "../../services/contracts";
import {
  followupOwner,
  readFollowupOperations,
  storeFollowupOperation,
  finishFollowupOperation,
  parseFollowupKey,
  type HistoricalFollowupOperation,
  type FollowupDraftReference,
} from "./followupOperationStorage";
import { boundedRequest } from "../../app/boundedRequest";
import {
  followupKey,
  readReceipt,
  type FollowupBinding,
  type FollowupMutation,
} from "../../domain/followup";
import { requireFollowup } from "../../services/followup";
const listeners = new Set<() => void>();
let revision = 0;
const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
};
const snapshot = () => revision;
function changed() {
  revision++;
  for (const listener of listeners) listener();
}
export function useFollowupOperation() {
  const { service, session, notify } = useApp();
  const action = useAction();
  const [resolvedDrafts, setResolvedDrafts] = useLocalDraft<
    Record<string, string[]>
  >(
    "followup-resolved:" +
      JSON.stringify([
        session.userId,
        session.accountScope?.id ?? null,
        session.accountScope?.version ?? null,
      ]),
    {},
    (value) =>
      !!value &&
      typeof value === "object" &&
      !Array.isArray(value) &&
      Object.entries(value).every(
        ([key, hashes]) =>
          key.length > 0 &&
          Array.isArray(hashes) &&
          hashes.every(
            (hash) => typeof hash === "string" && /^[a-f0-9]{64}$/.test(hash),
          ),
      ),
  );
  const acknowledgeDraft = (draft: FollowupDraftReference) => {
    if (!current()) return;
    setResolvedDrafts((old) => {
      const next = { ...old };
      const hashes = (next[draft.key] || []).filter(
        (hash) => hash !== draft.hash,
      );
      if (hashes.length) next[draft.key] = hashes;
      else delete next[draft.key];
      return next;
    });
  };
  const identity = useMemo(
    () => ({}),
    [
      service,
      service.followup,
      session.authenticated,
      session.userId,
      session.accountScope?.id,
      session.accountScope?.version,
    ],
  );
  const active = useRef(identity);
  active.current = identity;
  const mounted = useRef(true);
  useLayoutEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, [identity]);
  useSyncExternalStore(subscribe, snapshot, snapshot);
  useEffect(() => {
    window.addEventListener("storage", changed);
    return () => window.removeEventListener("storage", changed);
  }, []);
  const current = () => mounted.current && active.current === identity;
  let pending: Record<string, string> = {};
  let historical: HistoricalFollowupOperation[] = [];
  let storageError = "";
  if (session.authenticated)
    try {
      const stored = readFollowupOperations(followupOwner(session));
      if (stored.pending)
        pending = { [followupKey(stored.pending)]: "PENDING" };
      historical = stored.historical;
    } catch (error) {
      storageError =
        "原跟进操作记录无法可靠读取，保护仍保留。" + errorMessage(error);
    }
  const blocked =
    !!storageError || historical.length > 0 || Object.keys(pending).length > 0;
  const settle = (value: unknown, binding: FollowupBinding) => {
    if (!current()) return undefined;
    const receipt = readReceipt(value, binding);
    if (receipt.status === "SUCCEEDED" || receipt.status === "FAILED") {
      const stored = readFollowupOperations(followupOwner(session));
      if (
        !stored.pending ||
        followupKey(stored.pending) !== followupKey(binding)
      )
        throw new Error("原跟进操作记录已变化，保护仍保留。");
      // Store only a hash and opaque draft key, never the submitted note. The
      // editable draft and this acknowledgement have the same session lifetime.
      if (receipt.status === "SUCCEEDED" && stored.draft) {
        const draft = stored.draft;
        setResolvedDrafts((old) => ({
          ...old,
          [draft.key]: Array.from(
            new Set([...(old[draft.key] || []), draft.hash]),
          ),
        }));
      }
      finishFollowupOperation(followupOwner(session), binding);
      changed();
    }
    return receipt;
  };
  return {
    pending,
    historical,
    storageError,
    blocked,
    refresh: changed,
    resolvedDrafts,
    acknowledgeDraft,
    action,
    current,
    run: (
      mutation: FollowupMutation,
      legacy?: () => Promise<void>,
      draft?: FollowupDraftReference,
    ) =>
      action.run(async () => {
        if (!session.authenticated || !current())
          throw new Error("请先登录客户空间。");
        storeFollowupOperation(followupOwner(session), mutation.binding, draft);
        changed();
        if (legacy) {
          await boundedRequest(() => legacy(), {
            timeoutMessage: "保存结果未确认，请核对已有登记，不要重复保存。",
          });
          if (!current()) return;
          finishFollowupOperation(followupOwner(session), mutation.binding);
          changed();
          return "SUCCEEDED" as const;
        }
        const raw = await boundedRequest(
          () => requireFollowup(service.followup).mutate(mutation),
          { timeoutMessage: "保存结果未确认，请核对原操作，不要重复保存。" },
        );
        if (!current()) return;
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
        if (!receipt) return;
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
        const binding = parseFollowupKey(key);
        const stored = readFollowupOperations(followupOwner(session));
        if (!stored.pending || followupKey(stored.pending) !== key)
          throw new Error("只能在原客户空间及版本核对原跟进操作。");
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
        if (!receipt) return;
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
