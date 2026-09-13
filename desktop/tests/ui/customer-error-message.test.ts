import { describe, expect, it } from "vitest";
import { z } from "zod";
import { errorMessage, ServiceError } from "../../src/renderer/services/contracts";

describe("customer error messages", () => {
  it("does not expose schema diagnostics or network engine messages", () => {
    const result = z.object({ internal_field: z.string() }).safeParse({});
    if (result.success) throw new Error("Expected invalid fixture");
    for (const error of [result.error, new TypeError("Failed to fetch"), new Error("SQLITE_BUSY internal_table"), new ServiceError("INTERNAL", "openai-compatible: invalid_request")]) {
      expect(errorMessage(error)).toBe("操作未完成，请查看当前状态后再继续。");
    }
  });
  it("preserves actionable business errors and unknown-result recovery instructions", () => {
    for (const error of [
      new ServiceError("UNKNOWN", "发送结果尚未确认，请先核对原记录，不要重复发送。"),
      new Error("资料回执与查询请求不匹配，请继续核对原操作。"),
    ]) expect(errorMessage(error)).toBe(error.message);
  });
});
