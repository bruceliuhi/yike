import { z } from "zod";
import { hashText } from "./taskOperations";
import { parseStrategyReceipt } from "./researchStrategies";
import {
  prepareStrategySchema, confirmStrategySchema, revokeStrategySchema, strategyReceiptSchema, strategyUuidSchema,
  type PrepareStrategyRequest, type ConfirmStrategyRequest, type RevokeStrategyRequest, type StrategyReceipt,
} from "../../shared/researchStrategies";

const FAILURE = "策略原请求记录无法核对，保护已保留。";
const hash = z.string().regex(/^[a-f0-9]{64}$/);
const id = z.string().min(1).max(128).refine(value => value.trim() === value && !/[\p{Cc}\p{Cf}]/u.test(value));
const operation = z.object({ request_id: strategyUuidSchema, request_sha256: hash,
  state: z.enum(["PENDING", "RECORDED"]) }).strict();
const binding = z.object({ strategy_version_id: strategyUuidSchema,
  configuration_sha256: hash, profile_sha256: hash }).strict();
const contextSchema = z.object({ userId: id, accountScopeId: id.nullable(),
  scopeVersion: z.number().int().positive().max(Number.MAX_SAFE_INTEGER).nullable(), fingerprint: hash }).strict()
  .refine(value => (value.accountScopeId === null) === (value.scopeVersion === null));
const recordSchema = z.object({ version: z.literal(1), draft_id: strategyUuidSchema, context: contextSchema,
  prepare: operation, binding: binding.nullable(), confirm: operation.nullable(), revoke: operation.nullable() }).strict()
  .refine(value => value.prepare.state === "RECORDED" ? value.binding !== null
    : value.binding === null && value.confirm === null && value.revoke === null)
  .refine(value => new Set([value.prepare, value.confirm, value.revoke].filter(value => value !== null)
    .map(value => value.request_id)).size === [value.prepare, value.confirm, value.revoke].filter(value => value !== null).length);

export type StrategyRecord = z.infer<typeof recordSchema>;
export type StrategyRecordContext = z.infer<typeof contextSchema>;
export type StrategyRequest = PrepareStrategyRequest | ConfirmStrategyRequest | RevokeStrategyRequest;
type OperationName = "PREPARE" | "CONFIRM" | "REVOKE";
const slot = { PREPARE: "prepare", CONFIRM: "confirm", REVOKE: "revoke" } as const;

export function parseStrategyRecord(value: unknown): StrategyRecord {
  const parsed = recordSchema.safeParse(value);
  if (!parsed.success) throw new Error(FAILURE);
  return parsed.data;
}
export function strategyRecordKey(record: StrategyRecord): string {
  const r = parseStrategyRecord(record);
  return JSON.stringify([r.context.userId, r.context.accountScopeId, r.context.scopeVersion, r.draft_id]);
}
export function validStrategyEntry(key: string, value: string): boolean {
  try {
    if (value.length > 4096) return false;
    return strategyRecordKey(parseStrategyRecord(JSON.parse(value))) === key;
  } catch { return false; }
}
function parseRequest(value: unknown): { name: OperationName; request: StrategyRequest } {
  const prepared = prepareStrategySchema.safeParse(value);
  if (prepared.success) return { name: "PREPARE", request: prepared.data };
  const confirmed = confirmStrategySchema.safeParse(value);
  if (confirmed.success) return { name: "CONFIRM", request: confirmed.data };
  const revoked = revokeStrategySchema.safeParse(value);
  if (revoked.success) return { name: "REVOKE", request: revoked.data };
  throw new Error(FAILURE);
}
function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value !== null && typeof value === "object") return `{${Object.entries(value)
    .sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0).map(([key, item]) => `${JSON.stringify(key)}:${canonical(item)}`).join(",")}}`;
  return JSON.stringify(value);
}
/** A local original-request digest, never the server's configuration SHA. */
export async function strategyRequestDigest(request: unknown): Promise<string> {
  return hashText(canonical(parseRequest(request).request));
}
export async function newStrategyRecord(request: PrepareStrategyRequest, context: StrategyRecordContext): Promise<StrategyRecord> {
  const parsed = prepareStrategySchema.parse(request);
  return parseStrategyRecord({ version: 1, draft_id: parsed.draft_id, context,
    prepare: { request_id: parsed.request_id, request_sha256: await strategyRequestDigest(parsed), state: "PENDING" },
    binding: null, confirm: null, revoke: null });
}
export function strategyRecordPending(record: StrategyRecord): boolean {
  const r = parseStrategyRecord(record);
  return [r.prepare, r.confirm, r.revoke].some(value => value?.state === "PENDING");
}
export async function beginStrategyMutation(record: StrategyRecord, name: "CONFIRM" | "REVOKE", request: StrategyRequest): Promise<StrategyRecord> {
  const r = parseStrategyRecord(record);
  const expected = parseRequest(request);
  if (expected.name !== name || strategyRecordPending(r) || !r.binding || r.revoke?.state === "RECORDED"
    || r[slot[name]] !== null || !("strategy_version_id" in expected.request)
    || expected.request.strategy_version_id !== r.binding.strategy_version_id
    || ("configuration_sha256" in expected.request && expected.request.configuration_sha256 !== r.binding.configuration_sha256))
    throw new Error(FAILURE);
  return parseStrategyRecord({ ...r, [slot[name]]: {
    request_id: expected.request.request_id, request_sha256: await strategyRequestDigest(expected.request), state: "PENDING",
  } });
}
export async function strategyRetryRequest(record: StrategyRecord, request: StrategyRequest): Promise<StrategyRequest> {
  const r = parseStrategyRecord(record);
  const expected = parseRequest(request);
  const original = r[slot[expected.name]];
  if (original?.state !== "PENDING" || original.request_id !== expected.request.request_id
    || original.request_sha256 !== await strategyRequestDigest(expected.request)) throw new Error(FAILURE);
  return expected.request;
}

