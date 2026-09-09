import { PlatformLabel } from "../../components/Platform";
import { Button, Modal, Notice } from "../../components/ui";
import { PLATFORMS } from "../../domain/models";
import type { useConnectionDisconnect } from "./useConnectionDisconnect";

export function DisconnectPanel({
  action,
}: {
  action: ReturnType<typeof useConnectionDisconnect>;
}) {
  const target = action.target;
  if (!target) return null;
  const name =
    PLATFORMS.find((item) => item.id === target.platform)?.name ||
    target.platform;
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
        {target.accountName || target.accountId}”
      </p>
      <p>依赖该账号的采集与触达任务需要重新连接后才能继续。</p>
      {action.busy && (
        <p role="status">
          {action.phase === "preflight"
            ? "正在核对客户身份与执行账号…"
            : action.phase === "submitting"
              ? "正在等待断开回执…"
              : "正在读取原账号连接状态…"}
        </p>
      )}
      {action.pending && (
        <Notice tone="warning">
          {action.pending.acknowledged
            ? "已收到原请求回执，仍需核对原账号已断开。"
            : "原请求回执尚未确认，已保留核对记录。当前未重发，也未撤销服务端请求。"}
        </Notice>
      )}
      {action.message && <Notice tone="warning">{action.message}</Notice>}
      <p className="field-hint">
        关闭或取消等待不会删除核对记录。核对完成前，该平台不能再次断开或重新连接。
      </p>
    </Modal>
  );
}
