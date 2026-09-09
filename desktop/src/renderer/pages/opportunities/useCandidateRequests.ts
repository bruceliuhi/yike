import { useRef, useState } from "react";
import { z } from "zod";
import { useApp } from "../../app/context";
import {
  useOperationLedger,
  type OperationEntries,
} from "../../app/operationLedger";
import { boundedRequest } from "../../app/boundedRequest";
import { ServiceError } from "../../services/contracts";
import { useTaskScope } from "../tasks/useTaskScope";
import { parseCandidateOperation } from "../../domain/candidateReviewOperation";
import {
  candidateReviewRequestSchema,
  sourceVerificationRequestSchema,
  type CandidateReviewResultDto,
} from "../../../shared/candidateReviewApi";
import {
  newCandidateRequestOperation,
  parseCandidateRequestOperation,
  candidateRequestEntry,
  recoverCandidateRequestResult,
  type CandidateRequestOperation,
} from "../../domain/candidateRequestOperation";

const UNKNOWN = "原请求尚未核实，请先核对；不会自动重复判断、核验或入库。";
const requestSchema = z.union([
  candidateReviewRequestSchema,
  sourceVerificationRequestSchema,
]);
interface State {
  identity: object;
  busy?: boolean;
  error?: string;
  result?: CandidateReviewResultDto;
}
function decode(entries: OperationEntries): CandidateRequestOperation[] {
  return Object.entries(entries).map(([key, value]) => {
    const operation = parseCandidateRequestOperation(key, value);
    if (!operation) throw new Error(UNKNOWN);
    return operation;
  });
}
function binding(operation: CandidateRequestOperation) {
  return {
    candidateId: operation.candidateId,
    candidateRevision: operation.binding[0],
    sourceVersionId: operation.binding[1],
    profileId: operation.binding[2],
    profileVersion: operation.binding[3],
  };
}
function sameScope(a: CandidateRequestOperation, b: CandidateRequestOperation) {
  return a.scopeId === b.scopeId && a.scopeVersion === b.scopeVersion;
}
function hasRetry(
  operation: CandidateRequestOperation,
  records: CandidateRequestOperation[],
) {
  return (
    operation.action === "ASSESS" &&
    records.some(
      (other) =>
        sameScope(other, operation) &&
        other.candidateId === operation.candidateId &&
        other.action === "ASSESS" &&
        other.retryOf[0] === (operation.invocationId ?? operation.requestId),
    )
  );
}

