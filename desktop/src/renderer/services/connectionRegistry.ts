import { z } from "zod";
import { ServiceError } from "./contracts";
import type { PlatformConnection, PlatformId } from "../domain/models";

const id = z.string().min(1).max(256).refine(value => value.trim() === value && !/[\u0000-\u001f\u007f]/.test(value));
const timestamp = z.string().datetime({offset: true});
const platforms = {
  XIAOHONGSHU: "xhs", DOUYIN: "douyin", BILIBILI: "bilibili", ZHIHU: "zhihu", PUBLIC_WEB: "web",
} as const satisfies Record<string, PlatformId>;
const response = z.object({items: z.array(z.object({
  connection_id: id, device_id: id, account_public_id: id,
  platform: z.enum(["XIAOHONGSHU", "DOUYIN", "BILIBILI", "ZHIHU", "PUBLIC_WEB"]),
  status: z.enum(["UNVERIFIED", "CONNECTED", "DISCONNECTED", "EXPIRED"]),
  connection_version: z.number().int().min(1).max(2_147_483_647),
  connected_at: timestamp, disconnected_at: timestamp.nullable(),
})).max(10_000)});

/** GET /connections is a registration read model, not a platform capability check. */
export function decodeConnectionRegistry(value: unknown): PlatformConnection[] {
  const parsed = response.safeParse(value);
  if (!parsed.success || new Set(parsed.data.items.map(row => row.connection_id)).size !== parsed.data.items.length)
    throw new ServiceError("INVALID_SERVICE_RESPONSE", "连接列表响应不完整，请重新读取；未将其视为没有账号。");
  return parsed.data.items.map(row => ({
    platform: platforms[row.platform], status: row.status, accountId: row.account_public_id,
    capabilities: [],
    reason: "连接记录已读取，平台执行能力仍需单独核验。",
    registration: {
      connectionId: row.connection_id, deviceId: row.device_id, version: row.connection_version,
      connectedAt: row.connected_at, disconnectedAt: row.disconnected_at,
    },
  }));
}

/** Legacy platform checks must never replace registered accounts on other devices. */
export function mergeConnectionRead(
  rows: PlatformConnection[] | undefined, incoming: PlatformConnection,
): PlatformConnection[] {
  const list = rows || [];
  if (incoming.registration) return [
    ...list.filter(row => row.registration?.connectionId !== incoming.registration!.connectionId), incoming,
  ];
  return [
    ...list.filter(row => row.registration || row.platform !== incoming.platform || (
      incoming.accountId && row.accountId && row.accountId !== incoming.accountId
    )), incoming,
  ];
}
