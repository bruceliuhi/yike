import { decodeConnectionRegistry } from "../../src/renderer/services/connectionRegistry";
import type { YikeService } from "../../src/renderer/services/contracts";

/** Isolated UI coverage only: these are not real platform accounts or credentials. */
export function configureRegistryVisual(service: YikeService, record: (name: string) => void) {
  service.connections = async () => {
    record("connections.TEST-registry");
    return decodeConnectionRegistry({items: [
      {platform: "XIAOHONGSHU", status: "UNVERIFIED", account_public_id: "TEST-账号A", device_id: "TEST-device-one"},
      {platform: "XIAOHONGSHU", status: "CONNECTED", account_public_id: "TEST-账号A", device_id: "TEST-device-two"},
      {platform: "DOUYIN", status: "EXPIRED", account_public_id: "TEST-账号B", device_id: "TEST-device-one"},
    ].map((row, index) => ({...row, connection_id: `TEST-connection-${index + 1}`,
      connection_version: index + 1, connected_at: "2026-09-09T08:00:00+08:00", disconnected_at: null,
    }))});
  };
}
