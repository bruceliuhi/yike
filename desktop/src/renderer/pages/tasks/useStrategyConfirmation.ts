import { useRef, useState } from "react";
import { useApp } from "../../app/context";
import { useOperationLedger } from "../../app/operationLedger";
import { boundedRequest } from "../../app/boundedRequest";
import { ServiceError } from "../../services/contracts";
import type { TaskDraft } from "../../domain/models";
import { taskFingerprint } from "../../domain/task";
import { hashText } from "../../domain/taskOperations";
import { strategyPrepareRequest, parseStrategyView } from "../../domain/researchStrategies";
import { newStrategyRecord, parseStrategyRecord, strategyRecordKey, strategyRecordPending, beginStrategyMutation,
  recoverStrategyReceipt, recordStrategyReceipt, strategyRetryRequest, type StrategyRecord, type StrategyRequest } from "../../domain/strategyConfirmation";
import type { StrategyReceipt, StrategyView, ConfirmStrategyRequest, RevokeStrategyRequest } from "../../../shared/researchStrategies";
import { useTaskScope } from "./useTaskScope";

const UNKNOWN = "策略操作尚未核实，请查询原请求；不要重新创建确认。";
interface State { identity: object; busy?: boolean; error?: string; prepared?: StrategyReceipt;
  view?: StrategyView; matchesCurrent?: boolean; activated?: boolean; activationRecord?: string }

