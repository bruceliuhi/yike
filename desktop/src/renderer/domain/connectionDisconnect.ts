import { z } from "zod";
import type { OperationEntries } from "../app/operationLedger";
import type { PlatformConnection } from "./models";

const platform = z.enum(["xhs", "douyin", "bilibili", "zhihu"]);
const binding = z.tuple([
  platform,
  z.string().trim().min(1).max(512),
  z.string().trim().min(1).max(128),
]);
export interface DisconnectRecord {
  key: string;
  platform: z.infer<typeof platform>;
  accountId: string;
  requestId: string;
  acknowledged: boolean;
}
export interface DisconnectTarget {
  platform: DisconnectRecord["platform"];
  accountId: string;
  accountName?: string;
}
export function disconnectKey(target: DisconnectTarget, requestId: string) {
  return JSON.stringify(
    binding.parse([target.platform, target.accountId, requestId]),
  );
}
export function disconnectRecords(
  entries: OperationEntries,
): DisconnectRecord[] {
  return Object.entries(entries).map(([key, status]) => {
    const [platform, accountId, requestId] = binding.parse(JSON.parse(key));
    return {
      key,
      platform,
      accountId,
      requestId,
      acknowledged: status === "ACKNOWLEDGED",
    };
  });
}
const connectionSchema = z.object({
  platform: z.enum(["xhs", "douyin", "bilibili", "zhihu", "web"]),
  status: z.enum([
    "CONNECTED",
    "DISCONNECTED",
    "EXPIRED",
    "LIMITED",
    "UNAVAILABLE",
  ]),
  accountId: z.string().max(512).optional(),
  accountName: z.string().max(512).optional(),
  capabilities: z.array(z.string().max(128)).max(50),
  reason: z.string().max(2000).optional(),
});
export function checkedDisconnectConnection(
  value: unknown,
  target: DisconnectTarget,
): PlatformConnection {
  const connection = connectionSchema.parse(value);
  if (connection.platform !== target.platform)
    throw new Error("返回连接与原平台不匹配，未改变断开记录。");
  return connection;
}
export function disconnectTarget(value: PlatformConnection): DisconnectTarget {
  if (value.status !== "CONNECTED" || !value.accountId?.trim())
    throw new Error("当前账号身份或连接状态不完整，请先检查连接。");
  const [id, accountId] = binding.parse([
    value.platform,
    value.accountId,
    "validation",
  ]);
  return { platform: id, accountId, accountName: value.accountName };
}
