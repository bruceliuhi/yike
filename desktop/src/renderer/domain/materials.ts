import { z } from "zod";
import type { ProfileFields } from "./models";

export const MATERIAL_LIMIT_BYTES = 200 * 1024;
export const materialFieldLabels: Record<keyof ProfileFields, string> = {
  service: "服务内容",
  customer: "目标客户",
  regions: "服务地区",
  preference: "项目偏好",
  exclusions: "排除项",
};
export const materialFields = [
  "service",
  "customer",
  "regions",
  "preference",
  "exclusions",
] as const;
const id = z.string().trim().min(1).max(200);
const version = z.number().int().positive();
const time = z.string().datetime({ offset: true });
export const extractedFieldsSchema = z
  .object({
    service: z.string().max(500).optional(),
    customer: z.string().max(500).optional(),
    regions: z.string().max(500).optional(),
    preference: z.string().max(200).optional(),
    exclusions: z.string().max(500).optional(),
  })
  .strict()
  .refine(
    (value) => Object.values(value).some((item) => item?.trim()),
    "没有可确认的提取内容",
  );
export const materialInputSchema = z
  .object({
    name: z.string().trim().min(1).max(100),
    text: z
      .string()
      .trim()
      .min(1)
      .max(2000)
      .refine((v) => !v.includes("\0")),
    purpose: z.enum(["产品介绍", "真实案例", "服务说明"]),
    visibility: z.enum(["internal", "external"]),
    fileName: z.string().max(255).optional(),
    bytes: z.number().int().min(0).max(MATERIAL_LIMIT_BYTES).optional(),
  })
  .strict();
export type MaterialInput = z.infer<typeof materialInputSchema>;
export const materialSchema = materialInputSchema
  .extend({
    id,
    profileVersionId: id,
    version,
    updatedAt: time,
    status: z.enum([
      "DRAFT",
      "PARSING",
      "REVIEW_REQUIRED",
      "READY",
      "FAILED",
      "REVOKED",
    ]),
    failure: z.string().max(1000).optional(),
    extraction: z
      .object({
        id,
        materialVersion: version,
        fields: extractedFieldsSchema,
        evidence: z
          .array(
            z.object({
              field: z.enum(materialFields),
              quote: z.string().trim().min(1).max(2000),
            }),
          )
          .min(1)
          .max(20),
      })
      .optional(),
  })
  .superRefine((record, ctx) => {
    if (
      (record.status === "REVIEW_REQUIRED" || record.status === "READY") &&
      !record.extraction
    )
      ctx.addIssue({ code: "custom", message: "资料缺少提取证据" });
    if (
      record.extraction &&
      (record.extraction.materialVersion !== record.version ||
        record.extraction.evidence.some(
          (e) => !record.text.includes(e.quote),
        ) ||
        Object.keys(record.extraction.fields).some(
          (field) =>
            !record.extraction!.evidence.some((e) => e.field === field),
        ))
    )
      ctx.addIssue({
        code: "custom",
        message: "提取证据与资料版本或原文不匹配",
      });
  });
export type Material = z.infer<typeof materialSchema>;
export const materialStatus: Record<Material["status"], string> = {
  DRAFT: "已同步草稿",
  PARSING: "解析中",
  REVIEW_REQUIRED: "提取待确认",
  READY: "已确认",
  FAILED: "解析失败",
  REVOKED: "引用已撤销",
};
export function parseMaterials(
  value: unknown,
  profileVersionId: string,
): Material[] {
  const rows = z.array(materialSchema).max(500).parse(value);
  if (
    new Set(rows.map((row) => row.id)).size !== rows.length ||
    rows.some((row) => row.profileVersionId !== profileVersionId)
  )
    throw new Error("资料列表与当前画像不匹配，请刷新重试。");
  return rows;
}
export type MaterialChange =
  | {
      kind: "save";
      materialId: string;
      expectedVersion: number | null;
      input: MaterialInput;
    }
  | { kind: "parse"; materialId: string; expectedVersion: number }
  | {
      kind: "confirm";
      materialId: string;
      expectedVersion: number;
      extractionId: string;
      fields: Partial<ProfileFields>;
    }
  | {
      kind: "remove" | "revoke";
      materialId: string;
      expectedVersion: number;
      impactToken: string;
    };
export const materialPendingSchema = z
  .object({
    requestId: z.string().uuid(),
    profileVersionId: id,
    materialId: id,
    kind: z.enum(["save", "parse", "confirm", "remove", "revoke"]),
    expectedVersion: version.nullable(),
  })
  .strict()
  .refine(
    (value) => value.kind === "save" || value.expectedVersion !== null,
    "资料操作缺少版本",
  );
export type MaterialPending = z.infer<typeof materialPendingSchema>;
export type MaterialRequest = {
  requestId: string;
  profileVersionId: string;
  change: MaterialChange;
};
export const materialReceiptSchema = z.object({
  requestId: z.string().uuid(),
  profileVersionId: id,
  materialId: id,
  kind: z.enum(["save", "parse", "confirm", "remove", "revoke"]),
  status: z.enum(["SUCCEEDED", "FAILED", "PENDING", "UNKNOWN"]),
  record: materialSchema.optional(),
  confirmedNoChange: z.literal(true).optional(),
  message: z.string().max(1000).optional(),
});
export type MaterialReceipt = z.infer<typeof materialReceiptSchema>;
export function parseMaterialReceipt(
  value: unknown,
  expected: MaterialPending,
  change?: MaterialChange,
) {
  const receipt = materialReceiptSchema.parse(value);
  for (const key of [
    "requestId",
    "profileVersionId",
    "materialId",
    "kind",
  ] as const)
    if (receipt[key] !== expected[key])
      throw new Error("资料回执与原请求不匹配，请继续核对原操作。");
  if (receipt.status === "FAILED" && !receipt.confirmedNoChange)
    throw new Error("资料操作结果仍未确定，请继续核对原操作。");
  if (receipt.status === "SUCCEEDED" && expected.kind !== "remove") {
    const record = receipt.record;
    if (
      !record ||
      record.id !== expected.materialId ||
      record.profileVersionId !== expected.profileVersionId ||
      record.version <= (expected.expectedVersion ?? 0) ||
      (expected.kind === "confirm" && record.status !== "READY") ||
      (expected.kind === "revoke" && record.status !== "REVOKED") ||
      (expected.kind === "parse" &&
        !["PARSING", "REVIEW_REQUIRED", "FAILED"].includes(record.status)) ||
      (expected.kind === "save" && record.status !== "DRAFT")
    )
      throw new Error("资料版本或状态回执不完整，请继续核对原操作。");
    if (
      change?.kind === "save" &&
      (
        ["name", "text", "purpose", "visibility", "fileName", "bytes"] as const
      ).some((key) => record[key] !== change.input[key])
    )
      throw new Error(
        "保存回执与提交的资料内容不一致，输入和原操作保护仍保留。",
      );
    if (
      change?.kind === "confirm" &&
      (record.extraction?.id !== change.extractionId ||
        materialFields.some(
          (key) => record.extraction?.fields[key] !== change.fields[key],
        ))
    )
      throw new Error("提取回执与人工确认内容不一致，输入和原操作保护仍保留。");
  }
  return receipt;
}
export const materialImpactSchema = z.object({
  profileVersionId: id,
  materialId: id,
  version,
  action: z.enum(["remove", "revoke"]),
  token: id,
  expiresAt: time,
  references: z
    .array(z.object({ kind: z.enum(["profile", "draft"]), label: id }))
    .max(100),
});
export type MaterialImpact = z.infer<typeof materialImpactSchema>;
