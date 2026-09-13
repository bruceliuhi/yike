import { z } from "zod";

const identifier = z.string().min(1).max(200);
const moment = z.string().datetime({ offset: true });
export const operationKinds = [
  "bind-device",
  "unbind-device",
  "restore",
  "download-update",
  "install-update",
  "rollback",
] as const;
export const operationKindSchema = z.enum(operationKinds);
export type ManagementOperationKind = z.infer<typeof operationKindSchema>;
export const accountSchema = z.object({
  spaceId: identifier,
  spaceName: identifier,
  revision: identifier,
  license: z.object({
    status: z.enum(["UNKNOWN", "INACTIVE", "ACTIVE", "EXPIRED", "SUSPENDED"]),
    expiresAt: moment.nullable(),
  }),
  device: z.object({
    id: identifier,
    name: identifier,
    status: z.enum(["UNBOUND", "BOUND", "REVOKED", "OFFLINE"]),
  }),
});
export type AccountState = z.infer<typeof accountSchema>;
export const updateSchema = z
  .object({
    available: z.boolean(),
    version: identifier.optional(),
    notes: z.string().max(4000).optional(),
    download: z.enum(["NONE", "DOWNLOADING", "READY", "FAILED"]),
    progress: z.number().min(0).max(100).optional(),
    rollbackVersion: identifier.optional(),
  })
  .refine((value) => !value.available || !!value.version, "更新版本缺失");
export type UpdateState = z.infer<typeof updateSchema>;
export interface ManagementInput {
  kind: ManagementOperationKind;
  spaceId: string;
  revision: string;
  deviceId: string;
  targetVersion?: string;
  fileHash?: string;
}
export const planSchema = z.object({
  id: identifier,
  kind: operationKindSchema,
  spaceId: identifier,
  revision: identifier,
  inputHash: z.string().regex(/^[a-f0-9]{64}$/),
  expiresAt: moment,
  summary: z.string().min(1).max(2000),
  changes: z
    .array(
      z.object({
        label: identifier,
        added: z.number().int().nonnegative(),
        updated: z.number().int().nonnegative(),
        removed: z.number().int().nonnegative(),
      }),
    )
    .max(20),
});
export type ManagementPlan = z.infer<typeof planSchema>;
export const receiptSchema = z.object({
  requestId: identifier,
  kind: operationKindSchema,
  spaceId: identifier,
  status: z.enum(["PENDING", "UNKNOWN", "SUCCEEDED", "FAILED", "CANCELLED"]),
  message: z.string().max(1000).optional(),
});
export type ManagementReceipt = z.infer<typeof receiptSchema>;
export const backupSchema = z
  .object({
    product: z.literal("yike-ai"),
    schemaVersion: z.literal(1),
    spaceId: identifier,
    createdAt: moment,
    data: z
      .object({
        profiles: z.array(z.record(z.string(), z.unknown())),
        tasks: z.array(z.record(z.string(), z.unknown())),
        opportunities: z.array(z.record(z.string(), z.unknown())),
        followups: z.array(z.record(z.string(), z.unknown())),
      })
      .strict(),
  })
  .strict();
export type CustomerBackup = z.infer<typeof backupSchema>;

export function readBackup(content: string): CustomerBackup {
  if (
    new TextEncoder().encode(content).length > 2 * 1024 * 1024 ||
    content.includes("\0")
  )
    throw new Error("备份文件过大或包含无效字符，最大支持 2 MB。");
  let parsed: unknown;
  try {
    parsed = JSON.parse(content);
  } catch {
    throw new Error("无法读取此备份，请重新选择意客AI导出的备份文件。");
  }
  const result = backupSchema.safeParse(parsed);
  if (!result.success)
    throw new Error("备份格式或版本不受支持，请选择意客AI客户数据备份。");
  // Defense in depth only: the service must export an explicit business-field
  // allowlist. Prefixes used by platform/environment credential fields count too.
  const forbidden =
    /(?:password|passwd|cookie|token|authorization|secret|apikey|databaseurl|session|credential|privatekey)/i;
  const visit = (value: unknown, depth = 0) => {
    if (depth > 20) throw new Error("备份数据层级过深。");
    if (value && typeof value === "object")
      for (const [key, item] of Object.entries(value)) {
        if (
          forbidden.test(key.replace(/[_\-\s]/g, "")) ||
          ["__proto__", "prototype", "constructor"].includes(key)
        )
          throw new Error("备份包含不允许恢复的凭据或配置字段。");
        visit(item, depth + 1);
      }
  };
  visit(result.data);
  return result.data;
}
export async function digest(value: string): Promise<string> {
  return [
    ...new Uint8Array(
      await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value)),
    ),
  ]
    .map((n) => n.toString(16).padStart(2, "0"))
    .join("");
}
export function inputDigest(input: ManagementInput) {
  return digest(
    JSON.stringify([
      input.kind,
      input.spaceId,
      input.revision,
      input.deviceId,
      input.targetVersion ?? null,
      input.fileHash ?? null,
    ]),
  );
}
