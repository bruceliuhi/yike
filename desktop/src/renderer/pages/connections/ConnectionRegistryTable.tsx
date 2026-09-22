import { useState } from "react";
import { PlatformLabel } from "../../components/Platform";
import { Badge, Button, Modal, Notice, formatDate } from "../../components/ui";
import { PLATFORMS, type PlatformConnection } from "../../domain/models";

export const connectionLabel: Record<PlatformConnection["status"], string> = {
  CONNECTED: "已连接", DISCONNECTED: "未连接", EXPIRED: "登录已失效",
  LIMITED: "连接受限", UNAVAILABLE: "连接服务待接通", UNVERIFIED: "待核验",
};

export const connectionAccountLabel = (connection: PlatformConnection, index: number) => connection.accountName?.trim() || `${PLATFORMS.find(platform => platform.id === connection.platform)?.name || "平台"}账号${index + 1}`;

/** Show every registration. A platform name alone cannot identify an account or device. */
export function ConnectionRegistryTable({rows, loading, error, pendingPlatforms, onOpen, onDisconnect, onRefresh}: {
  rows: PlatformConnection[] | undefined;
  loading: boolean;
  error: string;
  pendingPlatforms: string[];
  onOpen: (platform: string) => void;
  onDisconnect: (connection: PlatformConnection) => void;
  onRefresh: () => void;
}) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected = rows?.find(row => row.registration?.connectionId === selectedId);
  return <>
    <div className="table-scroll">
      <table className="connection-table">
        <thead><tr><th>平台</th><th>当前账号</th><th>连接状态</th><th>操作</th></tr></thead>
        <tbody>{PLATFORMS.flatMap(platform => {
          const matches = rows?.filter(row => row.platform === platform.id) || [];
          const entries: (PlatformConnection | undefined)[] = matches.length ? matches : [undefined];
          return entries.map((connection, index) => {
            const registered = connection?.registration;
            const isWeb = platform.id === "web";
            const blocked = pendingPlatforms.includes(platform.id);
            // An unavailable registration is a known service state, not an
            // invitation to start another login flow. Keep the row visible
            // so the user can see why it is unavailable, but prevent a dead
            // button from opening a flow that cannot succeed.
            const unavailable = connection?.status === "UNAVAILABLE";
            const accountName = connection ? connectionAccountLabel(connection, index) : isWeb ? "无需账号" : "—";
            return <tr key={registered?.connectionId || `${platform.id}:${connection?.accountId || "empty"}:${index}`}>
              <td><PlatformLabel platform={platform.id} size={22} /></td>
              <td className="connection-account">
                <span>{accountName}</span>
              </td>
              <td>{isWeb && !connection ? "—" : <Badge tone={connection?.status === "CONNECTED" ? "green" : ["EXPIRED", "LIMITED", "UNVERIFIED"].includes(connection?.status || "") ? "orange" : "neutral"}>
                {connection ? connectionLabel[connection.status] : rows ? "未连接" : "待读取连接状态"}
              </Badge>}</td>
              <td>{registered ? <Button onClick={() => setSelectedId(registered.connectionId)} aria-label={`查看${platform.name}连接详情：${accountName}，连接 ${index + 1}`}>查看详情</Button> : !isWeb && <div className="inline-actions">
                <Button disabled={blocked || unavailable} title={unavailable ? (connection?.reason || "该平台连接服务暂不可用。") : undefined} onClick={() => onOpen(platform.id)}>{unavailable ? "暂不可用" : connection?.status === "CONNECTED" ? "查看连接" : connection?.status === "EXPIRED" ? "重新连接" : "连接"}</Button>
                {connection?.status === "CONNECTED" && <Button variant="ghost" disabled={blocked} onClick={() => onDisconnect(connection)}>断开</Button>}
              </div>}</td>
            </tr>;
          });
        })}</tbody>
      </table>
    </div>
    {selectedId && <Modal title="平台连接详情" onClose={() => setSelectedId(null)} footer={<>
      <Button onClick={() => setSelectedId(null)}>关闭</Button>
      <Button disabled={loading} onClick={onRefresh}>{loading ? "正在读取" : "刷新状态"}</Button>
    </>}>
      {selected?.registration ? <>
        <PlatformLabel platform={selected.platform} size={28} />
        <dl className="detail-list" style={{overflowWrap: "anywhere"}}>
          <div><dt>账号</dt><dd>{connectionAccountLabel(selected, rows!.filter(row => row.platform === selected.platform).indexOf(selected))}</dd></div>
          <div><dt>登记状态</dt><dd>{connectionLabel[selected.status]}</dd></div>
          <div><dt>登记时间</dt><dd>{formatDate(selected.registration.connectedAt)}</dd></div>
          <div><dt>断开时间</dt><dd>{selected.registration.disconnectedAt ? formatDate(selected.registration.disconnectedAt) : "—"}</dd></div>
        </dl>
      </> : <Notice>{loading ? "正在重新读取连接记录…" : error ? `连接详情读取失败：${error}` : "该连接当前不可见，请刷新列表核对。"}</Notice>}
    </Modal>}
  </>;
}
