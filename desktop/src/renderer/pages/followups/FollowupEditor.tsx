import { useEffect, useRef, useState } from "react";
import { z } from "zod";
import { useApp } from "../../app/context";
import { useAction, useLocalDraft, useUnsavedChanges } from "../../app/hooks";
import { boundedRequest } from "../../app/boundedRequest";
import {
  Button,
  Confirm,
  Drawer,
  Field,
  Notice,
  ResourceStatus,
} from "../../components/ui";
import type { Opportunity } from "../../domain/models";
import {
  FOLLOWUP_LABELS,
  followupFieldsSchema,
  legacyNote,
  readSnapshot,
  type FollowupRecord,
  type FollowupSnapshot,
} from "../../domain/followup";
import { isSample } from "../Opportunities";
import { useFollowupOperation } from "./useFollowupOperation";
import { taskDraftOwner } from "../../app/taskDraft";
import { hashText } from "../../domain/taskOperations";
const draftSchema = z.object({
  opportunityId: z.string(),
  status: z.string(),
  note: z.string(),
  contact: z.string(),
  nextStep: z.string(),
  nextDate: z.string(),
  ownerId: z.string(),
  reason: z.string(),
});
type Draft = z.infer<typeof draftSchema>;
function localTime(value: string | null) {
  if (!value) return "";
  const d = new Date(value);
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16);
}
export function FollowupEditor({
  rows,
  members,
  correction,
  loading,
  error,
  onRetry,
  onClose,
  onSaved,
}: {
  rows: Opportunity[];
  members: FollowupSnapshot["members"];
  correction?: FollowupRecord;
  loading: boolean;
  error: string;
  onRetry: () => void;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { service, session, route, notify } = useApp();
  const operation = useFollowupOperation();
  const saving = useAction();
  const requested =
    correction?.opportunityId || route.query.get("opportunity") || "";
  const [initial] = useState<Draft>(() => ({
    opportunityId: requested,
    status: correction?.status || "",
    note: correction?.note || "",
    contact: localTime(correction?.occurredAt || null),
    nextStep: correction?.nextStep || "",
    nextDate: localTime(correction?.nextFollowupAt || null).slice(0, 10),
    ownerId: correction?.ownerId || session.userId || "",
    reason: "",
  }));
  const draftKey = `followup:v3:${JSON.stringify([taskDraftOwner(session.userId, session.accountScope), correction?.id || "create", requested || "new"])}`;
  const [draft, setDraft, clear] = useLocalDraft<Draft>(
    draftKey,
    () => initial,
    (value) => draftSchema.safeParse(value).success,
  );
  const [closeAsked, setCloseAsked] = useState(false);
  const [exit, setExit] = useState<"saved" | "close" | null>(null);
  const draftText = JSON.stringify(draftSchema.parse(draft));
  const liveDraft = useRef(draftText);
  liveDraft.current = draftText;
  const recovered = useRef(false);
  const finishRecovered = (hash: string, text: string) => {
    if (!operation.current() || liveDraft.current !== text || recovered.current)
      return;
    recovered.current = true;
    clear();
    const removed = operation.acknowledgeDraft({ key: draftKey, hash });
    notify(
      removed
        ? "原跟进请求已确认保存，已清理相同提交稿。"
        : "原跟进请求已确认保存；本机旧稿尚未移除，继续保留防重复保护。",
      removed ? "success" : "info",
    );
    setExit("saved");
  };
  useEffect(() => {
    let active = true;
    const hashes = operation.resolvedDrafts[draftKey] || [];
    if (hashes.length && !saving.busy && !operation.action.busy)
      void hashText(draftText)
        .then((hash) => {
          if (active && hashes.includes(hash)) finishRecovered(hash, draftText);
        })
        .catch(() => {
          /* Keep the draft if its fingerprint cannot be checked. */
        });
    return () => {
      active = false;
    };
  }, [
    draftKey,
    draftText,
    operation.resolvedDrafts,
    saving.busy,
    operation.action.busy,
  ]);
  const edited = JSON.stringify(draft) !== JSON.stringify(initial);
  useUnsavedChanges(edited && !exit);
  useEffect(() => {
    if (exit === "saved") onSaved();
    else if (exit === "close") onClose();
  }, [exit]);
  const busy = saving.busy || operation.action.busy;
  const close = () => {
    if (busy) return;
    if (edited) setCloseAsked(true);
    else onClose();
  };
  const update = (value: Partial<Draft>) =>
    setDraft((old) => ({ ...old, ...value }));
  const submit = () =>
    saving.run(async () => {
      if (!session.authenticated) throw new Error("请先登录客户空间。");
      const draftHash = await hashText(draftText);
      if (!operation.current()) return;
      // Also gate the click path, so a fast click before the effect settles
      // cannot send the same recovered draft under a fresh request ID.
      if ((operation.resolvedDrafts[draftKey] || []).includes(draftHash)) {
        finishRecovered(draftHash, draftText);
        return;
      }
      const row = rows.find((r) => r.id === draft.opportunityId);
      if (!row || isSample(row) || !draft.status || !draft.note.trim())
        throw new Error("请选择已入库商机、事实类型，并填写实际沟通内容。");
      if (
        correction &&
        (correction.sample ||
          correction.state !== "ACTIVE" ||
          !service.followup)
      )
        throw new Error("此记录当前不能纠正。");
      if (correction && !draft.reason.trim())
        throw new Error("请填写纠正原因，原记录将保留。");
      if (
        draft.contact &&
        (!Number.isFinite(Date.parse(draft.contact)) ||
          Date.parse(draft.contact) > Date.now() + 60000)
      )
        throw new Error("联系时间应为实际已发生的时间。");
      const fields = followupFieldsSchema.safeParse({
        status: draft.status,
        note: draft.note,
        occurredAt: draft.contact
          ? new Date(draft.contact).toISOString()
          : null,
        nextStep: draft.nextStep,
        nextFollowupAt: draft.nextDate
          ? new Date(draft.nextDate + "T09:00:00").toISOString()
          : null,
        ownerId: draft.ownerId,
      });
      if (!fields.success)
        throw new Error("请核对事实类型、时间、负责人及500字内容限制。");
      if (
        service.followup &&
        (!row.profileVersionId ||
          !members.some((m) => m.id === fields.data.ownerId))
      )
        throw new Error("商机版本或负责人无效，请刷新后重新选择。");
      const version = JSON.stringify([row.profileVersionId, row.updatedAt]);
      const fresh = await boundedRequest(() => service.opportunity(row.id), {
        timeoutMessage: "商机核对超时，尚未保存。",
      });
      if (!operation.current()) return;
      if (
        !fresh ||
        fresh.id !== row.id ||
        isSample(fresh) ||
        JSON.stringify([fresh.profileVersionId, fresh.updatedAt]) !== version
      )
        throw new Error("商机或画像版本已变化，请刷新后核对内容，尚未保存。");
      if (correction) {
        const snapshot = readSnapshot(
          await boundedRequest(() => service.followup!.list(), {
            timeoutMessage: "记录核对超时，尚未纠正。",
          }),
        );
        if (!operation.current()) return;
        const target = snapshot.records.find((r) => r.id === correction.id);
        if (
          !target ||
          target.revision !== correction.revision ||
          target.state !== "ACTIVE" ||
          target.profileVersionId !== row.profileVersionId
        )
          throw new Error("原记录已变化，请刷新后核对，尚未纠正。");
      }
      const binding = {
        opportunityId: row.id,
        profileVersionId: row.profileVersionId || "legacy-unversioned",
        action: correction
          ? ("correct" as const)
          : service.followup
            ? ("create" as const)
            : ("legacy-create" as const),
        targetId: correction?.id || "",
        targetRevision: correction?.revision || 0,
        requestId: crypto.randomUUID(),
      };
      const result = await operation.run(
        {
          binding,
          values: fields.data,
          reason: correction ? draft.reason.trim() : undefined,
        },
        !service.followup
          ? () =>
              service.addFollowup(
                row.id,
                fields.data.status,
                legacyNote(fields.data),
              )
          : undefined,
        { key: draftKey, hash: draftHash },
      );
      if (!operation.current()) return;
      if (result === "SUCCEEDED") {
        recovered.current = true;
        clear();
        operation.acknowledgeDraft({ key: draftKey, hash: draftHash });
        notify(
          correction ? "纠正记录已保存，原登记保留。" : "跟进事实已保存。",
          "success",
        );
        setExit("saved");
      } else if (result === "FAILED")
        throw new Error("服务已确认本次保存失败，输入已保留，可核对后重试。");
    });
  return (
    <>
      <Drawer
        title={correction ? "纠正跟进" : "添加跟进"}
        onClose={close}
        footer={
          <>
            <Button disabled={busy} onClick={close}>
              取消
            </Button>
            <Button
              variant="primary"
              loading={busy}
              disabled={
                !session.authenticated ||
                loading ||
                !!error ||
                operation.blocked
              }
              onClick={() => void submit()}
            >
              保存记录
            </Button>
          </>
        }
      >
        {!session.authenticated && (
          <Notice tone="warning">请先登录后登记客户跟进。</Notice>
        )}
        <ResourceStatus loading={loading} error={error} onRetry={onRetry} />
        <fieldset
          className="followup-fields"
          disabled={busy || !session.authenticated}
        >
          <Field label="关联商机" required>
            <select
              aria-label="关联商机"
              value={draft.opportunityId}
              disabled={loading || !!correction}
              onChange={(e) => update({ opportunityId: e.target.value })}
            >
              <option value="">请选择已入库商机</option>
              {rows
                .filter((r) => !isSample(r))
                .map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.title}
                  </option>
                ))}
            </select>
          </Field>
          <Field label="跟进类型">
            <input aria-label="跟进类型" value="人工登记" readOnly />
          </Field>
          <Field label="事实类型" required>
            <div className="radio-group">
              {(["CONTACTED", "REPLIED", "MEETING", "QUOTED"] as const).map(
                (status) => (
                  <label key={status}>
                    <input
                      type="radio"
                      name="followup-status"
                      checked={draft.status === status}
                      onChange={() => update({ status })}
                    />
                    {FOLLOWUP_LABELS[status]}
                  </label>
                ),
              )}
            </div>
          </Field>
          <Field label="联系时间">
            <input
              type="datetime-local"
              aria-label="联系时间"
              value={draft.contact}
              onChange={(e) => update({ contact: e.target.value })}
            />
          </Field>
          <Field label="备注" required>
            <textarea
              aria-label="跟进备注"
              rows={4}
              maxLength={500}
              value={draft.note}
              onChange={(e) => update({ note: e.target.value })}
              placeholder="记录实际沟通内容"
            />
            <span className="character-count">
              {Array.from(draft.note).length}/500
            </span>
          </Field>
          <Field label="下一步">
            <textarea
              aria-label="下一步"
              rows={2}
              maxLength={500}
              value={draft.nextStep}
              onChange={(e) => update({ nextStep: e.target.value })}
              placeholder="输入下一步计划或待办事项"
            />
            <span className="character-count">
              {Array.from(draft.nextStep).length}/500
            </span>
          </Field>
          <Field label="下次跟进">
            <input
              type="date"
              aria-label="下次跟进"
              value={draft.nextDate}
              onChange={(e) => update({ nextDate: e.target.value })}
            />
          </Field>
          <Field label="负责人">
            <select
              aria-label="负责人"
              value={draft.ownerId}
              onChange={(e) => update({ ownerId: e.target.value })}
            >
              {service.followup ? (
                <>
                  <option value="">请选择负责人</option>
                  {members.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.name}
                    </option>
                  ))}
                </>
              ) : (
                <option value={session.userId || ""}>当前成员</option>
              )}
            </select>
          </Field>
          {correction && (
            <Field label="纠正原因" required>
              <textarea
                aria-label="纠正原因"
                maxLength={500}
                value={draft.reason}
                onChange={(e) => update({ reason: e.target.value })}
              />
            </Field>
          )}
        </fieldset>
        <Notice>
          {service.followup
            ? "人工登记与通道回复分开，原登记不会因纠正被抹除。"
            : "联系时间与下一步将随备注保存；结构化计划和提醒服务尚未接通。"}
        </Notice>
        {operation.blocked && (
          <Notice tone="warning">
            有操作结果待确认，请关闭抽屉后核对原操作，当前内容仍保留。
          </Notice>
        )}
        {(saving.error || operation.action.error) && (
          <Notice tone="error">{saving.error || operation.action.error}</Notice>
        )}
      </Drawer>
      {closeAsked && (
        <Confirm
          title="保留未保存内容并关闭？"
          onCancel={() => setCloseAsked(false)}
          confirmText="保留并关闭"
          onConfirm={() => {
            setCloseAsked(false);
            setExit("close");
          }}
        >
          <p>内容保存在当前账号的本机会话，尚未同步到客户空间。</p>
        </Confirm>
      )}
    </>
  );
}
