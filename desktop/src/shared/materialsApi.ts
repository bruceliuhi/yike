import { z } from "zod";

const id = z.string().trim().min(1).max(200);
const uuid = z.string().uuid();
const version = z.number().int().positive();
const fields = z.object({
  service: z.string().max(500).optional(),
  customer: z.string().max(500).optional(),
  regions: z.string().max(500).optional(),
  preference: z.string().max(200).optional(),
  exclusions: z.string().max(500).optional(),
}).strict().refine((value) => Object.values(value).some((item) => item?.trim()));
const input = z.object({
  name: z.string().trim().min(1).max(100),
  text: z.string().trim().min(1).max(2000).refine((value) => !value.includes("\0")),
  purpose: z.enum(["产品介绍", "真实案例", "服务说明"]),
  visibility: z.enum(["internal", "external"]),
  fileName: z.string().max(255).optional(),
  bytes: z.number().int().min(0).max(200 * 1024).optional(),
}).strict();
const materialId = { materialId: id };
const change = z.discriminatedUnion("kind", [
  z.object({ kind: z.literal("save"), ...materialId, expectedVersion: version.nullable(), input }).strict(),
  z.object({ kind: z.literal("parse"), ...materialId, expectedVersion: version }).strict(),
  z.object({ kind: z.literal("confirm"), ...materialId, expectedVersion: version, extractionId: id, fields }).strict(),
  z.object({ kind: z.enum(["remove", "revoke"]), ...materialId, expectedVersion: version, impactToken: id }).strict(),
]);

export const materialListRequestSchema = z.object({ profileVersionId: id }).strict();
export const materialMutationRequestSchema = z.object({
  requestId: uuid,
  profileVersionId: id,
  change,
}).strict();
export const materialOperationRequestSchema = z.object({
  profileVersionId: id,
  requestId: uuid,
}).strict();
export const materialImpactRequestSchema = z.object({
  profileVersionId: id,
  materialId: id,
  version,
  action: z.enum(["remove", "revoke"]),
}).strict();
