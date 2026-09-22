import type { ManagementService } from "../../src/renderer/services/management";
import { ServiceError } from "../../src/renderer/services/contracts";
import { TEST_USER } from "./fixtures";
import {
  inputDigest,
  type AccountState,
  type ManagementPlan,
} from "../../src/renderer/domain/management";

/** Isolated layout fixtures. No activation, restore, update, export or external IO. */
export const VISUAL_MANAGEMENT_SCOPE = {id: "TEST-visual-space", version: 1};
export function visualManagementAccount(): AccountState & {device: NonNullable<AccountState['device']>} {
  return {
    userId: TEST_USER,
    accountScope: {...VISUAL_MANAGEMENT_SCOPE},
    spaceId: "TEST-visual-space",
    spaceName: "TEST 视觉验收空间",
    revision: "TEST-r1",
    license: { status: "INACTIVE", expiresAt: null },
    device: { id: "TEST-device", name: "TEST 本机设备", status: "UNBOUND" },
  };
}

export function makeVisualManagement(state: string): ManagementService {
  const account = visualManagementAccount();
  const read = async <T>(value: T): Promise<T> => {
    if (state === "loading") return new Promise<T>(() => {});
    if (state === "error")
      throw new ServiceError(
        "VISUAL_TEST_ERROR",
        "TEST 管理服务失败状态（隔离夹具）",
        503,
      );
    return structuredClone(value);
  };
  const unavailable = async (): Promise<never> => {
    throw new ServiceError(
      "CAPABILITY_UNAVAILABLE",
      "TEST 已拦截操作，没有执行真实更改或生成数据文件。",
      501,
    );
  };
  return {
    account: () => read(account),
    updates: () => read({ available: false, download: "NONE" }),
    prepare: async (input, hash): Promise<ManagementPlan> => {
      if (
        input.spaceId !== account.spaceId ||
        hash !== (await inputDigest(input))
      )
        throw new Error("TEST 输入不匹配");
      return read({
        id: "TEST-plan",
        kind: input.kind,
        spaceId: input.spaceId,
        revision: input.revision,
        inputHash: hash,
        expiresAt: new Date(Date.now() + 60_000).toISOString(),
        summary: "TEST 确认预览，仅验证界面。操作被隔离环境拦截。",
        changes: [],
      });
    },
    exportData: unavailable,
    execute: unavailable,
    operation: unavailable,
    cancel: unavailable,
  };
}
