import { z } from "zod";
import { operationLedgerKey } from "../../app/operationLedger";
import type { Session } from "../../domain/models";
import { followupKey, type FollowupBinding } from "../../domain/followup";

const id = z.string().trim().min(1).max(512);
const ownerSchema = z
  .object({
    userId: id,
    accountScope: z
      .object({ id, version: z.number().int().positive() })
      .strict()
      .nullable(),
  })
  .strict();
const bindingSchema = z
  .object({
    opportunityId: id,
    profileVersionId: id,
    action: z.enum(["create", "correct", "void", "mark-read", "legacy-create"]),
    targetId: z.string().max(512),
    targetRevision: z.number().int().nonnegative(),
    requestId: id,
  })
  .strict();
const draftReferenceSchema = z
  .object({
    key: z.string().min(1).max(4096),
    hash: z.string().regex(/^[a-f0-9]{64}$/),
  })
  .strict();
export type FollowupDraftReference = z.infer<typeof draftReferenceSchema>;
const envelopeSchema = z
  .object({
    schemaVersion: z.literal(2),
    owner: ownerSchema,
    pending: bindingSchema,
    draft: draftReferenceSchema.optional(),
  })
  .strict();
const PREFIX = "yike.ui.followup-operation.v2.";
export type FollowupOwner = z.infer<typeof ownerSchema>;
export type HistoricalFollowupOperation = {
  binding: FollowupBinding;
  accountScope: FollowupOwner["accountScope"] | "unbound";
};
export function followupOwner(session: Session): FollowupOwner {
  if (!session.authenticated) throw new Error("请先登录客户空间。");
  return ownerSchema.parse({
    userId: session.userId,
    accountScope: session.accountScope ?? null,
  });
}
export function followupOperationStorageKey(owner: FollowupOwner) {
  return (
    PREFIX +
    encodeURIComponent(JSON.stringify(owner.userId)) +
    "." +
    encodeURIComponent(JSON.stringify(owner.accountScope))
  );
}
export function parseFollowupKey(key: string): FollowupBinding {
  const parts = z
    .tuple([
      id,
      id,
      bindingSchema.shape.action,
      z.string().max(512),
      z.number().int().nonnegative(),
      id,
    ])
    .parse(JSON.parse(key));
  const binding = {
    opportunityId: parts[0],
    profileVersionId: parts[1],
    action: parts[2],
    targetId: parts[3],
    targetRevision: parts[4],
    requestId: parts[5],
  };
  if (followupKey(binding) !== key) throw new Error("原跟进操作标识不完整。");
  return binding;
}
function legacyBindings(raw: string | null) {
  if (raw === null) return [];
  const entries = z
    .record(z.string(), z.literal("PENDING"))
    .parse(JSON.parse(raw));
  return Object.keys(entries).map(parseFollowupKey);
}
export function readFollowupOperations(owner: FollowupOwner) {
  let pending: FollowupBinding | null = null;
  let draft: FollowupDraftReference | undefined;
  const historical: HistoricalFollowupOperation[] = [];
  const legacyKey = operationLedgerKey("followup-operations", owner.userId);
  const oldSessionKey = "yike.ui.draft.v1.followup-operations." + owner.userId;
  const oldSession = sessionStorage.getItem(oldSessionKey);
  if (oldSession !== null) {
    // Preserve old session-only locks durably, without assigning today's space.
    const merged = Object.fromEntries(
      [
        ...legacyBindings(localStorage.getItem(legacyKey)),
        ...legacyBindings(oldSession),
      ].map((b) => [followupKey(b), "PENDING"]),
    );
    const serialized = JSON.stringify(merged);
    localStorage.setItem(legacyKey, serialized);
    if (localStorage.getItem(legacyKey) !== serialized)
      throw new Error("旧跟进操作未能可靠保留。");
  }
  for (const binding of legacyBindings(localStorage.getItem(legacyKey)))
    historical.push({ binding, accountScope: "unbound" });
  const prefix =
    PREFIX + encodeURIComponent(JSON.stringify(owner.userId)) + ".";
  const key = followupOperationStorageKey(owner);
  for (let index = 0; index < localStorage.length; index++) {
    const storedKey = localStorage.key(index);
    if (storedKey === null || !storedKey.startsWith(prefix)) continue;
    const entry = envelopeSchema.parse(
      JSON.parse(localStorage.getItem(storedKey) || "null"),
    );
    if (followupOperationStorageKey(entry.owner) !== storedKey)
      throw new Error("跟进操作身份记录不匹配。");
    if (entry.owner.userId !== owner.userId) continue;
    if (storedKey === key) {
      pending = entry.pending;
      draft = entry.draft;
    } else if (
      entry.owner.accountScope?.id === owner.accountScope?.id ||
      entry.owner.accountScope === null ||
      owner.accountScope === null
    )
      historical.push({
        binding: entry.pending,
        accountScope: entry.owner.accountScope,
      });
  }
  return { pending, historical, ...(draft ? { draft } : {}) };
}
export function storeFollowupOperation(
  owner: FollowupOwner,
  pending: FollowupBinding,
  draft?: FollowupDraftReference,
) {
  const existing = readFollowupOperations(owner);
  if (existing.pending || existing.historical.length)
    throw new Error("请先核对未完成的跟进操作，不能重复保存。");
  const serialized = JSON.stringify(
    envelopeSchema.parse({
      schemaVersion: 2,
      owner,
      pending,
      ...(draft ? { draft } : {}),
    }),
  );
  const key = followupOperationStorageKey(owner);
  localStorage.setItem(key, serialized);
  if (localStorage.getItem(key) !== serialized)
    throw new Error("原跟进操作未能可靠保存。");
}
export function finishFollowupOperation(
  owner: FollowupOwner,
  binding: FollowupBinding,
) {
  const key = followupOperationStorageKey(owner);
  const entry = envelopeSchema.parse(
    JSON.parse(localStorage.getItem(key) || "null"),
  );
  if (
    followupOperationStorageKey(entry.owner) !== key ||
    followupKey(entry.pending) !== followupKey(binding)
  )
    throw new Error("原跟进操作记录已变化，保护仍保留。");
  localStorage.removeItem(key);
  if (localStorage.getItem(key) !== null)
    throw new Error("原跟进操作未能可靠更新。");
}