export async function recoverStrategyReceipt(raw: unknown, record: StrategyRecord): Promise<StrategyReceipt> {
  try {
    const r = parseStrategyRecord(record);
    const receipt = strategyReceiptSchema.parse(raw);
    const original = r[slot[receipt.operation]];
    if (!original || original.request_id !== receipt.request_id || r.draft_id !== receipt.draft_id) throw new Error(FAILURE);
    const prepare: PrepareStrategyRequest = prepareStrategySchema.parse({ schema_version: "strategy-confirmation-v1",
      request_id: r.prepare.request_id, draft_id: receipt.draft_id, draft_revision: receipt.draft_revision,
      profile_version_id: receipt.profile_version_id, configuration: receipt.snapshot.configuration,
      platforms: receipt.snapshot.platforms, max_records: receipt.snapshot.max_records,
      max_runtime_seconds: receipt.snapshot.max_runtime_seconds });
    // This hash was saved BEFORE the call, not learned from the response.
    if (await strategyRequestDigest(prepare) !== r.prepare.request_sha256) throw new Error(FAILURE);
    if (r.binding && (r.binding.strategy_version_id !== receipt.strategy_version_id
      || r.binding.configuration_sha256 !== receipt.configuration_sha256 || r.binding.profile_sha256 !== receipt.profile_sha256))
      throw new Error(FAILURE);
    if (receipt.operation === "PREPARE") return parseStrategyReceipt(receipt, prepare);
    if (!r.binding) throw new Error(FAILURE);
    const expected = { schema_version: "strategy-confirmation-v1" as const, request_id: original.request_id,
      strategy_version_id: r.binding.strategy_version_id,
      ...(receipt.operation === "CONFIRM" ? { configuration_sha256: r.binding.configuration_sha256, human_confirmed: true as const } : {}) };
    if (await strategyRequestDigest(expected) !== original.request_sha256) throw new Error(FAILURE);
    // Reconstruct only the already digest-checked binding for the common parser.
    // It is not an original PREPARE receipt and is never returned or displayed.
    const checkedBinding = parseStrategyReceipt({ ...receipt, operation: "PREPARE", request_id: r.prepare.request_id }, prepare);
    return parseStrategyReceipt(receipt, expected, checkedBinding);
  } catch { throw new Error(FAILURE); }
}
export async function recordStrategyReceipt(record: StrategyRecord, raw: unknown): Promise<StrategyRecord> {
  const r = parseStrategyRecord(record);
  const receipt = await recoverStrategyReceipt(raw, r);
  return parseStrategyRecord({ ...r, binding: { strategy_version_id: receipt.strategy_version_id,
    configuration_sha256: receipt.configuration_sha256, profile_sha256: receipt.profile_sha256 },
    [slot[receipt.operation]]: { ...r[slot[receipt.operation]], state: "RECORDED" } });
}
