import {
  digest,
  inputDigest,
  operationKindSchema,
  planSchema,
  readBackup,
  receiptSchema,
  type CustomerBackup,
  type ManagementInput,
  type ManagementPlan,
  type ManagementReceipt,
  type UpdateState,
} from "../../src/renderer/domain/management";
import {
  ServiceError,
  type YikeService,
} from "../../src/renderer/services/contracts";
import type {
  ExportRequest,
  SaveExportResult,
} from "../../src/shared/contracts";
import { validatedExport } from "../../src/shared/exportValidation";
import { TEST_USER } from "./fixtures";
import { visualManagementAccount } from "./management";

export type ManagementSaveMode = "saved" | "cancelled" | "error";
export type ManagementResultMode = "UNKNOWN" | "SUCCEEDED" | "FAILED";
export type ManagementCancelMode = "PENDING" | "CANCELLED";
export interface ManagementRecoverySnapshot {
  saveMode: ManagementSaveMode;
  executeMode: ManagementResultMode;
  queryMode: ManagementResultMode;
  cancelMode: ManagementCancelMode;
  requestId: string;
  kind: string;
  phase: "READY" | ManagementReceipt["status"];
  lastSave: string;
}
export interface ManagementRecoveryController {
  subscribe(listener: () => void): () => void;
  snapshot(): ManagementRecoverySnapshot;
  setSaveMode(mode: ManagementSaveMode): void;
  setExecuteMode(mode: ManagementResultMode): void;
  setQueryMode(mode: ManagementResultMode): void;
  setCancelMode(mode: ManagementCancelMode): void;
  saveExport(input: ExportRequest): Promise<SaveExportResult>;
}

/** A separate, finite opt-in. Existing populated/error/loading layouts stay unchanged. */
export function selectManagementRecovery(
  value: string | null,
  page: string,
  state: string,
  guest: boolean,
) {
  if (!value) return false;
  if (value !== "lifecycle" || page !== "P18" || state !== "populated" || guest)
    throw new Error(
      "TEST 管理恢复仅支持 management=lifecycle、P18、populated 和 TEST 登录身份。",
    );
  return true;
}

