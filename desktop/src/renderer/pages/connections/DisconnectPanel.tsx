import { PlatformLabel } from "../../components/Platform";
import { Button, Modal, Notice } from "../../components/ui";
import { PLATFORMS, type PlatformConnection } from "../../domain/models";
import type { useConnectionDisconnect } from "./useConnectionDisconnect";
import { connectionAccountLabel } from "./ConnectionRegistryTable";

export function DisconnectPanel({
  action,
  rows,
}: {
  action: ReturnType<typeof useConnectionDisconnect>;
  rows?: PlatformConnection[];
}) {
  const target = action.target;
  if (!target) return null;
  const name =
    PLATFORMS.find((item) => item.id === target.platform)?.name ||
    target.platform;
  const matches = rows?.filter(row => row.platform === target.platform) || [];
  const index = matches.findIndex(row => row.accountId === target.accountId && !row.registration);
  const accountName = index >= 0 ? connectionAccountLabel(matches[index], index) : target.accountName?.trim() || `${name}原账号`;
  return (
    <Modal
      title={action.pending ? `核对${name}断开结果` : `断开${name}连接？`}
      onClose={action.close}
      footer={
        <>
          <Button onClick={action.close}>
            {action.busy ? "取消等待并关闭" : action.pending ? "关闭" : "取消"}
          </Button>
          <Button
            variant={action.pending ? "primary" : "danger"}
            loading={action.busy}
            onClick={action.pending ? action.check : action.start}
          >
            {action.pending ? "核对连接状态" : "断开连接"}
          </Button>
        </>
      }
    >
      <p>
        <PlatformLabel platform={target.platform} /> · 账号“
        {accountName}”
      </p>
      <p>依赖该账号的采集与触达任务需要重新连接后才能继续。</p>
      {action.busy && (
        <p role="status">
          {action.phase === "preflight"
            ? "正在检查账号…"
            : action.phase === "submitting"
              ? "正在断开连接…"
              : "正在检查连接状态…"}
        </p>
      )}
      {action.pending && (
        <Notice tone="warning">
          断开结果待确认，请检查连接状态。
        </Notice>
      )}
      {action.message && <Notice tone="warning">{action.message}</Notice>}
      <p className="field-hint">
        确认断开结果前，暂不能重新连接。
      </p>
    </Modal>
  );
}
