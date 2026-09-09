import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
  type SetStateAction,
} from "react";
import { errorMessage } from "../services/contracts";
import { boundedRequest } from "./boundedRequest";
import { sessionContentAtRisk } from "./sessionContent";
export function useResource<T>(loader: (signal?: AbortSignal) => Promise<T>, deps: unknown[] = []) {
  // The dependency identity also gates render-time data. Clearing in an effect
  // alone would expose the previous account's data for one render.
  const identity = useMemo(() => ({}), deps);
  const active = useRef(identity);
  active.current = identity;
  const mounted = useRef(true);
  const generation = useRef(0);
  const pending = useRef<AbortController | null>(null);
  const [state, setState] = useState<{
    identity: object;
    data: T | undefined;
    loading: boolean;
    error: string;
  }>(() => ({ identity, data: undefined, loading: true, error: "" }));
  const load = useCallback(async () => {
    if (active.current !== identity || !mounted.current) return;
    const id = ++generation.current;
    pending.current?.abort();
    const controller = new AbortController();
    pending.current = controller;
    setState({ identity, data: undefined, loading: true, error: "" });
    try {
      // Start immediately, retaining established loader identity and StrictMode semantics.
      const promise = loader(controller.signal);
      void promise.catch(() => undefined);
      // Existing domain reads own a 30s deadline and their specific recovery message.
      const data = await boundedRequest(() => promise, { signal: controller.signal, timeoutMs: 31_000, timeoutMessage: "读取超时，请重试。" });
      if (
        mounted.current &&
        active.current === identity &&
        id === generation.current
      )
        setState({ identity, data, loading: false, error: "" });
    } catch (error) {
      if (
        mounted.current &&
        active.current === identity &&
        id === generation.current
      )
        setState({
          identity,
          data: undefined,
          loading: false,
          error: errorMessage(error),
        });
    } finally {
      controller.abort();
    }
  }, [identity]);
  useEffect(() => {
    mounted.current = true;
    void load();
    return () => {
      mounted.current = false;
      generation.current++;
      pending.current?.abort();
    };
  }, [load]);
  const setData = useCallback(
    (next: SetStateAction<T | undefined>) => {
      if (!mounted.current || active.current !== identity) return;
      generation.current++;
      pending.current?.abort();
      setState((old) => ({
        identity,
        loading: false,
        error: "",
        data:
          typeof next === "function"
            ? (next as (value: T | undefined) => T | undefined)(
                old.identity === identity ? old.data : undefined,
              )
            : next,
      }));
    },
    [identity],
  );
  const current =
    state.identity === identity
      ? state
      : { data: undefined, loading: true, error: "" };
  return {
    data: current.data,
    loading: current.loading,
    error: current.error,
    reload: load,
    setData,
  };
}
const draftMemory = new Map<string, unknown>();
const editedDraftKeys = new Set<string>();
const DRAFT_PREFIX = "yike.ui.draft.v1.";
const draftListeners = new Set<() => void>();
const draftKeyEpochs = new Map<string, number>();
let draftRevision = 0;
let clearEpoch = 0;
let storageReadsBlocked = false;
const subscribeDrafts = (listener: () => void) => {
  draftListeners.add(listener);
  return () => {
    draftListeners.delete(listener);
  };
};
const getDraftRevision = () => draftRevision;
function announceDraftChange() {
  draftRevision++;
  for (const listener of draftListeners) listener();
}
function removeStoredDraft(key: string) {
  try {
    sessionStorage.removeItem(key);
  } catch {
    /* Storage can be disabled. */
  }
}
function legacyOperationKey(key: string) {
  return (
    key.startsWith(DRAFT_PREFIX + "send-attempts.") ||
    key.startsWith(DRAFT_PREFIX + "unknown-task-starts.") ||
    key.startsWith(DRAFT_PREFIX + "followup-operations.")
  );
}
export function readLegacyOperationLock(key: string): unknown {
  return legacyOperationKey(key) ? draftMemory.get(key) : undefined;
}
export function forgetLegacyOperationLock(key: string) {
  if (legacyOperationKey(key)) draftMemory.delete(key);
}
const guards = new Set<symbol>();
export function hasUnsavedChanges() {
  return guards.size > 0;
}
/** Includes drafts from pages that have unmounted, without exposing their text. */
export function hasSessionContentAtRisk() {
  const values = new Map<string, unknown>();
  const written = new Set(editedDraftKeys);
  try {
    if (!storageReadsBlocked) {
      for (const key of Object.keys(sessionStorage)) {
        if (!key.startsWith(DRAFT_PREFIX) || draftKeyEpochs.has(key)) continue;
        try {
          values.set(key, JSON.parse(sessionStorage.getItem(key) || "null"));
          if (!draftMemory.has(key)) written.add(key);
        }
        catch { /* Malformed storage is not accepted as a draft. */ }
      }
    }
  } catch { /* Memory still protects unsaved input when storage is denied. */ }
  for (const [key, value] of draftMemory) values.set(key, value);
  for (const [key, value] of values)
    if (sessionContentAtRisk(key.slice(DRAFT_PREFIX.length), value, written.has(key))) return true;
  return false;
}
export function clearLocalDrafts() {
  clearEpoch++;
  editedDraftKeys.clear();
  const keys = new Set([...draftMemory.keys(), ...draftKeyEpochs.keys()]);
  try {
    for (const key of Object.keys(sessionStorage))
      if (key.startsWith(DRAFT_PREFIX)) keys.add(key);
  } catch {
    storageReadsBlocked = true;
  }
  for (const key of draftMemory.keys())
    if (!legacyOperationKey(key)) draftMemory.delete(key);
  for (const key of keys) {
    if (legacyOperationKey(key)) continue;
    draftKeyEpochs.set(key, (draftKeyEpochs.get(key) || 0) + 1);
    removeStoredDraft(key);
  }
  announceDraftChange();
}
function plainRecord(value: unknown): value is Record<string, unknown> {
  return (
    value !== null &&
    typeof value === "object" &&
    !Array.isArray(value) &&
    Object.getPrototypeOf(value) === Object.prototype
  );
}
function safeJson(value: unknown, depth = 0): boolean {
  if (depth > 64) return false;
  if (value === null || typeof value === "string" || typeof value === "boolean")
    return true;
  if (typeof value === "number") return Number.isFinite(value);
  if (Array.isArray(value))
    return value.every((item) => safeJson(item, depth + 1));
  // Optional object fields may be explicitly cleared to undefined in memory;
  // JSON serialization omits them. Undefined array elements remain invalid.
  return (
    plainRecord(value) &&
    Object.entries(value).every(
      ([key, item]) =>
        !["__proto__", "prototype", "constructor"].includes(key) &&
        (item === undefined || safeJson(item, depth + 1)),
    )
  );
}
function matchesInitial(value: unknown, initial: unknown): boolean {
  if (initial === null)
    return (
      value === null ||
      typeof value === "string" ||
      typeof value === "boolean" ||
      (typeof value === "number" && Number.isFinite(value))
    );
  if (Array.isArray(initial))
    return (
      Array.isArray(value) &&
      (initial.length
        ? value.every((item) =>
            initial.some((template) => matchesInitial(item, template)),
          )
        : value.length === 0)
    );
  if (plainRecord(initial))
    return (
      plainRecord(value) &&
      Object.keys(initial).every(
        (key) =>
          Object.hasOwn(value, key) && matchesInitial(value[key], initial[key]),
      ) &&
      (Object.keys(initial).length > 0 || Object.keys(value).length === 0)
    );
  return (
    typeof value === typeof initial &&
    (typeof value !== "number" || Number.isFinite(value))
  );
}
export function useLocalDraft<T>(
  key: string,
  initial: T | (() => T),
  validate?: (value: unknown) => boolean,
) {
  const storageKey = DRAFT_PREFIX + key;
  const base = useMemo(
    () => (typeof initial === "function" ? (initial as () => T)() : initial),
    [storageKey],
  );
  const activeKey = useRef(storageKey);
  activeKey.current = storageKey;
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  useSyncExternalStore(subscribeDrafts, getDraftRevision, getDraftRevision);
  const epoch = clearEpoch;
  const keyEpoch = draftKeyEpochs.get(storageKey) || 0;
  // Empty collections cannot describe their element type. Their callers supply
  // the existing optional validator; nullable complex values also need one.
  const valid = (value: unknown) => {
    try {
      return (
        safeJson(value) &&
        (validate ? validate(value) : matchesInitial(value, base))
      );
    } catch {
      return false;
    }
  };
  const read = () => {
    if (draftMemory.has(storageKey)) {
      const saved = draftMemory.get(storageKey);
      if (valid(saved)) return saved as T;
      draftMemory.delete(storageKey);
      editedDraftKeys.delete(storageKey);
      removeStoredDraft(storageKey);
    }
    try {
      // A failed removeItem must not resurrect a cleared record during this
      // session, even if storage later becomes readable again.
      const raw =
        storageReadsBlocked || draftKeyEpochs.has(storageKey)
          ? null
          : sessionStorage.getItem(storageKey);
      if (raw !== null) {
        try {
          const saved: unknown = JSON.parse(raw);
          if (valid(saved)) {
            draftMemory.set(storageKey, saved);
            if (key.startsWith("followup:v3:") && JSON.stringify(saved) !== JSON.stringify(base))
              editedDraftKeys.add(storageKey);
            return saved as T;
          }
        } catch {
          /* Discard malformed JSON. */
        }
        removeStoredDraft(storageKey);
      }
    } catch {
      /* A denied read still permits an in-memory draft. */
    }
    const fallback = structuredClone(base);
    draftMemory.set(storageKey, fallback);
    return fallback;
  };
  const value = read();
  const stillCurrent = () =>
    mounted.current &&
    activeKey.current === storageKey &&
    epoch === clearEpoch &&
    keyEpoch === (draftKeyEpochs.get(storageKey) || 0);
  const setValue = (next: SetStateAction<T>) => {
    if (!stillCurrent()) return;
    const updated =
      typeof next === "function" ? (next as (previous: T) => T)(read()) : next;
    // Persist synchronously, so clear cannot race a queued effect writing old data.
    draftMemory.set(storageKey, updated);
    const restoredFollowup = key.startsWith("followup:v3:") &&
      JSON.stringify(updated) === JSON.stringify(base);
    if (restoredFollowup) {
      editedDraftKeys.delete(storageKey);
      removeStoredDraft(storageKey);
    } else {
      editedDraftKeys.add(storageKey);
      try {
        sessionStorage.setItem(storageKey, JSON.stringify(updated));
      } catch {
        /* Keep the edit in memory on quota or permission failure. */
      }
    }
    announceDraftChange();
  };
  const clear = () => {
    if (!stillCurrent()) return;
    draftMemory.delete(storageKey);
    editedDraftKeys.delete(storageKey);
    removeStoredDraft(storageKey);
    draftKeyEpochs.set(storageKey, keyEpoch + 1);
    announceDraftChange();
  };
  return [value, setValue, clear] as const;
}
export function useUnsavedChanges(dirty: boolean) {
  useEffect(() => {
    if (!dirty) return;
    const guard = Symbol("unsaved");
    guards.add(guard);
    const handler = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", handler);
    return () => {
      guards.delete(guard);
      window.removeEventListener("beforeunload", handler);
    };
  }, [dirty]);
}
export function useAction() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const lock = useRef(false);
  const run = async <T>(action: () => Promise<T>): Promise<T | undefined> => {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setError("");
    try {
      return await action();
    } catch (e) {
      setError(errorMessage(e));
      return undefined;
    } finally {
      lock.current = false;
      setBusy(false);
    }
  };
  return { busy, error, setError, run };
}