/** TEST-only authoritative memory. Does not read/write disk, fetch, bind devices or install software. */
export function configureManagementRecovery(harness: {
  service: YikeService;
  record(operation: string, detail?: string): void;
}): ManagementRecoveryController {
  const { service, record } = harness;
  let account = visualManagementAccount();
  let revision = 1;
  let updates: UpdateState = {
    available: true,
    version: "0.2.1-TEST",
    download: "NONE",
    rollbackVersion: "0.2.0-TEST",
    notes: "TEST 内存更新状态，没有下载地址或真实安装程序。",
  };
  let data: CustomerBackup["data"] = {
    profiles: [{ id: "TEST-backup-profile", name: "TEST 内存资料" }],
    tasks: [],
    opportunities: [],
    followups: [],
  };
  const plans = new Map<
    string,
    { input: ManagementInput; plan: ManagementPlan; backup?: CustomerBackup }
  >();
  const operations = new Map<
    string,
    { planId: string; receipt: ManagementReceipt }
  >();
  const exports = new Map<string, number>();
  const listeners = new Set<() => void>();
  let snapshot: ManagementRecoverySnapshot = {
    saveMode: "cancelled",
    executeMode: "UNKNOWN",
    queryMode: "UNKNOWN",
    cancelMode: "PENDING",
    requestId: "",
    kind: "",
    phase: "READY",
    lastSave: "尚未模拟保存",
  };
  const clone = <T>(value: T): T => structuredClone(value);
  const change = (value: Partial<ManagementRecoverySnapshot>) => {
    snapshot = { ...snapshot, ...value };
    listeners.forEach((listener) => listener());
  };
  const reject = (message: string): never => {
    throw new ServiceError("VISUAL_SCOPE_REJECTED", "TEST " + message, 400);
  };
  const requireUser = async () => {
    const current = await service.session();
    if (!current.authenticated || current.userId !== TEST_USER)
      throw new ServiceError(
        "UNAUTHORIZED",
        "TEST 管理恢复仅接受本实例测试身份",
        401,
      );
  };
  const terminal = (receipt: ManagementReceipt) =>
    ["SUCCEEDED", "FAILED", "CANCELLED"].includes(receipt.status);
  const checkedBackup = (content: string) => {
    const backup = readBackup(content);
    if (backup.spaceId !== account.spaceId) reject("备份不属于本测试空间");
    for (const rows of Object.values(backup.data))
      if (
        rows.some(
          (row) => typeof row.id !== "string" || !row.id.startsWith("TEST-"),
        )
      )
        reject("仅接受 ID 以 TEST- 开头的合成备份记录");
    return backup;
  };
  const apply = (planId: string) => {
    const entry = plans.get(planId)!;
    const { kind } = entry.input;
    if (kind === "restore") data = clone(entry.backup!.data);
    if (kind === "bind-device") account.device.status = "BOUND";
    if (kind === "unbind-device") account.device.status = "REVOKED";
    if (kind === "download-update") updates = { ...updates, download: "READY" };
    if (kind === "install-update" || kind === "rollback")
      updates = { ...updates, available: false, download: "NONE" };
    account = { ...account, revision: `TEST-r${++revision}` };
  };
  const settle = (requestId: string, status: ManagementReceipt["status"]) => {
    const operation = operations.get(requestId);
    if (!operation) return reject("本实例没有此原请求，不伪造终态");
    if (terminal(operation.receipt)) return clone(operation.receipt);
    if (status === "SUCCEEDED") apply(operation.planId);
    if (operation.receipt.kind === "download-update" && status === "FAILED")
      updates = { ...updates, download: "FAILED" };
    if (operation.receipt.kind === "download-update" && status === "CANCELLED")
      updates = { ...updates, download: "NONE" };
    operation.receipt = receiptSchema.parse({
      ...operation.receipt,
      status,
      message:
        status === "FAILED"
          ? "TEST 原请求已确认未执行；没有客户数据变更。"
          : status === "CANCELLED"
            ? "TEST 原下载请求已确认取消；没有下载文件。"
            : status === "SUCCEEDED"
              ? "TEST 仅更新本实例内存；没有真实恢复、绑定或安装。"
              : "TEST 原请求结果仍待确认；没有真实执行器。",
    });
    change({ requestId, kind: operation.receipt.kind, phase: status });
    return clone(operation.receipt);
  };
  service.management = {
    account: async () => {
      await requireUser();
      return clone(account);
    },
    updates: async () => {
      await requireUser();
      return clone(updates);
    },
    exportData: async (kind) => {
      await requireUser();
      if (kind !== "csv" && kind !== "backup-json")
        return reject("导出格式不支持");
      const content =
        kind === "csv"
          ? "id,name\nTEST-backup-profile,TEST 内存导出\n"
          : JSON.stringify({
              product: "yike-ai",
              schemaVersion: 1,
              spaceId: account.spaceId,
              createdAt: new Date().toISOString(),
              data,
            });
      const result = {
        spaceId: account.spaceId,
        name: "TEST-memory-export",
        content,
      };
      const normalized = validatedExport({
        format: kind,
        name: result.name,
        content,
      })!;
      exports.set(JSON.stringify(normalized), revision);
      record("management.TEST.export", `${kind} 仅在内存生成；无真实下载`);
      return result;
    },
    prepare: async (value, hash, content) => {
      const input = clone(value);
      await requireUser();
      if (
        !operationKindSchema.safeParse(input.kind).success ||
        input.spaceId !== account.spaceId ||
        input.revision !== account.revision ||
        input.deviceId !== account.device.id ||
        hash !== (await inputDigest(input))
      )
        return reject("计划身份、版本或输入摘要不匹配");
      if ([...operations.values()].some((value) => !terminal(value.receipt)))
        return reject("仍有原请求待确认，不能另建执行计划");
      const updateKind = [
        "download-update",
        "install-update",
        "rollback",
      ].includes(input.kind);
      const target =
        input.kind === "rollback" ? updates.rollbackVersion : updates.version;
      if (updateKind && (!target || input.targetVersion !== target))
        return reject("更新目标版本不匹配");
      if (!updateKind && input.targetVersion !== undefined)
        return reject("此操作不接受更新版本");
      if (input.kind === "install-update" && updates.download !== "READY")
        return reject("TEST 安装文件尚未就绪");
      let backup: CustomerBackup | undefined;
      if (input.kind === "restore") {
        if (!content || input.fileHash !== (await digest(content)))
          return reject("备份全文与摘要不一致");
        backup = checkedBackup(content);
      } else if (content !== undefined || input.fileHash !== undefined)
        return reject("此操作不接受备份正文");
      const plan = planSchema.parse({
        id: "TEST-plan-" + crypto.randomUUID(),
        kind: input.kind,
        spaceId: input.spaceId,
        revision: input.revision,
        inputHash: hash,
        expiresAt: new Date(Date.now() + 60_000).toISOString(),
        summary: "TEST 影响预览，仅修改隔离内存，不会恢复客户数据或安装软件。",
        changes: backup
          ? Object.entries(backup.data).map(([label, rows]) => ({
              label: "TEST " + label,
              added: rows.length,
              updated: 0,
              removed: data[label as keyof typeof data].length,
            }))
          : [],
      });
      await requireUser();
      plans.set(plan.id, {
        input: clone(input),
        plan,
        backup: backup && clone(backup),
      });
      record("management.TEST.prepare", `${input.kind} / ${plan.id}`);
      return clone(plan);
    },
    execute: async (planId, requestId) => {
      await requireUser();
      if (!requestId.trim() || requestId.length > 128)
        return reject("原请求 ID 无效");
      const previous = operations.get(requestId);
      if (previous) {
        if (previous.planId !== planId)
          return reject("同一原请求不能改为另一个计划");
        return clone(previous.receipt);
      }
      const entry = plans.get(planId);
      if (
        !entry ||
        Date.parse(entry.plan.expiresAt) <= Date.now() ||
        entry.input.revision !== account.revision
      )
        return reject("执行计划不存在、过期或账户版本已变化");
      if ([...operations.values()].some((value) => !terminal(value.receipt)))
        return reject("原请求未确认，不得另发一次执行");
      operations.set(requestId, {
        planId,
        receipt: {
          requestId,
          kind: entry.input.kind,
          spaceId: account.spaceId,
          status: "UNKNOWN",
        },
      });
      record(
        "management.TEST.execute",
        `${entry.input.kind} / ${requestId} / 仅内存`,
      );
      return settle(requestId, snapshot.executeMode);
    },
    operation: async (requestId) => {
      await requireUser();
      record("management.TEST.query", requestId);
      return settle(requestId, snapshot.queryMode);
    },
    cancel: async (requestId) => {
      await requireUser();
      const original = operations.get(requestId);
      if (!original || original.receipt.kind !== "download-update")
        return reject("仅能取消本实例原下载请求");
      record("management.TEST.cancel", `${requestId} / ${snapshot.cancelMode}`);
      return settle(requestId, snapshot.cancelMode);
    },
  };
  return {
    subscribe: (listener) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    snapshot: () => snapshot,
    setSaveMode: (mode) => {
      if (!["saved", "cancelled", "error"].includes(mode))
        reject("保存模式无效");
      change({ saveMode: mode });
    },
    setExecuteMode: (mode) => {
      if (!["UNKNOWN", "SUCCEEDED", "FAILED"].includes(mode))
        reject("执行模式无效");
      change({ executeMode: mode });
    },
    setQueryMode: (mode) => {
      if (!["UNKNOWN", "SUCCEEDED", "FAILED"].includes(mode))
        reject("查询模式无效");
      change({ queryMode: mode });
    },
    setCancelMode: (mode) => {
      if (!["PENDING", "CANCELLED"].includes(mode)) reject("取消模式无效");
      change({ cancelMode: mode });
    },
    saveExport: async (input) => {
      await requireUser();
      const request = validatedExport(input);
      if (!request || exports.get(JSON.stringify(request)) !== revision)
        return { status: "error", error: "INVALID_EXPORT_REQUEST" };
      record(
        "management.TEST.save",
        `${snapshot.saveMode} / ${request.format} / 未写文件`,
      );
      change({
        lastSave:
          snapshot.saveMode === "saved"
            ? "TEST 模拟保存完成，未创建文件"
            : snapshot.saveMode === "cancelled"
              ? "TEST 模拟取消保存，未创建文件"
              : "TEST 模拟保存失败，未创建文件",
      });
      return snapshot.saveMode === "error"
        ? { status: "error", error: "EXPORT_FAILED" }
        : { status: snapshot.saveMode };
    },
  };
}
