import { z } from "zod";
import { taskDraftOwner } from "../../app/taskDraft";
import { materialPendingSchema, type MaterialPending } from "../../domain/materials";
import type { Session } from "../../domain/models";

const ownerSchema = z.object({
  userId: z.string().trim().min(1).max(512),
  accountScope: z.object({
    id: z.string().trim().min(1).max(512),
    version: z.number().int().positive(),
  }).strict().nullable(),
}).strict();
const entrySchema = z.object({
  schemaVersion: z.literal(2),
  owner: ownerSchema,
  pending: materialPendingSchema,
}).strict();
export type MaterialOwner = z.infer<typeof ownerSchema>;
export type HistoricalMaterialOperation = {
  requestId: string;
  profileVersionId: string;
  accountScope: MaterialOwner["accountScope"] | "unbound";
};
export function materialOwner(session: Session): MaterialOwner {
  if (!session.authenticated) throw new Error("请先登录客户空间。");
  return ownerSchema.parse({userId: session.userId, accountScope: session.accountScope ?? null});
}
export function materialOperationKey(owner: MaterialOwner, profileVersionId: string) {
  return "yike.ui.material-operation.v2." + encodeURIComponent(owner.userId) + "." +
    encodeURIComponent(taskDraftOwner(owner.userId, owner.accountScope ?? undefined)) + "." +
    encodeURIComponent(profileVersionId);
}
export function legacyMaterialOperationKey(userId: string, profileVersionId: string) {
  return "yike.ui.material-operation.v1." + encodeURIComponent(userId) + "." + encodeURIComponent(profileVersionId);
}
export function readMaterialOperations(owner: MaterialOwner, profileVersionId: string) {
  const key = materialOperationKey(owner, profileVersionId);
  let pending: MaterialPending | null = null;
  const historical: HistoricalMaterialOperation[] = [];
  const legacy = localStorage.getItem(legacyMaterialOperationKey(owner.userId, profileVersionId));
  if (legacy !== null) {
    const record = materialPendingSchema.parse(JSON.parse(legacy));
    if (record.profileVersionId !== profileVersionId) throw new Error("旧资料操作与画像不匹配。");
    // Never infer an old operation's customer space from the currently open space.
    historical.push({requestId: record.requestId, profileVersionId, accountScope: "unbound"});
  }
  const prefix = "yike.ui.material-operation.v2." + encodeURIComponent(owner.userId) + ".";
  for (let index = 0; index < localStorage.length; index++) {
    const storedKey = localStorage.key(index);
    if (storedKey === null) continue;
    if (!storedKey.startsWith(prefix) || !storedKey.endsWith("." + encodeURIComponent(profileVersionId))) continue;
    const entry = entrySchema.parse(JSON.parse(localStorage.getItem(storedKey) || "null"));
    if (materialOperationKey(entry.owner, entry.pending.profileVersionId) !== storedKey)
      throw new Error("资料操作记录身份不匹配。");
    // Dots are valid in IDs and are not escaped by encodeURIComponent. The
    // prefix/suffix filter is only a scan optimization, never identity proof.
    if (entry.owner.userId !== owner.userId || entry.pending.profileVersionId !== profileVersionId) continue;
    if (storedKey === key) pending = entry.pending;
    else if (entry.owner.accountScope?.id === owner.accountScope?.id ||
        entry.owner.accountScope === null || owner.accountScope === null) {
      // An old version of this space (or missing scope) must not become a fresh write.
      historical.push({requestId: entry.pending.requestId, profileVersionId, accountScope: entry.owner.accountScope});
    }
  }
  return {pending, historical};
}
export function storeMaterialOperation(owner: MaterialOwner, pending: MaterialPending) {
  const existing = readMaterialOperations(owner, pending.profileVersionId);
  if (existing.pending || existing.historical.length) throw new Error("存在待确认资料操作。");
  const entry = entrySchema.parse({schemaVersion: 2, owner, pending});
  const key = materialOperationKey(owner, pending.profileVersionId);
  const serialized = JSON.stringify(entry);
  localStorage.setItem(key, serialized);
  if (localStorage.getItem(key) !== serialized) throw new Error("资料操作记录未可靠保存。");
}
export function finishMaterialOperation(owner: MaterialOwner, pending: MaterialPending) {
  const key = materialOperationKey(owner, pending.profileVersionId);
  const stored = localStorage.getItem(key);
  if (stored === null) throw new Error("原资料操作记录丢失，请继续核对。");
  const entry = entrySchema.parse(JSON.parse(stored));
  if (materialOperationKey(entry.owner, entry.pending.profileVersionId) !== key ||
      JSON.stringify(entry.pending) !== JSON.stringify(pending))
    throw new Error("资料操作记录已变化，请继续核对。");
  localStorage.removeItem(key);
  if (localStorage.getItem(key) !== null) throw new Error("原资料操作记录未能更新。");
}
