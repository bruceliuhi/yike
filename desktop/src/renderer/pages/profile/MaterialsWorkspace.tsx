import { useLayoutEffect, useMemo, useRef, useState } from "react";
import { Plus, FileText } from "@phosphor-icons/react";
import { useApp } from "../../app/context";
import { boundedRequest } from "../../app/boundedRequest";
import { useResource } from "../../app/hooks";
import {
  Badge,
  Button,
  Empty,
  Notice,
  ResourceStatus,
  formatDate,
} from "../../components/ui";
import {
  materialStatus,
  materialInputSchema,
  parseMaterials,
  type Material,
  type MaterialReceipt,
  type MaterialInput,
} from "../../domain/materials";
import type { Profile, ProfileFields } from "../../domain/models";
import type { MaterialService } from "../../services/materials";
import { MaterialEditor } from "./MaterialEditor";
import { MaterialExtraction } from "./MaterialExtraction";
import { MaterialImpact } from "./MaterialImpact";
import { useMaterialRequest } from "./useMaterialRequest";
import { LocalMaterialDrafts, type LocalMaterialDraft } from "./LocalMaterialDrafts";
import { localMaterialIdentity } from "./localMaterialIdentity";
import { materialOwner } from "./materialOperationStorage";
import "./profile.css";

type MaterialsWorkspaceProps = {
  api: MaterialService;
  profile: Profile;
  currentFields: ProfileFields;
  onApply: (fields: Partial<ProfileFields>) => void;
  localDrafts?: LocalMaterialDraft[];
  onEditLocal?: (draft: LocalMaterialDraft) => void;
  onRemoveLocal?: (draft: LocalMaterialDraft) => void;
};
export function MaterialsWorkspace(props: MaterialsWorkspaceProps) {
  const { session } = useApp();
  // Remount the entire editor/impact boundary synchronously on identity changes.
  const boundary = useMemo(() => crypto.randomUUID(), [props.api, props.profile.id, props.profile.version, session.authenticated, session.userId, session.accountScope?.id, session.accountScope?.version]);
  return <ScopedMaterialsWorkspace key={boundary} {...props} />;
}