/** Event-driven: rendering/remounting never prepares or confirms a strategy. */
export function useStrategyConfirmation(draft: TaskDraft, limits: { max_records: number; max_runtime_seconds: number }) {
  const { service, session } = useApp();
  const api = service.researchStrategies;
  const variant = JSON.stringify([taskFingerprint(draft), limits]);
  const scope = useTaskScope(variant);
  const [entries, setEntries, getEntries] = useOperationLedger("research-strategy-operations", session.userId);
  const [state, setState] = useState<State>({ identity: scope.identity });
  const running = useRef(new Set<object>());
  const key = JSON.stringify([session.userId, session.accountScope?.id ?? null, session.accountScope?.version ?? null, draft.id]);
  let record: StrategyRecord | null = null;
  let recordError = false;
  try { if (entries[key]) record = parseStrategyRecord(JSON.parse(entries[key])); }
  catch { recordError = true; }
  const shown: State = state.identity === scope.identity ? state : { identity: scope.identity };

  function show(patch: Partial<State>) {
    if (scope.current()) setState(previous => ({ ...(previous.identity === scope.identity ? previous : {}), identity: scope.identity, ...patch }));
  }
  function write(next: StrategyRecord, expected: StrategyRecord | null) {
    const target = strategyRecordKey(next);
    setEntries(latest => {
      const actual = latest[target] ? parseStrategyRecord(JSON.parse(latest[target])) : null;
      if (JSON.stringify(actual) !== JSON.stringify(expected)) throw new Error(UNKNOWN);
      return { ...latest, [target]: JSON.stringify(next) };
    });
  }
  async function call(operation: () => Promise<unknown>) {
    if (!scope.current()) throw new Error(UNKNOWN);
    return boundedRequest(operation, { timeoutMessage: UNKNOWN });
  }
  async function run(operation: () => Promise<void>, stillValid?: () => boolean): Promise<boolean> {
    if (running.current.has(scope.identity)) return false;
    running.current.add(scope.identity);
    show({ busy: true, error: undefined });
    try {
      if (!api || !session.authenticated || !session.userId || recordError) throw new Error(UNKNOWN);
      await operation();
      if (stillValid && !stillValid()) throw new Error(UNKNOWN);
      return scope.current();
    } catch (error) {
      show({ activated: false, error: error instanceof ServiceError ? error.message : UNKNOWN });
      return false;
    } finally {
      running.current.delete(scope.identity);
      show({ busy: false });
    }
  }
  async function settle(original: StrategyRecord, raw: unknown) {
    const receipt = await recoverStrategyReceipt(raw, original);
    const next = await recordStrategyReceipt(original, receipt);
    // May settle only this captured account's opaque ledger after unmount/switch.
    write(next, original);
    return { next, receipt };
  }
  function current(view: StrategyView) {
    return view.is_current && view.profile_current && view.state !== "REVOKED";
  }
  async function loadKnown(original: StrategyRecord, activate = false) {
    let working = original;
    const first = await settle(working, await call(() => api!.getReceipt(working.prepare.request_id)));
    working = first.next;
    if (!scope.current()) return;
    const matchesCurrent = working.context.fingerprint === await hashText(variant);
    show({ prepared: first.receipt, matchesCurrent, activated: false });
    let hasConfirmation = false;
    for (const name of ["confirm", "revoke"] as const) {
      const op = working[name];
      if (!op) continue;
      const result = await settle(working, await call(() => api!.getReceipt(op.request_id)));
      working = result.next;
      if (name === "confirm") hasConfirmation = result.receipt.state === "CONFIRMED";
      if (!scope.current()) return;
    }
    const view = parseStrategyView(await call(() => api!.getStrategy(first.receipt.strategy_version_id)), first.receipt);
    show({ view, activationRecord: JSON.stringify(working),
      activated: activate && matchesCurrent && hasConfirmation && current(view) && view.state === "CONFIRMED" });
  }
  const prepare = () => run(async () => {
    if (record && strategyRecordPending(record)) throw new Error(UNKNOWN);
    const fingerprint = await hashText(variant);
    if (!scope.current()) return;
    if (record?.context.fingerprint === fingerprint) { await loadKnown(record); return; }
    const request = strategyPrepareRequest(structuredClone(draft), crypto.randomUUID(), limits);
    const pending = await newStrategyRecord(request, { userId: session.userId!, accountScopeId: session.accountScope?.id ?? null,
      scopeVersion: session.accountScope?.version ?? null, fingerprint });
    if (!scope.current()) return;
    write(pending, record);
    const result = await settle(pending, await call(() => api!.prepare(request)));
    if (!scope.current()) return;
    show({ prepared: result.receipt, matchesCurrent: true, activated: false });
    const view = parseStrategyView(await call(() => api!.getStrategy(result.receipt.strategy_version_id)), result.receipt);
    show({ view });
  });
  const reconcile = () => run(async () => {
    if (!record) throw new Error(UNKNOWN);
    await loadKnown(record);
  });
  const confirm = (humanConfirmed: boolean) => run(async () => {
    if (humanConfirmed !== true || !record || strategyRecordPending(record) || !shown.prepared || !shown.matchesCurrent) throw new Error(UNKNOWN);
    if (record.context.fingerprint !== await hashText(variant) || !scope.current()) throw new Error(UNKNOWN);
    const prepared = shown.prepared;
    const view = parseStrategyView(await call(() => api!.getStrategy(prepared.strategy_version_id)), prepared);
    if (!current(view)) throw new Error(UNKNOWN);
    if (record.confirm?.state === "RECORDED") { await loadKnown(record, true); return; }
    const request: ConfirmStrategyRequest = { schema_version: "strategy-confirmation-v1", request_id: crypto.randomUUID(),
      strategy_version_id: prepared.strategy_version_id, configuration_sha256: prepared.configuration_sha256, human_confirmed: true };
    const pending = await beginStrategyMutation(record, "CONFIRM", request);
    if (!scope.current()) return;
    write(pending, record);
    const result = await settle(pending, await call(() => api!.confirm(request)));
    if (!scope.current()) return;
    const after = parseStrategyView(await call(() => api!.getStrategy(prepared.strategy_version_id)), prepared);
    show({ view: after, activationRecord: JSON.stringify(result.next), activated: current(after) && after.state === "CONFIRMED" });
  });
  const revoke = () => run(async () => {
    if (!record?.binding || strategyRecordPending(record)) throw new Error(UNKNOWN);
    const request: RevokeStrategyRequest = { schema_version: "strategy-confirmation-v1", request_id: crypto.randomUUID(),
      strategy_version_id: record.binding.strategy_version_id };
    const pending = await beginStrategyMutation(record, "REVOKE", request);
    if (!scope.current()) return;
    write(pending, record);
    show({ activated: false });
    const result = await settle(pending, await call(() => api!.revoke(request)));
    if (!scope.current()) return;
    await loadKnown(result.next);
  });
  const retry = () => run(async () => {
    if (!record) throw new Error(UNKNOWN);
    const pendingOperation = [record.prepare, record.confirm, record.revoke].find(value => value?.state === "PENDING");
    if (!pendingOperation) throw new Error(UNKNOWN);
    let recovered: unknown;
    let found = true;
    try {
      recovered = await call(() => api!.getReceipt(pendingOperation.request_id));
    } catch (error) {
      if (!(error instanceof ServiceError) || error.status !== 404 || error.code !== "request_not_found") throw error;
      found = false;
    }
    if (found) {
      const result = await settle(record, recovered);
      if (scope.current()) await loadKnown(result.next);
      return;
    }
    // Only a conclusive not-found response permits an explicit same-request POST.
    if (record.context.fingerprint !== await hashText(variant)) throw new Error(UNKNOWN);
    let request: StrategyRequest;
    let dispatch: () => Promise<unknown>;
    if (record.prepare.state === "PENDING") {
      const original = strategyPrepareRequest(structuredClone(draft), record.prepare.request_id, limits);
      request = original;
      dispatch = () => api!.prepare(original);
    } else if (record.confirm?.state === "PENDING" && record.binding) {
      const original: ConfirmStrategyRequest = { schema_version: "strategy-confirmation-v1", request_id: record.confirm.request_id,
        strategy_version_id: record.binding.strategy_version_id, configuration_sha256: record.binding.configuration_sha256, human_confirmed: true };
      request = original;
      dispatch = () => api!.confirm(original);
    } else if (record.revoke?.state === "PENDING" && record.binding) {
      const original: RevokeStrategyRequest = { schema_version: "strategy-confirmation-v1", request_id: record.revoke.request_id,
        strategy_version_id: record.binding.strategy_version_id };
      request = original;
      dispatch = () => api!.revoke(original);
    } else throw new Error(UNKNOWN);
    await strategyRetryRequest(record, request);
    if (!scope.current()) return;
    // A same-key durable write also rechecks storage health immediately before retry.
    write(record, record);
    const result = await settle(record, await call(dispatch));
    if (!scope.current()) return;
    await loadKnown(result.next);
  });
  const confirmed = Boolean(shown.activated && shown.matchesCurrent && record && !strategyRecordPending(record)
    && record.confirm?.state === "RECORDED" && !record.revoke && shown.activationRecord === JSON.stringify(record)
    && shown.view && current(shown.view) && shown.view.state === "CONFIRMED");
  const recheck = () => run(async () => {
    if (!confirmed || !record || !shown.prepared) throw new Error(UNKNOWN);
    const view = parseStrategyView(await call(() => api!.getStrategy(shown.prepared!.strategy_version_id)), shown.prepared);
    if (!current(view) || view.state !== "CONFIRMED") throw new Error(UNKNOWN);
    show({ view });
  }, () => {
    // Another consumer can change the ledger while a valid view is in flight.
    // Read durable state synchronously; a captured render value/ref is too old.
    const latest = getEntries()[key];
    return Boolean(record && latest && JSON.stringify(parseStrategyRecord(JSON.parse(latest))) === JSON.stringify(record));
  });
  return { available: Boolean(api), busy: Boolean(shown.busy), error: shown.error ?? (recordError ? UNKNOWN : null),
    prepared: shown.matchesCurrent ? shown.prepared ?? null : null, view: shown.view ?? null,
    historyReceipt: shown.prepared ?? null,
    historyOnly: Boolean(shown.prepared && !shown.matchesCurrent), confirmed,
    pending: record ? strategyRecordPending(record) : false, prepare, confirm, revoke, reconcile, retry, recheck };
}
