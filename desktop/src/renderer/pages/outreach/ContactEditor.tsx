import { Fragment, useEffect, useRef, useState, type ReactNode } from "react";
import { ArrowSquareOut, Copy, PaperPlaneTilt } from "@phosphor-icons/react";
import { useApp } from "../../app/context";
import {
  useAction,
  useLocalDraft,
  useResource,
  useUnsavedChanges,
} from "../../app/hooks";
import { boundedRequest } from "../../app/boundedRequest";
import {
  Badge,
  Button,
  Confirm,
  Field,
  Modal,
  Notice,
  Tabs,
  formatDate,
} from "../../components/ui";
import type {
  ContactDraft,
  Opportunity,
  PlatformConnection,
} from "../../domain/models";
import { errorMessage } from "../../services/contracts";
import {
  COACH_PURPOSES,
  type CoachPurpose,
  type DraftSaveReceipt,
} from "../../domain/shortCoach";
import { EvidencePanel, isSample } from "../Opportunities";
import { ContactNotes } from "./ContactNotes";
import { ShortCoachPanel } from "./ShortCoachPanel";
import { useContactDraftSave } from "./useContactDraftSave";
import { useLatestContactDraft } from "./useLatestContactDraft";
import { nativeOutreachLedgerKey, useNativeOutreachRecord } from "./nativeOutreachLedger";
import { nativeOutreachCommand } from "./NativeSendConfirmation";
import {ContactMaterialQuotes} from './ContactMaterialQuotes';
import "./short-coach.css";

function initialDraft(
  row: Opportunity,
  channel: "comment" | "dm",
): ContactDraft {
  const content = channel === "comment" ? row.comment : row.dm;
  return {
    opportunityId: row.id,
    channel,
    content,
    version: 1,
    savedContent: content,
    accountId: "",
    recipient: "",
  };
}
interface DraftSet {
  comment: ContactDraft;
  dm: ContactDraft;
}
interface DraftPersistence {
  savedMaterialReferences?: string;
  known: boolean;
  previousRequestId: string | null;
  savedAccountId: string;
  savedRecipient: string;
  profileVersionId: string;
  sourceEvidenceVersion: string | null;
}
type DraftPersistenceSet = Record<"comment" | "dm", DraftPersistence>;

