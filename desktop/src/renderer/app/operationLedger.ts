import { useEffect, useSyncExternalStore, type SetStateAction } from "react";
import { ServiceError } from "../services/contracts";
import { forgetLegacyOperationLock, readLegacyOperationLock } from "./hooks";
import { parseCandidateOperation } from "../domain/candidateReviewOperation";
import { usageReservationSchema } from "../domain/researchUsage";
import { validCoverageAdjustmentEntry } from "../domain/coveragePlan";
import { validStrategyEntry } from "../domain/strategyConfirmation";

export type OperationScope =
  | "send-attempts"
  | "unknown-task-starts"
  | "followup-operations"
  | "task-operations"
  | "connection-disconnects"
  | "candidate-reviews"
  | "contact-draft-saves"
  | "coverage-adjustments"
  | "research-strategy-operations"
  | "management-operations";
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
    if (scope === "candidate-reviews")
      return status === "PENDING" && parseCandidateOperation(key) !== null;
    if (scope === "coverage-adjustments") return validCoverageAdjustmentEntry(key, status);
    if (scope === "research-strategy-operations") return validStrategyEntry(key, status);
    if (scope === "contact-draft-saves") {
      if (status !== "PENDING") return false;
      try {
        const parts: unknown = JSON.parse(key);
        return Array.isArray(parts) && parts.length === 4 &&
          typeof parts[0] === "string" && parts[0].trim().length > 0 && parts[0].length <= 128 &&
          ["comment", "dm"].includes(parts[1]) &&
          typeof parts[2] === "string" && parts[2].trim().length > 0 && parts[2].length <= 128 &&
          typeof parts[3] === "string" && /^[a-f0-9]{64}$/.test(parts[3]);
      } catch { return false; }
    }
    if (scope === "connection-disconnects") {
      if (status !== "PENDING" && status !== "ACKNOWLEDGED") return false;
      try {
        const parts: unknown = JSON.parse(key);
        return (
          Array.isArray(parts) &&
          parts.length === 3 &&
          ["xhs", "douyin", "bilibili", "zhihu"].includes(parts[0]) &&
          typeof parts[1] === "string" &&
          parts[1].trim().length > 0 &&
          parts[1].length <= 512 &&
          typeof parts[2] === "string" &&
          parts[2].trim().length > 0 &&
          parts[2].length <= 128
        );
      } catch {
        return false;
      }
    }
    if (scope === "task-operations") {
      if (status !== "PENDING") return false;
      try {
        const parts: unknown = JSON.parse(key);
        return (
          Array.isArray(parts) &&
          parts.length === 4 &&
          typeof parts[0] === "string" &&
          parts[0].length > 0 &&
          parts[0].length <= 128 &&
          ["pause", "resume", "retry", "cancel"].includes(parts[1]) &&
          typeof parts[2] === "string" &&
          /^[a-f0-9]{64}$/.test(parts[2]) &&
          typeof parts[3] === "string" &&
          parts[3].length > 0 &&
          parts[3].length <= 128
        );
      } catch {
        return false;
      }
    }
    if (scope === "followup-operations") {
      if (status !== "PENDING") return false;
      try {
        const parts: unknown = JSON.parse(key);
        return (
          Array.isArray(parts) &&
          parts.length === 6 &&
          typeof parts[0] === "string" &&
          parts[0].length > 0 &&
          parts[0].length <= 512 &&
          typeof parts[1] === "string" &&
          parts[1].length > 0 &&
          parts[1].length <= 512 &&
          ["create", "correct", "void", "mark-read", "legacy-create"].includes(
            parts[2],
          ) &&
          typeof parts[3] === "string" &&
          parts[3].length <= 512 &&
          Number.isSafeInteger(parts[4]) &&
          parts[4] >= 0 &&
          typeof parts[5] === "string" &&
          parts[5].length > 0 &&
          parts[5].length <= 128
        );
      } catch {
        return false;
      }
    }
    if (scope === "management-operations")
      return (
        /^[a-zA-Z0-9_-]{1,200}$/.test(key) &&
        [
          "bind-device",
          "unbind-device",
          "restore",
          "download-update",
          "install-update",
          "rollback",
        ].includes(status)
      );
    if (scope === "unknown-task-starts") {
      if (key.length > 512) return false;
      if (status.startsWith("task:" + key + ":"))
        return /^\d+$/.test(status.slice(("task:" + key + ":").length));
      try {
        const parts: unknown = JSON.parse(status);
        return (
          Array.isArray(parts) &&
          (parts.length === 4 || (parts.length === 5 && usageReservationSchema.safeParse(parts[4]).success)) &&
          Number.isSafeInteger(parts[1]) &&
          parts[1] >= 1 &&
          parts[0] === `task:${key}:${parts[1]}` &&
          typeof parts[2] === "string" &&
          /^[a-f0-9]{64}$/.test(parts[2]) &&
          (parts[3] === "once" || parts[3] === "monitor")
        );
      } catch {
        return false;
      }
    }
    if (status !== "PENDING" && status !== "SENT") return false;
    try {
      const parts: unknown = JSON.parse(key);
      return (
        Array.isArray(parts) &&
        (parts.length === 2 || parts.length === 3 || parts.length === 4) &&
        typeof parts[0] === "string" &&
        !!parts[0] &&
        parts[0].length <= 512 &&
        (parts[1] === "comment" || parts[1] === "dm") &&
        (parts.length === 2 ||
          (typeof parts[2] === "number" &&
            Number.isSafeInteger(parts[2]) &&
            parts[2] >= 1)) &&
        (parts.length !== 4 ||
          (typeof parts[3] === "string" &&
            parts[3].length > 0 &&
            parts[3].length <= 128))
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
  const getEntries = () => {
    if (!userId) throw new ServiceError("UNAUTHORIZED", "请先登录客户空间。");
    const latest = read(scope, userId);
    if (latest.blocked) throw ledgerError();
    return latest.entries;
  };
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
  // A captured reader sees synchronous writes even before React renders again.
  return [current.entries, setEntries, getEntries] as const;
}