/** Explicit events only. Reads and remounts never create IDs, POST, or retry. */
export function useCandidateRequests(variant = "") {
  const { service, session } = useApp(),
    api = service.candidateReview;
  const scope = useTaskScope(variant);
  const [entries, setEntries, getEntries] = useOperationLedger(
    "candidate-request-operations",
    session.userId,
  );
  const [, , getLegacyEntries] = useOperationLedger(
    "candidate-reviews",
    session.userId,
  );
  const [state, setState] = useState<State>({ identity: scope.identity });
  const running = useRef(new Set<object>());
  const visible = (record: CandidateRequestOperation) =>
    record.scopeId === (session.accountScope?.id ?? null) &&
    record.scopeVersion === (session.accountScope?.version ?? null);
  let operations: CandidateRequestOperation[] = [],
    malformed = false;
  try {
    operations = session.authenticated ? decode(entries).filter(visible) : [];
  } catch {
    malformed = true;
  }
  const shown: State =
    state.identity === scope.identity ? state : { identity: scope.identity };
  function show(patch: Partial<State>) {
    if (scope.current())
      setState((previous) => ({
        ...(previous.identity === scope.identity ? previous : {}),
        identity: scope.identity,
        ...patch,
      }));
  }
  function lookup(key: string) {
    const op = decode(getEntries()).find((value) => value.key === key);
    if (!op || !visible(op)) throw new Error(UNKNOWN);
    return op;
  }
  function replace(
    next: CandidateRequestOperation,
    original: CandidateRequestOperation,
  ) {
    const before = candidateRequestEntry(original),
      after = candidateRequestEntry(next);
    setEntries((latest) => {
      if (latest[before.key] !== before.value) throw new Error(UNKNOWN);
      return { ...latest, [after.key]: after.value };
    });
  }
  function candidateSnapshot(values: OperationEntries, candidateId: string) {
    return JSON.stringify(
      decode(values)
        .filter(
          (record) => visible(record) && record.candidateId === candidateId,
        )
        .map((record) => [record.key, candidateRequestEntry(record).value])
        .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0)),
    );
  }
  function insert(
    next: CandidateRequestOperation,
    prior: string,
    parent?: CandidateRequestOperation,
  ) {
    checkLegacy(next.candidateId);
    const entry = candidateRequestEntry(next);
    setEntries((latest) => {
      const records = decode(latest);
      if (candidateSnapshot(latest, next.candidateId) !== prior)
        throw new Error(UNKNOWN);
      if (latest[entry.key] !== undefined) throw new Error(UNKNOWN);
      if (parent) {
        const expected = candidateRequestEntry(parent);
        if (
          latest[expected.key] !== expected.value ||
          hasRetry(parent, records)
        )
          throw new Error(UNKNOWN);
      }
      if (
        records.some(
          (record) =>
            sameScope(record, next) &&
            record.candidateId === next.candidateId &&
            record.key !== parent?.key &&
            record.state !== "RECORDED" &&
            !hasRetry(record, records),
        )
      )
        throw new Error(UNKNOWN);
      return { ...latest, [entry.key]: entry.value };
    });
  }
  function checkLegacy(candidateId: string) {
    if (
      Object.keys(getLegacyEntries()).some(
        (key) => parseCandidateOperation(key)?.candidateId === candidateId,
      )
    )
      throw new Error(UNKNOWN);
  }
  async function call<T>(operation: (signal: AbortSignal) => Promise<T>) {
    return boundedRequest(
      (signal) => {
        if (!scope.current()) throw new Error(UNKNOWN);
        return operation(signal);
      },
      { timeoutMessage: UNKNOWN },
    );
  }
  async function settle(original: CandidateRequestOperation, raw: unknown) {
    const recovered = await recoverCandidateRequestResult(raw, original);
    // Captured setter is tied to the original user even after unmount or scope change.
    replace(recovered.operation, original);
    show({ result: recovered.result });
    return recovered;
  }
  async function run(
    operation: () => Promise<CandidateReviewResultDto>,
  ): Promise<CandidateReviewResultDto | null> {
    if (running.current.has(scope.identity)) return null;
    running.current.add(scope.identity);
    show({ busy: true, error: undefined, result: undefined });
    try {
      if (
        !scope.current() ||
        !api ||
        !session.authenticated ||
        !session.userId ||
        malformed
      )
        throw new Error(UNKNOWN);
      getEntries();
      const result = await operation();
      return scope.current() ? result : null;
    } catch (error) {
      show({ error: error instanceof ServiceError ? error.message : UNKNOWN });
      return null;
    } finally {
      running.current.delete(scope.identity);
      show({ busy: false });
    }
  }
  const submit = (input: unknown) =>
    run(async () => {
      // Parse/copy before hashing; editor mutations cannot alter the original request.
      const request = requestSchema.parse(input);
      if ("retryOf" in request && request.retryOf != null)
        throw new Error(UNKNOWN);
      const prior = candidateSnapshot(getEntries(), request.candidateId);
      const op = await newCandidateRequestOperation(
        request,
        session.accountScope ?? null,
      );
      if (!scope.current()) throw new Error(UNKNOWN);
      insert(op, prior);
      const raw = await call((signal) => {
        checkLegacy(request.candidateId);
        return "action" in request
          ? api!.review(request, signal)
          : api!.verifySource(request, signal);
      });
      return (await settle(op, raw)).result;
    });
  const reconcile = (key: string) =>
    run(async () => {
      const original = lookup(key);
      const raw = await call((signal) =>
        api!.getRequest(
          original.requestId,
          { binding: binding(original) },
          signal,
        ),
      );
      return (await settle(original, raw)).result;
    });
  const retryAssessment = (key: string, confirmed: boolean) =>
    run(async () => {
      if (confirmed !== true) throw new Error(UNKNOWN);
      const original = lookup(key);
      if (original.action !== "ASSESS") throw new Error(UNKNOWN);
      const { operation: parent, result } = await settle(
        original,
        await call((signal) =>
          api!.getRequest(
            original.requestId,
            { binding: binding(original) },
            signal,
          ),
        ),
      );
      if (
        !scope.current() ||
        (result.kind !== "failure" &&
          !(result.kind === "pending" && result.status === "UNKNOWN"))
      )
        throw new Error(UNKNOWN);
      const request = {
        ...binding(parent),
        action: "ASSESS" as const,
        requestId: crypto.randomUUID(),
        retryOf: parent.invocationId ?? parent.requestId,
      };
      const prior = candidateSnapshot(getEntries(), parent.candidateId);
      const op = await newCandidateRequestOperation(
        request,
        session.accountScope ?? null,
      );
      if (!scope.current()) throw new Error(UNKNOWN);
      // Recheck the freshly observed parent and absence of a retry child at the durable write.
      insert(op, prior, parent);
      const raw = await call((signal) => {
        checkLegacy(request.candidateId);
        return api!.review(request, signal);
      });
      return (await settle(op, raw)).result;
    });
  return {
    available: Boolean(api),
    busy: Boolean(shown.busy),
    error: shown.error ?? (malformed ? UNKNOWN : null),
    operations,
    result: shown.result ?? null,
    submit,
    reconcile,
    retryAssessment,
  };
}