export function ContactEditor({
  row,
  renderConfirmation,
}: {
  row: Opportunity;
  renderConfirmation: (props: {
    draft: ContactDraft;
    connection?: PlatformConnection;
    onClose: () => void;
  }) => ReactNode;
}) {
  const { service, session, route, navigate, notify } = useApp();
  const sample = isSample(row);
  const [channel, setChannel] = useState<"comment" | "dm">(() =>
    route.query.get("channel") === "dm" ? "dm" : "comment",
  );
  const [drafts, setDrafts] = useLocalDraft<DraftSet>(
    `contact:${session.userId || "public"}:${row.id}${session.accountScope ? ":" + JSON.stringify(session.accountScope) : ""}`,
    () => ({
      comment: initialDraft(row, "comment"),
      dm: initialDraft(row, "dm"),
    }),
  );
  const draft = sample ? initialDraft(row, channel) : drafts[channel];
  const persistenceKey = `contact-persistence:${session.userId || "public"}:${row.id}${session.accountScope ? ":" + JSON.stringify(session.accountScope) : ""}`;
  const [persistence, setPersistence] = useLocalDraft<DraftPersistenceSet>(
    persistenceKey,
    () => ({
      comment: {
        known: false,
        previousRequestId: null,
        savedAccountId: "",
        savedRecipient: "",
        profileVersionId: row.profileVersionId,
        sourceEvidenceVersion: row.sourceEvidenceVersion || null,
      },
      dm: {
        known: false,
        previousRequestId: null,
        savedAccountId: "",
        savedRecipient: "",
        profileVersionId: row.profileVersionId,
        sourceEvidenceVersion: row.sourceEvidenceVersion || null,
      },
    }),
  );
  const persisted = persistence[channel];
  const native = !sample && row.platform === "xhs" && channel === "comment" && !!nativeOutreachCommand();
  const nativeRecord = useNativeOutreachRecord(native ? nativeOutreachLedgerKey(session,row.id,channel) : null);
  const [purposes, setPurposes] = useLocalDraft<
    Record<"comment" | "dm", CoachPurpose>
  >(
    `contact-purpose:${session.userId || "public"}:${row.id}:${session.accountScope ? JSON.stringify(session.accountScope) : "legacy"}`,
    {
      comment: sample ? "materials" : "requirement",
      dm: sample ? "materials" : "requirement",
    },
    (value) =>
      !!value &&
      typeof value === "object" &&
      ["comment", "dm"].every((key) =>
        Object.hasOwn(COACH_PURPOSES, (value as Record<string, string>)[key]),
      ),
  );
  const [savedEpoch, setSavedEpoch] = useState(0);
  const [generated, setGenerated] = useState<{
    channel: "comment" | "dm";
    content: string;
    version: number;
  } | null>(null);
  const [pendingRegenerate, setPendingRegenerate] = useState(false);
  const [generationFailed, setGenerationFailed] = useState(false);
  const action = useAction();
  const request = useRef(0);
  const live = useRef(draft);
  live.current = draft;
  useEffect(
    () => () => {
      request.current++;
    },
    [],
  );
  const connections = useResource(
    () =>
      sample
        ? Promise.resolve([] as PlatformConnection[])
        : service.connections(),
    [service, row.id, sample],
  );
  const available = (connections.data || []).filter(
    (c) =>
      c.status === "CONNECTED" &&
      c.accountId &&
      ((native && c.platform === "xhs") || c.capabilities.some((v) =>
        ["send", channel, "send_" + channel].includes(v),
      )),
  );
  const connection = available.find((c) => c.accountId === draft.accountId);
  const dirty =
    JSON.stringify(draft.materialReferences) !== persisted.savedMaterialReferences ||
    draft.content !== draft.savedContent ||
    draft.accountId !== persisted.savedAccountId ||
    draft.recipient !== persisted.savedRecipient ||
    (persisted.known &&
      (persisted.profileVersionId !== row.profileVersionId ||
        persisted.sourceEvidenceVersion !== (row.sourceEvidenceVersion || null)));
  const otherChannel = channel === "comment" ? "dm" : "comment";
  const otherPersisted = persistence[otherChannel];
  const otherDirty =
    JSON.stringify(drafts[otherChannel].materialReferences) !== otherPersisted.savedMaterialReferences ||
    drafts[otherChannel].content !== drafts[otherChannel].savedContent ||
    drafts[otherChannel].accountId !== otherPersisted.savedAccountId ||
    drafts[otherChannel].recipient !== otherPersisted.savedRecipient ||
    (otherPersisted.known &&
      (otherPersisted.profileVersionId !== row.profileVersionId ||
        otherPersisted.sourceEvidenceVersion !==
          (row.sourceEvidenceVersion || null)));
  // Switching purposes keeps both local texts; saving one must not silently
  // remove the exit guard for unsaved edits in the other purpose.
  useUnsavedChanges(!sample && (dirty || otherDirty));
  const edit = (change: Partial<ContactDraft>) => {
    if (sample || !session.authenticated) return;
    setDrafts((old) => ({
      ...old,
      [channel]: {
        ...old[channel],
        ...change,
        version: old[channel].version + 1,
        confirmedFingerprint: undefined,
      },
    }));
  };
  const saving = useContactDraftSave(row, draft, (snapshot, binding) => {
    const submitted = snapshot.draft;
    setDrafts((old) => ({
      ...old,
      [submitted.channel]: (() => {
        const current = old[submitted.channel];
        const initial = initialDraft(row, submitted.channel);
        const sameEditableValues =
          JSON.stringify(current.materialReferences) === JSON.stringify(submitted.materialReferences) &&
          current.content === submitted.content &&
          current.version === submitted.version &&
          current.accountId === submitted.accountId &&
          current.recipient === submitted.recipient;
        const untouchedInitial =
          current.materialReferences === undefined &&
          current.content === initial.content &&
          current.savedContent === initial.savedContent &&
          current.version === initial.version &&
          current.accountId === initial.accountId &&
          current.recipient === initial.recipient;
        if (untouchedInitial && !sameEditableValues)
          return { ...submitted, confirmedFingerprint: undefined };
        return {
          ...current,
          savedContent: submitted.content,
          version: sameEditableValues
            ? submitted.version
            : Math.max(current.version, submitted.version) +
              (current.version <= submitted.version ? 1 : 0),
          confirmedFingerprint: undefined,
        };
      })(),
    }));
    setPersistence((old) => ({
      ...old,
      [submitted.channel]: {
        known: true,
        previousRequestId: binding?.requestId ?? old[submitted.channel].previousRequestId,
        savedAccountId: submitted.accountId,
        savedMaterialReferences: JSON.stringify(submitted.materialReferences),
        savedRecipient: submitted.recipient,
        profileVersionId: snapshot.profileVersionId,
        sourceEvidenceVersion: snapshot.sourceEvidenceVersion,
      },
    }));
    setSavedEpoch((value) => value + 1);
  });
  const applyLatest = (receipt: DraftSaveReceipt, automatic: boolean) => {
    const snapshot = receipt.snapshot!;
    const restored = snapshot.draft;
    const sameEvidence =
      snapshot.profileVersionId === row.profileVersionId &&
      snapshot.sourceEvidenceVersion === (row.sourceEvidenceVersion || null);
    setDrafts((old) => ({
      ...old,
      [channel]: {
        ...restored,
        version: automatic || sameEvidence
          ? restored.version
          : Math.max(old[channel].version, restored.version) + 1,
        confirmedFingerprint: undefined,
      },
    }));
    setPersistence((old) => ({
      ...old,
      [channel]: {
        known: true,
        previousRequestId: receipt.binding.requestId,
        savedAccountId: restored.accountId,
        savedMaterialReferences: JSON.stringify(restored.materialReferences),
        savedRecipient: restored.recipient,
        profileVersionId: snapshot.profileVersionId,
        sourceEvidenceVersion: snapshot.sourceEvidenceVersion,
      },
    }));
  };
  const pristineInitial = (() => {
    const initial = initialDraft(row, channel);
    return !persisted.known && JSON.stringify(draft) === JSON.stringify(initial);
  })();
  const latest = useLatestContactDraft(row, channel, pristineInitial, applyLatest);
  const generate = async () => {
    if (sample || !session.authenticated) return;
    setPendingRegenerate(false);
    setGenerationFailed(false);
    const id = ++request.current;
    const atChannel = channel;
    const version = draft.version;
    const result = await action.run(async () => {
      const value = await boundedRequest(
        () => service.generateContact(row.id, atChannel),
        { timeoutMessage: "草稿生成超时，当前内容已保留，请重试生成。" },
      );
      if (typeof value !== "string" || !value.trim())
        throw new Error("未生成可用草稿，当前内容已保留，请重试生成。");
      return value;
    });
    if (typeof result === "string" && id === request.current) {
      setGenerated({ channel: atChannel, content: result, version });
    } else if (id === request.current) setGenerationFailed(true);
  };
  const applyGenerated = () => {
    if (!generated || sample || !session.authenticated) return;
    if (generated.channel !== channel) {
      notify("用途已切换，请返回对应草稿再应用。");
      return;
    }
    setDrafts((old) => ({
      ...old,
      [channel]: {
        ...old[channel],
        content: generated.content,
        version: old[channel].version + 1,
        confirmedFingerprint: undefined,
      },
    }));
    setGenerated(null);
  };
  const copy = async () => {
    try {
      await service.copy(draft.content);
      notify("文字已复制，尚未发送。", "success");
    } catch (error) {
      notify(errorMessage(error), "error");
    }
  };
  const closeConfirm = () =>
    navigate(
      "/outreach?opportunity=" +
        encodeURIComponent(row.id) +
        "&channel=" +
        channel,
    );
  return (
    <>
      <section className="contact-editor r4-contact-editor">
        <div className="section-heading">
          <h2>联系草稿</h2>
          <Badge tone={sample ? "orange" : "neutral"}>
            {sample
              ? "公开研究样例 · 只读"
              : dirty
                ? "本机修改未同步"
                : "已保存内容"}
          </Badge>
        </div>
        <Tabs
          active={channel}
          onChange={(value) => setChannel(value as "comment" | "dm")}
          items={[
            { key: "comment", label: "评论草稿" },
            { key: "dm", label: "私信草稿" },
          ]}
        />
        {!sample && otherDirty && (
          <p className="muted text-small" role="status">
            {otherChannel === "comment" ? "评论" : "私信"}草稿仍有未保存修改；切换用途不会保存或放弃内容。
          </p>
        )}
        <Field label="沟通目的">
          <select
            aria-label="沟通目的"
            value={purposes[channel]}
            disabled={sample || !session.authenticated}
            onChange={(event) =>
              setPurposes((old) => ({
                ...old,
                [channel]: event.target.value as CoachPurpose,
              }))
            }
          >
            {Object.entries(COACH_PURPOSES).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </Field>
        <div className="section-heading">
          <h3>沟通内容</h3>
          <Button
            variant="ghost"
            disabled={sample || !session.authenticated || action.busy}
            onClick={() =>
              draft.content && !generationFailed
                ? setPendingRegenerate(true)
                : void generate()
            }
          >
            {generationFailed
              ? "重试生成"
              : draft.content.trim()
                ? "重新生成"
                : "生成联系草稿"}
          </Button>
        </div>
        <textarea
          className="contact-content"
          aria-label="沟通内容"
          value={draft.content}
          readOnly={sample}
          onChange={(e) => edit({ content: e.target.value })}
          rows={6}
          placeholder={
            sample ? "此用途尚无样例草稿" : "填写联系内容，或根据商机生成草稿"
          }
        />
        <p className="character-count">{Array.from(draft.content).length} 字</p>
        {action.error && <Notice tone="error">{action.error}</Notice>}
        <ContactMaterialQuotes key={JSON.stringify([session.userId,session.accountScope,row.id,row.profileVersionId,channel])}
          row={row} draft={draft} onChange={edit} disabled={sample||!session.authenticated||saving.busy||saving.blocked}/>
        <ShortCoachPanel
          row={row}
          draft={draft}
          purpose={purposes[channel]}
          onApply={(content, materialReferences) => edit({ content, materialReferences })}
        />
        {!sample && (
          <details className="contact-routing">
            <summary>
              发送配置
              <span>
                {draft.recipient.trim() ? "对象已填写" : "对象未填写"} ·{" "}
                {connection ? "账号已选择" : "账号未选择"}
              </span>
            </summary>
            <div className="contact-routing-fields">
              <Field
                label="收件对象"
                hint="对象须经渠道映射核验，手填名称不能作为身份依据。"
              >
                <input
                  aria-label="收件对象"
                  value={draft.recipient}
                  disabled={sample}
                  onChange={(e) => edit({ recipient: e.target.value })}
                  placeholder="核对原文后填写"
                />
              </Field>
              <Field label="选择已连接渠道">
                <select
                  aria-label="发送账号"
                  value={draft.accountId}
                  disabled={sample || connections.loading}
                  onChange={(e) => edit({ accountId: e.target.value })}
                >
                  <option value="">未选择</option>
                  {available.map((c) => (
                    <option
                      key={`${c.platform}:${c.accountId}`}
                      value={c.accountId}
                    >
                      {c.accountName || c.accountId} · {c.platform}
                    </option>
                  ))}
                </select>
              </Field>
            </div>
            {connections.error && (
              <p className="field-hint">{connections.error}</p>
            )}
          </details>
        )}
        {saving.error && <Notice tone="error">{saving.error}</Notice>}
        {!sample && latest.loading && <p className="field-hint">正在读取已保存草稿…</p>}
        {!sample && latest.error && (
          <Notice tone="error">
            {latest.error}
            <Button onClick={latest.retry}>重新读取已保存草稿</Button>
          </Notice>
        )}
        {!sample && latest.candidate && (
          <Notice tone="warning">
            已读取到本人保存的草稿；本机已有编辑或来源版本已变化，当前内容未覆盖。
            <Button onClick={latest.adopt}>采用已保存草稿</Button>
          </Notice>
        )}
        {native && nativeRecord.record && route.query.get("confirm") !== "send" && <Notice tone="warning">
          {nativeRecord.record.state === "SENT" ? "此商机评论已确认发送，修改草稿不会解除首联保护。" : "原生发送结果待核对；原请求已保留，不能重复发送。"}
          <Button onClick={() => navigate("/outreach?opportunity=" + encodeURIComponent(row.id) + "&channel=" + channel + "&confirm=send")}>查看原发送记录</Button>
        </Notice>}
        {!!saving.pending.length && (
          <div className="draft-save-recovery">
            <Notice tone="warning">
              此用途的草稿保存结果待确认，当前文字仍保留，不能重复保存或发送。
            </Notice>
            <div className="inline-actions">
              {saving.pending.map((key) => (
                <Button
                  key={key}
                  loading={saving.busy}
                  onClick={() => void saving.reconcile(key)}
                >
                  核对原保存请求
                </Button>
              ))}
            </div>
          </div>
        )}
        <p className="muted text-small">
          {sample
            ? "公开样例仅供预览和复制，不能保存或发送。"
            : "编辑内容按当前账号保存在本机当前会话；同步成功前不会成为客户空间草稿。"}
        </p>
        <div className="action-row">
          <Button
            variant="primary"
            disabled={
              sample ||
              !session.authenticated ||
              !draft.content.trim() ||
              saving.blocked ||
              !latest.complete ||
              !!latest.candidate ||
              (persisted.known && !dirty) ||
              action.busy
            }
            loading={saving.busy}
            onClick={() => void saving.save(persisted.known ? persisted.previousRequestId : undefined)}
          >
            保存草稿
          </Button>
          <Button
            disabled={
              sample ||
              !session.authenticated ||
              !draft.content.trim() ||
              dirty ||
              saving.blocked ||
              !latest.complete ||
              !!latest.candidate ||
              saving.busy
            }
            onClick={() =>
              navigate(
                "/outreach?opportunity=" +
                  encodeURIComponent(row.id) +
                  "&channel=" +
                  channel +
                  "&confirm=send",
              )
            }
          >
            <PaperPlaneTilt />
            准备发送
          </Button>
          <Button
            variant={sample ? "primary" : "ghost"}
            disabled={!draft.content}
            onClick={() => void copy()}
            aria-label="复制联系草稿"
          >
            <Copy />
            {sample ? "复制样例文字" : null}
          </Button>
        </div>
      </section>
      <aside className="outreach-evidence">
        <div className="section-heading">
          <h2>原文依据</h2>
          <Button
            variant="ghost"
            onClick={() =>
              navigate("/opportunities/" + encodeURIComponent(row.id))
            }
          >
            查看详情
            <ArrowSquareOut />
          </Button>
        </div>
        <h3>{row.title}</h3>
        <Badge tone={sample ? "orange" : "blue"}>
          {sample ? "公开研究样例 · 待复核 · 未入客户库" : "客户商机"}
        </Badge>
        <dl className="detail-list">
          <div>
            <dt>发布单位</dt>
            <dd>{row.buyer || "—"}</dd>
          </div>
          <div>
            <dt>发布时间</dt>
            <dd>{formatDate(row.publishedAt)}</dd>
          </div>
          {sample && (
            <>
              <div>
                <dt>项目地点</dt>
                <dd>深圳国际会展中心</dd>
              </div>
              <div>
                <dt>展区面积</dt>
                <dd>180㎡</dd>
              </div>
              <div>
                <dt>资料截止</dt>
                <dd>09-15 18:00</dd>
              </div>
            </>
          )}
        </dl>
        <h3>{sample ? "公开样例摘录" : "旧版摘录（非固定原文）"}</h3>
        <blockquote className="coach-quote">
          {row.excerpt || "暂无原始摘录"}
        </blockquote>
        <details>
          <summary>查看完整判断</summary>
          <EvidencePanel opportunity={row} compact />
        </details>
        {!sample && <Notice>发送前需完成来源、画像、对象及账号的核验。</Notice>}
        <ContactNotes
          key={`${session.userId}:${row.id}:${row.profileVersionId}`}
          row={row}
        />
      </aside>
      {pendingRegenerate && (
        <Confirm
          title="重新生成联系草稿"
          onCancel={() => setPendingRegenerate(false)}
          onConfirm={() => void generate()}
          confirmText="生成新建议"
        >
          <p>当前内容会保留。生成后先预览新建议，由你决定是否替换。</p>
        </Confirm>
      )}
      {generated && (
        <Modal
          title="新草稿预览"
          onClose={() => setGenerated(null)}
          footer={
            <>
              <Button onClick={() => setGenerated(null)}>保留当前内容</Button>
              <Button
                variant="primary"
                disabled={generated.channel !== channel}
                onClick={applyGenerated}
              >
                替换当前草稿
              </Button>
            </>
          }
        >
          <p>替换会覆盖当前用途的文字，请先核对。</p>
          {generated.version !== draft.version && (
            <Notice tone="warning">
              生成期间你修改了草稿；当前编辑仍完整保留。
            </Notice>
          )}
          <pre className="draft-preview">{generated.content}</pre>
        </Modal>
      )}
      {route.query.get("confirm") === "send" &&
        (saving.blocked || saving.busy ? (
          <Notice tone="warning">请先核对草稿保存结果，再重新准备发送。</Notice>
        ) : (
          <Fragment key={savedEpoch}>
            {renderConfirmation({ draft, connection, onClose: closeConfirm })}
          </Fragment>
        ))}
    </>
  );
}
