import { useEffect, useState } from "react";
import { boundedRequest } from "../../app/boundedRequest";
import { useResource } from "../../app/hooks";
import { Button, Modal, Notice, ResourceStatus } from "../../components/ui";
import { materialImpactSchema, type Material } from "../../domain/materials";
import type { MaterialService } from "../../services/materials";

export function MaterialImpact({
  api,
  record,
  kind,
  busy,
  locked,
  error,
  onClose,
  onConfirm,
}: {
  api: MaterialService;
  record: Material;
  kind: "remove" | "revoke";
  busy: boolean;
  locked: boolean;
  error: string;
  onClose: () => void;
  onConfirm: (token: string) => void;
}) {
  const [verified, setVerified] = useState(false);
  const [now, setNow] = useState(Date.now());
  const resource = useResource(async () => {
    const result = materialImpactSchema.parse(
      await boundedRequest(
        () =>
          api.impact(record.profileVersionId, record.id, record.version, kind),
        { timeoutMessage: "引用影响核对超时，请重试。" },
      ),
    );
    if (
      result.profileVersionId !== record.profileVersionId ||
      result.materialId !== record.id ||
      result.version !== record.version ||
      result.action !== kind
    )
      throw new Error("引用影响与当前资料版本不匹配，请重新核对。");
    return result;
  }, [api, record.id, record.version, kind]);
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  const expired = resource.data && Date.parse(resource.data.expiresAt) <= now;
  const refresh = () => {
    setVerified(false);
    void resource.reload();
  };
  return (
    <Modal
      title={kind === "remove" ? "移除资料？" : "撤销资料引用？"}
      onClose={() => {
        if (!busy) onClose();
      }}
      footer={
        <>
          <Button disabled={busy} onClick={onClose}>
            取消
          </Button>
          <Button
            variant="primary"
            loading={busy}
            disabled={
              locked ||
              !verified ||
              !resource.data ||
              expired ||
              resource.loading
            }
            onClick={() => {
              if (
                resource.data &&
                verified &&
                !busy &&
                !locked &&
                Date.parse(resource.data.expiresAt) > Date.now()
              )
                onConfirm(resource.data.token);
            }}
          >
            {kind === "remove" ? "确认移除" : "确认撤销引用"}
          </Button>
        </>
      }
    >
      <p>
        {record.name} · 资料版本 {record.version}
      </p>
      <ResourceStatus
        loading={resource.loading}
        error={resource.error}
        onRetry={refresh}
      />
      {resource.data && (
        <>
          <p>
            {resource.data.references.length
              ? "当前引用此版本的内容："
              : "当前版本没有活动引用。"}
          </p>
          {resource.data.references.length > 0 && (
            <ul>
              {resource.data.references.map((reference, index) => (
                <li key={index}>
                  {reference.kind === "profile" ? "画像" : "联系草稿"}：
                  {reference.label}
                </li>
              ))}
            </ul>
          )}
          <Notice>
            停止后续引用，历史版本与审计记录保留。未发送草稿需重新核对，已发送内容不会撤回。
          </Notice>
          {expired ? (
            <Notice tone="warning">
              引用信息已过期，请
              <Button variant="ghost" onClick={refresh}>
                重新核对
              </Button>
              。
            </Notice>
          ) : (
            <label className="checkbox-row">
              <input
                type="checkbox"
                disabled={busy || locked}
                checked={verified}
                onChange={(e) => setVerified(e.target.checked)}
              />
              已核对引用影响
            </label>
          )}
        </>
      )}
      {error && <Notice tone="error">{error}</Notice>}
    </Modal>
  );
}
