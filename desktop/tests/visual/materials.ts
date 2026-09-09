/** TEST-only in-memory adapter for visible P03/P04 verification.
 * Never import from production src; no network, filesystem or real AI parsing.
 */
import {
  extractedFieldsSchema,
  materialInputSchema,
  materialSchema,
  type Material,
  type MaterialImpact,
  type MaterialReceipt,
  type MaterialRequest,
} from "../../src/renderer/domain/materials";
import type { MaterialService } from "../../src/renderer/services/materials";

export const TEST_MATERIAL_PROFILE_ID = "TEST-profile-v1";

export function makeVisualMaterials(): MaterialService {
  const rows = new Map<string, Material>();
  const receipts = new Map<string, { input: string; value: MaterialReceipt }>();
  const impacts = new Map<string, MaterialImpact>();
  const scope = (profileId: string) => {
    if (profileId !== TEST_MATERIAL_PROFILE_ID)
      throw new Error("TEST 资料夹具仅用于 TEST-profile-v1，未操作其他画像。");
  };
  const testText = (value: string) => {
    if (!value.includes("TEST"))
      throw new Error(
        "TEST 隔离验收请使用含 TEST 标记的资料名称、正文和提取内容。",
      );
  };
  const clone = <T>(value: T): T => structuredClone(value);
  return {
    async list(profileId) {
      scope(profileId);
      return clone([...rows.values()]);
    },
    async mutate(request, options) {
      scope(request.profileVersionId);
      if (options.signal.aborted) throw new Error("TEST 请求等待已取消。");
      const input = JSON.stringify(request);
      const previous = receipts.get(request.requestId);
      if (previous) {
        if (previous.input !== input)
          throw new Error("TEST 原请求 ID 的提交内容发生变化，未重复操作。");
        return clone(previous.value);
      }
      const change = request.change;
      const base: MaterialReceipt = {
        requestId: request.requestId,
        profileVersionId: request.profileVersionId,
        materialId: change.materialId,
        kind: change.kind,
        status: "SUCCEEDED",
      };
      let value: MaterialReceipt;
      try {
        const current = rows.get(change.materialId);
        if (
          change.expectedVersion === null
            ? !!current || change.kind !== "save"
            : !current || current.version !== change.expectedVersion
        )
          throw new Error("TEST 资料版本已变化，请刷新后重新核对。");
        const version = (current?.version || 0) + 1;
        let next: Material | undefined;
        if (change.kind === "save") {
          const saved = materialInputSchema.parse(change.input);
          testText(saved.name);
          testText(saved.text);
          next = {
            ...saved,
            id: change.materialId,
            profileVersionId: TEST_MATERIAL_PROFILE_ID,
            version,
            updatedAt: new Date().toISOString(),
            status: "DRAFT",
          };
        } else if (change.kind === "parse") {
          if (!["DRAFT", "FAILED", "REVOKED"].includes(current!.status))
            throw new Error("TEST 当前资料状态不能重复提取。");
          // Deterministic excerpt, explicitly a fixture, never an AI result.
          const excerpt = current!.text.slice(0, 500);
          next = {
            ...current!,
            version,
            updatedAt: new Date().toISOString(),
            status: "REVIEW_REQUIRED",
            extraction: {
              id: "TEST-extraction-" + crypto.randomUUID(),
              materialVersion: version,
              fields: { service: excerpt },
              evidence: [{ field: "service", quote: excerpt }],
            },
          };
        } else if (change.kind === "confirm") {
          const extraction = current!.extraction;
          if (
            current!.status !== "REVIEW_REQUIRED" ||
            !extraction ||
            extraction.id !== change.extractionId
          )
            throw new Error("TEST 提取版本已变化，未确认其他结果。");
          const fields = extractedFieldsSchema.parse(change.fields);
          if (
            Object.keys(fields).some(
              (key) => !Object.hasOwn(extraction.fields, key),
            )
          )
            throw new Error("TEST 提取字段没有对应原文证据。");
          Object.values(fields).forEach((text) => {
            if (text) testText(text);
          });
          next = {
            ...current!,
            version,
            updatedAt: new Date().toISOString(),
            status: "READY",
            extraction: { ...extraction, materialVersion: version, fields },
          };
        } else {
          const impact = impacts.get(change.impactToken);
          if (
            !impact ||
            impact.materialId !== current!.id ||
            impact.version !== current!.version ||
            impact.action !== change.kind ||
            Date.parse(impact.expiresAt) <= Date.now()
          )
            throw new Error("TEST 引用影响已变化或过期，请重新核对。");
          if (change.kind === "revoke") {
            next = {
              ...current!,
              version,
              updatedAt: new Date().toISOString(),
              status: "REVOKED",
              extraction: undefined,
            };
          }
        }
        if (next) next = materialSchema.parse(next);
        // All validation precedes mutation; confirmed failures leave the map intact.
        if (change.kind === "remove") rows.delete(change.materialId);
        else rows.set(change.materialId, next!);
        if (change.kind === "remove" || change.kind === "revoke")
          impacts.delete(change.impactToken);
        value = { ...base, ...(next ? { record: next } : {}) };
      } catch (error) {
        value = {
          ...base,
          status: "FAILED",
          confirmedNoChange: true,
          message: error instanceof Error ? error.message : "TEST 操作未执行。",
        };
      }
      receipts.set(request.requestId, { input, value: clone(value) });
      return clone(value);
    },
    async operation(profileId, requestId) {
      scope(profileId);
      const receipt = receipts.get(requestId);
      if (!receipt)
        throw new Error("TEST 内存中没有该原请求；未伪造成功回执。");
      return clone(receipt.value);
    },
    async impact(profileId, materialId, version, action) {
      scope(profileId);
      const row = rows.get(materialId);
      if (!row || row.version !== version)
        throw new Error("TEST 资料不存在或版本已变化。");
      if (action === "revoke" && row.status !== "READY")
        throw new Error("TEST 仅已确认资料可撤销引用。");
      const result: MaterialImpact = {
        profileVersionId: TEST_MATERIAL_PROFILE_ID,
        materialId,
        version,
        action,
        token: "TEST-impact-" + crypto.randomUUID(),
        expiresAt: new Date(Date.now() + 60_000).toISOString(),
        // This adapter creates no persistent profile/draft references.
        references: [],
      };
      impacts.set(result.token, clone(result));
      return result;
    },
  };
}
