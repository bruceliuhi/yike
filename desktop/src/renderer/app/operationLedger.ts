import { useEffect, useSyncExternalStore, type SetStateAction } from "react";
import { ServiceError } from "../services/contracts";
import { forgetLegacyOperationLock, readLegacyOperationLock } from "./hooks";

export type OperationScope = "send-attempts" | "unknown-task-starts";
export type OperationEntries = Record<string, string>;
const PREFIX = "yike.ui.operation.v1.";
const memory = new Map<string, OperationEntries>();
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
export function operationLedgerKey(
  scope: OperationScope,
  userId: string,
): string {
  return PREFIX + scope + "." + encodeURIComponent(userId);
}
function legacyKey(scope: OperationScope, userId: string) {
  return "yike.ui.draft.v1." + scope + "." + userId;
}
function ledgerError() {
  return new ServiceError(
    "OPERATION_LEDGER_UNAVAILABLE",
    "操作确认记录暂时无法可靠保存，请检查本机存储并核对平台记录后重试。",
  );
}
function validEntries(
  value: unknown,
  scope: OperationScope,
): value is OperationEntries {
  if (
    !value ||
    typeof value !== "object" ||
    Array.isArray(value) ||
    Object.getPrototypeOf(value) !== Object.prototype
  )
    return false;
  const entries = Object.entries(value);
  if (entries.length > 10_000) return false;
  return entries.every(([key, status]) => {
    if (
      !key ||
      key.length > 1024 ||
      ["__proto__", "prototype", "constructor"].includes(key) ||
      typeof status !== "string"
    )
      return false;
    if (scope === "unknown-task-starts")
      return (
        key.length <= 512 &&
        status.startsWith("task:" + key + ":") &&
        /^\d+$/.test(status.slice(("task:" + key + ":").length))
      );
    if (status !== "PENDING" && status !== "SENT") return false;
    try {
      const parts: unknown = JSON.parse(key);
      return (
        Array.isArray(parts) &&
        (parts.length === 2 || parts.length === 3) &&
        typeof parts[0] === "string" &&
        !!parts[0] &&
        parts[0].length <= 512 &&
        (parts[1] === "comment" || parts[1] === "dm") &&
        (parts.length === 2 ||
          (typeof parts[2] === "number" &&
            Number.isSafeInteger(parts[2]) &&
            parts[2] >= 1))
      );
    } catch {
      return false;
    }
  });
}
function decode(raw: string | null, scope: OperationScope): OperationEntries {
  if (raw === null) return {};
  const value: unknown = JSON.parse(raw);
  if (!validEntries(value, scope)) throw ledgerError();
  return value;
}
function read(
  scope: OperationScope,
  userId: string,
): { entries: OperationEntries; blocked: boolean } {
  const key = operationLedgerKey(scope, userId);
  let known = memory.get(key) || {};
  try {
    let entries = decode(localStorage.getItem(key), scope);
    known = entries;
    // Old builds stored these locks with editable drafts. Migrate before deleting
    // any legacy key; a failed migration remains locked and can be retried.
    const oldKey = legacyKey(scope, userId);
    const legacy = sessionStorage.getItem(oldKey);
    const cached = readLegacyOperationLock(oldKey);
    if (legacy !== null || cached !== undefined) {
      if (cached !== undefined && !validEntries(cached, scope))
        throw ledgerError();
      entries = {
        ...((cached as OperationEntries) || {}),
        ...decode(legacy, scope),
        ...entries,
      };
      known = entries;
      localStorage.setItem(key, JSON.stringify(entries));
      sessionStorage.removeItem(oldKey);
      forgetLegacyOperationLock(oldKey);
    }
    memory.set(key, entries);
    return { entries, blocked: false };
  } catch {
    return { entries: known, blocked: true };
  }
}

/** Only opaque operation IDs and status markers belong here, never draft text,
 * recipients, account credentials or confirmation tokens. The service remains
 * authoritative for idempotency; this ledger prevents ordinary UI re-submission.
 */
export function useOperationLedger(scope: OperationScope, userId?: string) {
  useSyncExternalStore(subscribe, snapshot, snapshot);
  useEffect(() => {
    const onStorage = (event: StorageEvent) => {
      if (event.key === null || event.key.startsWith(PREFIX)) changed();
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);
  const current = userId ? read(scope, userId) : { entries: {}, blocked: true };
  const setEntries = (next: SetStateAction<OperationEntries>) => {
    if (!userId) throw new ServiceError("UNAUTHORIZED", "请先登录客户空间。");
    const latest = read(scope, userId);
    if (latest.blocked) throw ledgerError();
    const updated = typeof next === "function" ? next(latest.entries) : next;
    if (!validEntries(updated, scope)) throw ledgerError();
    const key = operationLedgerKey(scope, userId);
    // Commit before returning to a caller that is about to send/start. If durable
    // storage fails, throwing prevents that external write from being attempted.
    try {
      localStorage.setItem(key, JSON.stringify(updated));
    } catch {
      throw ledgerError();
    }
    memory.set(key, updated);
    changed();
  };
  // Unlike editable drafts, an already-started operation may settle after its
  // page unmounts. Its captured setter updates only that original user's ledger.
  return [current.entries, setEntries] as const;
}
