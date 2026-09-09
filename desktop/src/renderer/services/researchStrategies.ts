import type { z } from "zod";
import type { ApiOperation } from "../../shared/contracts";
import {
  prepareStrategySchema, confirmStrategySchema, revokeStrategySchema, strategyUuidSchema,
  type PrepareStrategyRequest, type ConfirmStrategyRequest, type RevokeStrategyRequest,
} from "../../shared/researchStrategies";
import { ServiceError } from "./contracts";

/** Responses remain untrusted until checked against the original operation. */
export interface ResearchStrategiesService {
  prepare(request: PrepareStrategyRequest): Promise<unknown>;
  confirm(request: ConfirmStrategyRequest): Promise<unknown>;
  revoke(request: RevokeStrategyRequest): Promise<unknown>;
  getReceipt(requestId: string): Promise<unknown>;
  getStrategy(strategyVersionId: string): Promise<unknown>;
}
type Transport = (operation: ApiOperation, path: string, method: string, payload: unknown) => Promise<unknown>;

function validate<T>(schema: z.ZodType<T>, input: unknown): T {
  const result = schema.safeParse(input);
  if (!result.success || new TextEncoder().encode(JSON.stringify(result.data)).byteLength > 128 * 1024)
    throw new ServiceError("INVALID_REQUEST", "策略请求不完整或已变化，请重新核对配置。", 422);
  return result.data;
}

/** One explicit request only; receipt reconciliation belongs to the caller. */
export function createResearchStrategiesService(request: Transport): ResearchStrategiesService {
  return {
    async prepare(input) {
      return request("strategies.prepare", "/research-strategies/prepare", "POST", validate(prepareStrategySchema, input));
    },
    async confirm(input) {
      return request("strategies.confirm", "/research-strategies/confirm", "POST", validate(confirmStrategySchema, input));
    },
    async revoke(input) {
      return request("strategies.revoke", "/research-strategies/revoke", "POST", validate(revokeStrategySchema, input));
    },
    async getReceipt(input) {
      const key = validate(strategyUuidSchema, input);
      return request("strategies.receipt", `/research-strategy-operations/${key}`, "GET", { request_id: key });
    },
    async getStrategy(input) {
      const key = validate(strategyUuidSchema, input);
      return request("strategies.get", `/research-strategies/${key}`, "GET", { strategy_version_id: key });
    },
  };
}
