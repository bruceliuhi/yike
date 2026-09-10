import type {
  Material,
  MaterialImpact,
  MaterialReceipt,
  MaterialRequest,
} from "../domain/materials";
import {
  materialImpactRequestSchema,
  materialListRequestSchema,
  materialMutationRequestSchema,
  materialOperationRequestSchema,
} from "../../shared/materialsApi";
import {
  materialImpactSchema,
  materialReceiptSchema,
  parseMaterialReceipt,
  parseMaterials,
} from "../domain/materials";
import type { ApiOperation } from "../../shared/contracts";
import { ServiceError } from "./contracts";

/** Authenticated, versioned adapter. Authority and service URL stay outside the renderer. */
export interface MaterialService {
  list(profileVersionId: string): Promise<Material[]>;
  mutate(
    request: MaterialRequest,
    options: {
      signal: AbortSignal;
      onUploadProgress: (percent: number) => void;
    },
  ): Promise<MaterialReceipt>;
  operation(
    profileVersionId: string,
    requestId: string,
  ): Promise<MaterialReceipt>;
  impact(
    profileVersionId: string,
    materialId: string,
    version: number,
    action: "remove" | "revoke",
  ): Promise<MaterialImpact>;
}

type Transport = (
  operation: ApiOperation,
  path: string,
  method?: string,
  payload?: unknown,
  signal?: AbortSignal,
) => Promise<unknown>;

function checked<T>(schema: { safeParse(value: unknown): { success: boolean; data?: T } }, value: unknown): T {
  const parsed = schema.safeParse(value);
  if (!parsed.success)
    throw new ServiceError("INVALID_REQUEST", "资料请求格式不正确，请检查当前内容。");
  return parsed.data as T;
}

export function createMaterialsService(transport: Transport): MaterialService {
  return {
    async list(profileVersionId) {
      const payload = checked(materialListRequestSchema, { profileVersionId });
      const raw = await transport("materials.list", `/materials?profileVersionId=${encodeURIComponent(profileVersionId)}`, "GET", payload);
      return parseMaterials(raw, profileVersionId);
    },
    async mutate(request, options) {
      const payload = checked(materialMutationRequestSchema, request) as MaterialRequest;
      options.signal.throwIfAborted();
      const raw = await transport("materials.mutate", "/materials/mutate", "POST", payload, options.signal);
      options.signal.throwIfAborted();
      const expected = {
        requestId: payload.requestId,
        profileVersionId: payload.profileVersionId,
        materialId: payload.change.materialId,
        kind: payload.change.kind,
        expectedVersion: payload.change.expectedVersion,
      };
      return parseMaterialReceipt(raw, expected, payload.change);
    },
    async operation(profileVersionId, requestId) {
      const payload = checked(materialOperationRequestSchema, { profileVersionId, requestId });
      const result = materialReceiptSchema.parse(await transport(
        "materials.operation",
        `/materials/operation?profileVersionId=${encodeURIComponent(profileVersionId)}&requestId=${encodeURIComponent(requestId)}`,
        "GET",
        payload,
      ));
      if (result.profileVersionId !== profileVersionId || result.requestId !== requestId)
        throw new Error("资料回执与查询请求不匹配，请继续核对原操作。");
      return result;
    },
    async impact(profileVersionId, materialId, version, action) {
      const payload = checked(materialImpactRequestSchema, { profileVersionId, materialId, version, action });
      const result = materialImpactSchema.parse(await transport("materials.impact", "/materials/impact", "POST", payload));
      if (result.profileVersionId !== profileVersionId || result.materialId !== materialId || result.version !== version || result.action !== action)
        throw new Error("资料影响范围与当前操作不匹配，请重新读取。");
      return result;
    },
  };
}