function ScopedMaterialsWorkspace({api, profile, currentFields, onApply, localDrafts = [], onEditLocal, onRemoveLocal}: MaterialsWorkspaceProps) {
  const { session, notify } = useApp();
  const resource = useResource(
    async () =>
      parseMaterials(
        await boundedRequest(() => api.list(profile.id), {
          timeoutMessage: "资料列表加载超时，请重试。",
        }),
        profile.id,
      ),
    [api, profile.id, session.authenticated, session.userId, session.accountScope?.id, session.accountScope?.version],
  );
  const [editor, setEditor] = useState<{
    id: string;
    record?: Material;
    initialInput?: MaterialInput;
  } | null>(null);
  const [extraction, setExtraction] = useState<{
    record: Material;
    mode: "review" | "apply";
  } | null>(null);
  const [impact, setImpact] = useState<{
    record: Material;
    kind: "remove" | "revoke";
  } | null>(null);
  const receive = (receipt: MaterialReceipt) => {
    resource.setData((previous) =>
      receipt.kind === "remove"
        ? previous?.filter((record) => record.id !== receipt.materialId)
        : [
            receipt.record!,
            ...(previous || []).filter(
              (record) => record.id !== receipt.materialId,
            ),
          ],
    );
    if (receipt.kind === "save") {
      setEditor(null);
      notify("资料草稿已同步，尚未解析确认。", "success");
    }
    if (receipt.kind === "parse")
      notify(
        receipt.record?.status === "PARSING"
          ? "解析请求已接收，请刷新查看解析状态。"
          : "解析状态已更新，请核对原文和提取结果。",
        "info",
      );
    if (receipt.kind === "confirm") {
      setExtraction(null);
      notify("资料提取结果已确认；业务画像仍需单独保存和确认。", "success");
    }
    if (receipt.kind === "remove" || receipt.kind === "revoke") {
      setImpact(null);
      notify(
        receipt.kind === "remove" ? "资料已移除。" : "资料引用已撤销。",
        "success",
      );
    }
  };
  const request = useMaterialRequest(api, profile.id, receive);
  const blocked =
    !!request.pending || request.historical.length > 0 || !!request.storageError || request.action.busy;
  const [preparing, setPreparing] = useState(false);
  const live = useRef(false);
  const preparingRef = useRef(false);
  const latest = useRef({ blocked, resource });
  latest.current = { blocked, resource };
  useLayoutEffect(() => {
    live.current = true;
    return () => { live.current = false; };
  }, []);
  const transfer = async (draft: LocalMaterialDraft) => {
    if (blocked || preparingRef.current || resource.loading || resource.error) return;
    preparingRef.current = true;
    setPreparing(true);
    request.action.setError("");
    try {
      const parsed = materialInputSchema.safeParse({
        name: draft.name, text: draft.text, purpose: draft.purpose, visibility: draft.visibility,
        ...(draft.fileName ? { fileName: draft.fileName, bytes: draft.bytes } : {}),
      });
      if (!parsed.success) throw new Error("本机草稿格式不完整，请先编辑检查名称、内容和用途。");
      const initialInput = parsed.data;
      const id = await localMaterialIdentity(materialOwner(session), profile.id, draft.id);
      if (!live.current) return;
      const state = latest.current;
      if (state.blocked || state.resource.loading || state.resource.error) return;
      const record = state.resource.data?.find(item => item.id === id);
      if (record?.status === "PARSING") throw new Error("这份资料正在解析，请完成后再带入修改。");
      if (!record && (state.resource.data?.length ?? 0) >= 500) throw new Error("当前画像资料已达上限，请先整理已有资料。");
      setEditor({ id, record, initialInput });
    } catch (error) {
      if (live.current) request.action.setError(error instanceof Error ? error.message : "资料暂时无法带入，请重试。");
    } finally {
      preparingRef.current = false;
      if (live.current) setPreparing(false);
    }
  };
  const openEditor = (record?: Material) => {
    request.action.setError("");
    setEditor({ id: record?.id || crypto.randomUUID(), record });
  };
  return (
    <>
      <div className="section-heading">
        <span className="muted">画像版本 {profile.version} · 客户空间资料</span>
        <Button
          variant="primary"
          disabled={
            blocked || preparing ||
            resource.loading ||
            !!resource.error ||
            (resource.data?.length ?? 0) >= 500
          }
          onClick={() => openEditor()}
        >
          <Plus />
          添加资料
        </Button>
      </div>
      <ResourceStatus
        loading={resource.loading}
        error={resource.error}
        onRetry={() => void resource.reload()}
      />
      {request.storageError && (
        <Notice tone="error">
          {request.storageError}
          <Button variant="ghost" onClick={request.reloadStorage}>
            重新读取操作记录
          </Button>
        </Notice>
      )}
      {request.pending && (
        <Notice tone="warning">
          资料操作结果待确认，当前不会重复提交。
          <Button
            loading={request.action.busy}
            onClick={() => void request.reconcile()}
          >
            核对原资料操作
          </Button>
        </Notice>
      )}
      {request.historical.length > 0 && (
        <Notice tone="warning">
          存在未绑定当前客户空间版本的旧资料操作。记录已保留；确认原请求归属和结果前，不会重新提交或在当前空间查询。
          {request.historical.map((entry) => (
            <details key={entry.requestId}>
              <summary>查看原资料操作身份</summary>
              <p>画像版本：{entry.profileVersionId}</p>
              <p>空间：{entry.accountScope === "unbound" ? "旧记录未保存空间归属" : entry.accountScope ? `${entry.accountScope.id} · 版本 ${entry.accountScope.version}` : "原请求未提供空间身份"}</p>
              <label>
                原请求 ID（可复制）
                <input readOnly aria-label="旧资料操作请求ID" value={entry.requestId} onFocus={event => event.currentTarget.select()} />
              </label>
            </details>
          ))}
          <Button variant="ghost" onClick={request.reloadStorage}>重新读取操作记录</Button>
        </Notice>
      )}
      {request.action.error && !editor && !extraction && !impact && (
        <Notice tone="error">{request.action.error}</Notice>
      )}
      {resource.data && (
        <div className="table-scroll material-table">
          <table>
            <thead>
              <tr>
                <th>资料名称</th>
                <th>用途</th>
                <th>引用范围</th>
                <th>状态</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {resource.data.map((record) => (
                <tr key={record.id}>
                  <td>
                    <FileText aria-hidden />
                    {record.name}
                    <small>
                      版本 {record.version} · {formatDate(record.updatedAt)}
                    </small>
                  </td>
                  <td>{record.purpose}</td>
                  <td>
                    {record.status === "REVOKED"
                      ? "已停止引用"
                      : record.visibility === "internal"
                        ? "仅供内部判断"
                        : record.status === "READY"
                          ? "允许对外引用"
                          : "对外引用待确认"}
                  </td>
                  <td>
                    <Badge
                      tone={
                        record.status === "READY"
                          ? "green"
                          : record.status === "FAILED"
                            ? "orange"
                            : "neutral"
                      }
                    >
                      {materialStatus[record.status]}
                    </Badge>
                    {record.status === "FAILED" && (
                      <small>{record.failure || "解析未完成，请重试。"}</small>
                    )}
                  </td>
                  <td>
                    <div className="inline-actions">
                      <Button
                        variant="ghost"
                        disabled={blocked || record.status === "PARSING"}
                        onClick={() => openEditor(record)}
                      >
                        编辑
                      </Button>
                      {["DRAFT", "FAILED", "REVOKED"].includes(
                        record.status,
                      ) && (
                        <Button
                          variant="ghost"
                          disabled={blocked}
                          onClick={() =>
                            void request.run({
                              kind: "parse",
                              materialId: record.id,
                              expectedVersion: record.version,
                            })
                          }
                        >
                          {record.status === "FAILED" ? "重试解析" : "解析资料"}
                        </Button>
                      )}
                      {record.status === "PARSING" && (
                        <Button
                          variant="ghost"
                          disabled={resource.loading}
                          onClick={() => void resource.reload()}
                        >
                          刷新解析状态
                        </Button>
                      )}
                      {record.status === "REVIEW_REQUIRED" && (
                        <Button
                          variant="ghost"
                          disabled={blocked}
                          onClick={() => {
                            request.action.setError("");
                            setExtraction({ record, mode: "review" });
                          }}
                        >
                          核对提取
                        </Button>
                      )}
                      {record.status === "READY" && (
                        <>
                          <Button
                            variant="ghost"
                            disabled={blocked}
                            onClick={() =>
                              setExtraction({ record, mode: "apply" })
                            }
                          >
                            用于画像
                          </Button>
                          <Button
                            variant="ghost"
                            disabled={blocked}
                            onClick={() => {
                              request.action.setError("");
                              setImpact({ record, kind: "revoke" });
                            }}
                          >
                            撤销引用
                          </Button>
                        </>
                      )}
                      <Button
                        variant="ghost"
                        disabled={blocked || record.status === "PARSING"}
                        onClick={() => {
                          request.action.setError("");
                          setImpact({ record, kind: "remove" });
                        }}
                      >
                        移除
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {resource.data?.length === 0 && (
        <Empty title="暂无资料" description="添加产品介绍或真实案例。" />
      )}
      {localDrafts.length > 0 && onEditLocal && onRemoveLocal && (
        <details className="local-material-drafts" open>
          <summary>本机资料草稿 · {localDrafts.length} 份</summary>
          <p className="muted">本机草稿仍可编辑；选择带入，再保存到当前画像。</p>
          <LocalMaterialDrafts drafts={localDrafts} onEdit={onEditLocal} onRemove={onRemoveLocal}
            onTransfer={draft => void transfer(draft)}
            transferDisabled={blocked || preparing || resource.loading || !!resource.error} />
        </details>
      )}
      {editor && (
        <MaterialEditor
          key={editor.id}
          record={editor.record}
          initialInput={editor.initialInput}
          busy={request.action.busy}
          locked={!!request.pending || request.historical.length > 0 || !!request.storageError}
          progress={request.progress}
          error={request.action.error}
          onClose={() => setEditor(null)}
          onSave={(input) =>
            void request.run({
              kind: "save",
              materialId: editor.id,
              expectedVersion: editor.record?.version ?? null,
              input,
            })
          }
        />
      )}
      {extraction && (
        <MaterialExtraction
          key={`${extraction.record.id}:${extraction.record.version}:${extraction.mode}`}
          record={extraction.record}
          currentFields={currentFields}
          mode={extraction.mode}
          busy={request.action.busy}
          locked={blocked && !request.action.busy}
          error={request.action.error}
          onClose={() => setExtraction(null)}
          onConfirm={(fields) => {
            if (extraction.mode === "apply") {
              if (!blocked) {
                onApply(fields);
                setExtraction(null);
              }
              return;
            }
            void request.run({
              kind: "confirm",
              materialId: extraction.record.id,
              expectedVersion: extraction.record.version,
              extractionId: extraction.record.extraction!.id,
              fields,
            });
          }}
        />
      )}
      {impact && (
        <MaterialImpact
          key={`${impact.record.id}:${impact.record.version}:${impact.kind}`}
          api={api}
          record={impact.record}
          kind={impact.kind}
          busy={request.action.busy}
          locked={!!request.pending || request.historical.length > 0 || !!request.storageError}
          error={request.action.error}
          onClose={() => setImpact(null)}
          onConfirm={(impactToken) =>
            void request.run({
              kind: impact.kind,
              materialId: impact.record.id,
              expectedVersion: impact.record.version,
              impactToken,
            })
          }
        />
      )}
    </>
  );
}
