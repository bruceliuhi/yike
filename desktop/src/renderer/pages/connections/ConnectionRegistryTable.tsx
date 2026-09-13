import { useState } from "react";
import { PlatformLabel } from "../../components/Platform";
import { Badge, Button, Modal, Notice, formatDate } from "../../components/ui";
import { PLATFORMS, type PlatformConnection } from "../../domain/models";

export const connectionLabel: Record<PlatformConnection["status"], string> = {
  CONNECTED: "已连接", DISCONNECTED: "未连接", EXPIRED: "登录已失效",
  LIMITED: "连接受限", UNAVAILABLE: "连接服务待接通", UNVERIFIED: "待核验",
};

export function capabilityText(capabilities: string[]) {
  const labels: Record<string, string> = {
    search: "搜索公开内容", read: "读取原文", monitor: "持续监控", comment: "发布评论", dm: "发送私信",
  };
  return [...new Set(capabilities.map(value => labels[value] || "其他能力待核验"))].join("、");
}

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
        <thead><tr><th>平台</th><th>当前账号</th><th>连接状态</th><th>可用能力</th><th>操作</th></tr></thead>
        <tbody>{PLATFORMS.flatMap(platform => {
          const matches = rows?.filter(row => row.platform === platform.id) || [];
          const entries: (PlatformConnection | undefined)[] = matches.length ? matches : [undefined];
          return entries.map((connection, index) => {
            const registered = connection?.registration;
            const isWeb = platform.id === "web";
            const blocked = pendingPlatforms.includes(platform.id);
            return <tr key={registered?.connectionId || `${platform.id}:${connection?.accountId || "empty"}:${index}`}>
              <td><PlatformLabel platform={platform.id} size={22} /></td>
              <td className="connection-account">
                <span>{connection?.accountName || connection?.accountId || (isWeb ? "无需账号" : "—")}</span>
                {registered && <p className="field-hint">已登记设备 · 连接 {index + 1}</p>}
              </td>
              <td>{isWeb && !connection ? "—" : <Badge tone={connection?.status === "CONNECTED" ? "green" : ["EXPIRED", "LIMITED", "UNVERIFIED"].includes(connection?.status || "") ? "orange" : "neutral"}>
                {connection ? connectionLabel[connection.status] : rows ? "未连接" : "待读取连接状态"}
              </Badge>}</td>
              <td>{connection?.capabilities.length ? capabilityText(connection.capabilities) : registered ? "尚无已核验能力" : isWeb ? "公开页面读取（范围待验收）" : "待检查平台能力"}</td>
              <td>{registered ? <Button onClick={() => setSelectedId(registered.connectionId)} aria-label={`查看${platform.name}连接详情：${connection.accountName || connection.accountId}，连接 ${index + 1}`}>查看详情</Button> : !isWeb && <div className="inline-actions">
                <Button disabled={blocked} onClick={() => onOpen(platform.id)}>{connection?.status === "CONNECTED" ? "查看连接" : connection?.status === "EXPIRED" ? "重新连接" : "连接"}</Button>
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
          <div><dt>账号</dt><dd>{selected.accountName || selected.accountId}</dd></div>
          <div><dt>登记状态</dt><dd>{connectionLabel[selected.status]}</dd></div>
          <div><dt>登记时间</dt><dd>{formatDate(selected.registration.connectedAt)}</dd></div>
          <div><dt>断开时间</dt><dd>{selected.registration.disconnectedAt ? formatDate(selected.registration.disconnectedAt) : "—"}</dd></div>
          <div><dt>可用能力</dt><dd>{selected.capabilities.length ? capabilityText(selected.capabilities) : "尚无已核验能力"}</dd></div>
        </dl>
        <Notice>当前可查看服务端连接记录；本机账号登录、能力核验与断开操作仍待接通。</Notice>
        <details>
          <summary>查看连接技术信息</summary>
          <dl className="detail-list" style={{overflowWrap: "anywhere"}}>
            <div><dt>连接编号</dt><dd>{selected.registration.connectionId}</dd></div>
            <div><dt>设备编号</dt><dd>{selected.registration.deviceId}</dd></div>
            <div><dt>连接版本</dt><dd>v{selected.registration.version}</dd></div>
          </dl>
        </details>
      </> : <Notice>{loading ? "正在重新读取连接记录…" : error ? `连接详情读取失败：${error}` : "该连接当前不可见，请刷新列表核对。"}</Notice>}
    </Modal>}
  </>;
}
