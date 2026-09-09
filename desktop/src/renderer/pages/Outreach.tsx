import { useEffect, useRef, useState } from "react";
import {
  ArrowSquareOut,
  Copy,
  MagnifyingGlass,
  PaperPlaneTilt,
} from "@phosphor-icons/react";
import { useApp } from "../app/context";
import {
  useAction,
  useLocalDraft,
  useResource,
  useUnsavedChanges,
} from "../app/hooks";
import { useOperationLedger } from "../app/operationLedger";
import { boundedRequest } from "../app/boundedRequest";
import {
  Badge,
  Button,
  Confirm,
  Empty,
  Field,
  Modal,
  Notice,
  PageHeader,
  ResourceStatus,
  Tabs,
  formatDate,
} from "../components/ui";
import type {
  ContactDraft,
  Opportunity,
  PlatformConnection,
  ContactVerification,
} from "../domain/models";
import { errorMessage } from "../services/contracts";
import {
  parseSendReceipt,
  pendingSend,
  type OutreachQueue as Queue,
  type SendRequestBinding,
} from "../domain/outreach";
import { requireOutreach } from "../services/outreach";
import { OutreachQueue } from "./OutreachQueue";
import { ContactNotes } from "./outreach/ContactNotes";
import { sortContactRows, type ContactSort } from "../domain/contactList";
import { EvidencePanel, PUBLIC_SAMPLE, isSample } from "./Opportunities";

export function contactFingerprint(
  draft: ContactDraft,
  opportunity: Opportunity,
  connection?: PlatformConnection,
): string {
  return JSON.stringify([
    opportunity.id,
    opportunity.profileVersionId,
    opportunity.profileStatus,
    opportunity.sourceStatus,
    isSample(opportunity),
    draft.channel,
    draft.version,
    draft.content,
    draft.savedContent,
    draft.accountId,
    draft.recipient,
    connection?.status || "",
    connection?.accountId || "",
    connection?.capabilities || [],
  ]);
}
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

export function OutreachPage() {
  const { session } = useApp();
  return <OutreachWorkspace key={session.userId || "public"} />;
}
function OutreachWorkspace() {
  const { service, session, route, navigate } = useApp();
  const id = route.query.get("opportunity");
  const list = useResource(
    () =>
      session.authenticated
        ? service.opportunities()
        : Promise.resolve([] as Opportunity[]),
    [service, session.userId, session.authenticated],
  );
  const detail = useResource(
    () =>
      id === "sample"
        ? Promise.resolve(PUBLIC_SAMPLE)
        : id && session.authenticated
          ? service.opportunity(id).then((row) => {
              if (!row || row.id !== id || isSample(row))
                throw new Error("商机返回记录与当前选择不匹配，请刷新重试。");
              return row;
            })
          : Promise.resolve(undefined),
    [service, id, session.userId, session.authenticated],
  );
  const [listView, setListView] = useLocalDraft<{
    query: string;
    sort: ContactSort;
  }>(
    `contact-list:${session.userId || "public"}`,
    { query: "", sort: "newest" },
    (value) =>
      !!value &&
      typeof value === "object" &&
      typeof (value as { query?: unknown }).query === "string" &&
      ["newest", "oldest", "title"].includes((value as { sort: string }).sort),
  );
  const query = listView.query;
  const [queue, setQueue] = useState("draft");
  const rows = sortContactRows(
    (list.data || []).filter(
      (r) =>
        !isSample(r) &&
        [r.title, r.buyer, r.platform, r.url]
          .join(" ")
          .toLowerCase()
          .includes(query.trim().toLowerCase()),
    ),
    listView.sort,
  );
  const selected = detail.data;
  return (
    <>
      <PageHeader
        title="触达中心"
        description="基于公开信息，准备沟通内容，跟进商机进展。"
      />
      <Tabs
        active={queue}
        onChange={setQueue}
        items={[
          { key: "draft", label: "草稿箱" },
          { key: "confirm", label: "待确认" },
          { key: "reply", label: "待回复" },
          { key: "issues", label: "需处理" },
        ]}
      />
      {queue !== "draft" ? (
        <OutreachQueue
          key={`${session.userId}:${queue}`}
          queue={queue as Queue}
          onOpen={(path) => {
            setQueue("draft");
            navigate(path);
          }}
        />
      ) : (
        <div className="outreach-layout">
          <aside className="draft-list">
            <div className="search-input">
              <MagnifyingGlass />
              <input
                aria-label="搜索联系准备"
                value={query}
                onChange={(e) =>
                  setListView((old) => ({ ...old, query: e.target.value }))
                }
                placeholder="搜索商机标题或来源"
              />
            </div>
            <select
              className="contact-sort"
              aria-label="联系准备排序"
              value={listView.sort}
              onChange={(event) =>
                setListView((old) => ({
                  ...old,
                  sort: event.target.value as ContactSort,
                }))
              }
            >
              <option value="newest">按更新时间 · 最新优先</option>
              <option value="oldest">按更新时间 · 最早优先</option>
              <option value="title">按商机标题</option>
            </select>
            {session.authenticated && (
              <ResourceStatus
                loading={list.loading}
                error={list.error}
                onRetry={list.reload}
              />
            )}
            {rows.map((row) => (
              <button
                className={`list-item ${id === row.id ? "selected" : ""}`}
                key={row.id}
                onClick={() =>
                  navigate(
                    "/outreach?opportunity=" + encodeURIComponent(row.id),
                  )
                }
              >
                <strong>{row.title}</strong>
                <span>{row.buyer}</span>
                <small>
                  {row.comment || row.dm ? "已有联系草稿" : "待准备内容"}
                </small>
                <small>更新于 {formatDate(row.updatedAt)}</small>
              </button>
            ))}
            {!list.loading &&
              !list.error &&
              session.authenticated &&
              !rows.length && <p className="muted">暂无可联系的客户商机</p>}
            {!session.authenticated && (
              <Button onClick={() => navigate("/login")}>登录客户空间</Button>
            )}
            <div className="sample-list-section">
              <span className="muted">公开研究样例</span>
              <button
                className={`list-item ${id === "sample" ? "selected" : ""}`}
                onClick={() => navigate("/outreach?opportunity=sample")}
              >
                <strong>高交会预算询价 · 联系准备</strong>
                <span>湖南省商务厅官网</span>
                <Badge tone="orange">公开样例 · 只读</Badge>
              </button>
            </div>
          </aside>
          {!id ? (
            <Empty
              title="选择一条商机"
              description="查看证据并准备联系内容。"
            />
          ) : id !== "sample" && !session.authenticated ? (
            <Empty title="登录后准备客户联系内容" />
          ) : detail.loading || detail.error ? (
            <ResourceStatus
              loading={detail.loading}
              error={detail.error}
              onRetry={detail.reload}
            />
          ) : selected ? (
            <ContactEditor
              key={`${session.userId || "public"}:${selected.id}:${route.query.get("channel") === "dm" ? "dm" : "comment"}`}
              row={selected}
            />
          ) : (
            <Empty title="商机暂不可访问" />
          )}
        </div>
      )}
    </>
  );
}

function ContactEditor({ row }: { row: Opportunity }) {
  const { service, session, route, navigate, notify } = useApp();
  const sample = isSample(row);
  const [channel, setChannel] = useState<"comment" | "dm">(() =>
    route.query.get("channel") === "dm" ? "dm" : "comment",
  );
  const [drafts, setDrafts] = useLocalDraft<DraftSet>(
    `contact:${session.userId || "public"}:${row.id}`,
    () => ({
      comment: initialDraft(row, "comment"),
      dm: initialDraft(row, "dm"),
    }),
  );
  const draft = sample ? initialDraft(row, channel) : drafts[channel];
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
      c.capabilities.some((v) =>
        ["send", channel, "send_" + channel].includes(v),
      ),
  );
  const connection = available.find((c) => c.accountId === draft.accountId);
  const dirty = draft.content !== draft.savedContent;
  useUnsavedChanges(!sample && dirty);
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
  const save = async () => {
    if (sample || !session.authenticated || !draft.content.trim()) return;
    const submitted = { ...draft };
    await action.run(async () => {
      await service.saveContact(submitted);
      setDrafts((old) => {
        const current = old[submitted.channel];
        return {
          ...old,
          [submitted.channel]: { ...current, savedContent: submitted.content },
        };
      });
      notify("草稿已保存到客户空间。", "success");
    });
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
      <section className="contact-editor">
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
              <option key={`${c.platform}:${c.accountId}`} value={c.accountId}>
                {c.accountName || c.accountId} · {c.platform}
              </option>
            ))}
          </select>
        </Field>
        {!sample && connections.error && (
          <p className="field-hint">{connections.error}</p>
        )}
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
          rows={10}
          placeholder={
            sample ? "此用途尚无样例草稿" : "填写联系内容，或根据商机生成草稿"
          }
        />
        <p className="character-count">{Array.from(draft.content).length} 字</p>
        {action.error && <Notice tone="error">{action.error}</Notice>}
        <p className="muted text-small">
          {sample
            ? "公开样例仅供预览和复制，不能保存或发送。"
            : "编辑内容按当前账号保存在本机当前会话；同步成功前不会成为客户空间草稿。"}
        </p>
        <div className="action-row">
          <Button
            variant="primary"
            disabled={sample || !session.authenticated || !draft.content.trim()}
            loading={action.busy}
            onClick={() => void save()}
          >
            保存草稿
          </Button>
          <Button
            disabled={
              sample || !session.authenticated || !draft.content.trim() || dirty
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
          <h2>相关商机</h2>
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
        <EvidencePanel opportunity={row} compact />
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
      {route.query.get("confirm") === "send" && (
        <SendConfirmation
          row={row}
          draft={draft}
          connection={connection}
          onClose={closeConfirm}
        />
      )}
    </>
  );
}

export function SendConfirmation({
  row,
  draft,
  connection,
  onClose,
}: {
  row: Opportunity;
  draft: ContactDraft;
  connection?: PlatformConnection;
  onClose: () => void;
}) {
  const { service, session, notify } = useApp();
  const fingerprint = contactFingerprint(draft, row, connection);
  const [snapshot] = useState(() => ({ draft: { ...draft }, fingerprint }));
  const [checked, setChecked] = useState(false);
  const [proof, setProof] = useState<ContactVerification | null>(null);
  const [expired, setExpired] = useState(false);
  const verify = useAction();
  const sending = useAction();
  const reconciliation = useAction();
  const mounted = useRef(true);
  const [attempts, setAttempts] = useOperationLedger(
    "send-attempts",
    session.userId,
  );
  const attemptKey = JSON.stringify([row.id, draft.channel]);
  const sentKey = JSON.stringify([row.id, draft.channel, draft.version]);
  const pending = pendingSend(attempts, row.id, draft.channel);
  const attempted = pending
    ? "PENDING"
    : attempts[attemptKey] || attempts[sentKey];
  const changed = snapshot.fingerprint !== fingerprint;
  const sample = isSample(row);
  const prerequisites = sample
    ? "公开样例未入客户库，当前不可发送。"
    : !session.authenticated
      ? "请先登录客户空间。"
      : changed
        ? "内容或连接已变化，请返回重新确认。"
        : draft.content !== draft.savedContent
          ? "请先保存当前完整草稿。"
          : !draft.content.trim()
            ? "发送内容不能为空。"
            : row.profileStatus !== "CONFIRMED" || row.sourceStatus !== "OPEN"
              ? "画像或来源尚未完成核验。"
              : draft.opportunityId !== row.id
                ? "草稿与当前商机不匹配，请返回重新选择。"
                : !connection ||
                    connection.status !== "CONNECTED" ||
                    !draft.accountId ||
                    connection.accountId !== draft.accountId ||
                    !connection.capabilities.some((value) =>
                      ["send", draft.channel, "send_" + draft.channel].includes(
                        value,
                      ),
                    )
                  ? "请先连接并选择有效发送账号。"
                  : "";
  const liveState = useRef({
    fingerprint,
    prerequisites,
    userId: session.userId,
  });
  liveState.current = { fingerprint, prerequisites, userId: session.userId };
  const proofMatches = (value: ContactVerification) =>
    value.allowed &&
    value.fingerprint === fingerprint &&
    value.opportunityId === row.id &&
    value.accountId === draft.accountId &&
    value.channel === draft.channel &&
    !!value.recipientId &&
    !!value.recipientLabel &&
    !!value.confirmationToken &&
    Date.parse(value.expiresAt) > Date.now();
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  useEffect(() => {
    if (!proof) return;
    const delay = Date.parse(proof.expiresAt) - Date.now();
    if (!Number.isFinite(delay) || delay <= 0) {
      setExpired(true);
      return;
    }
    const timeout = window.setTimeout(
      () => {
        setExpired(true);
        setChecked(false);
      },
      Math.min(delay, 2_147_483_647),
    );
    return () => window.clearTimeout(timeout);
  }, [proof]);
  const inspect = async () => {
    if (prerequisites || attempted) return;
    setChecked(false);
    setProof(null);
    setExpired(false);
    await verify.run(async () => {
      const value = await boundedRequest(
        () => service.verifyContact(snapshot.draft, snapshot.fingerprint),
        { timeoutMessage: "发送条件核验超时，尚未发送，请重新核验。" },
      );
      if (!mounted.current) return;
      if (
        liveState.current.fingerprint !== snapshot.fingerprint ||
        liveState.current.prerequisites ||
        liveState.current.userId !== session.userId
      )
        throw new Error("核验期间内容或身份已变化，请返回重新确认。");
      if (!proofMatches(value))
        throw new Error(
          value.reason || "对象、账号或草稿核验未通过，请重新核对。",
        );
      setProof(value);
    });
  };
  const send = async () => {
    if (
      prerequisites ||
      attempted ||
      !checked ||
      !proof ||
      expired ||
      !proofMatches(proof)
    )
      return;
    await sending.run(async () => {
      const fresh = await boundedRequest(
        () => service.verifyContact(snapshot.draft, snapshot.fingerprint),
        { timeoutMessage: "发送条件核验超时，尚未发送，请重新核验。" },
      );
      if (!mounted.current) return;
      if (
        liveState.current.fingerprint !== snapshot.fingerprint ||
        liveState.current.prerequisites ||
        liveState.current.userId !== session.userId
      ) {
        setChecked(false);
        setProof(null);
        throw new Error("核验期间内容或身份已变化，尚未发送。");
      }
      if (
        !proofMatches(fresh) ||
        fresh.recipientId !== proof.recipientId ||
        fresh.recipientLabel !== proof.recipientLabel
      ) {
        setChecked(false);
        setProof(null);
        throw new Error("发送对象或条件已变化，请重新核验并确认。");
      }
      const binding: SendRequestBinding | undefined = service.outreach
        ? {
            requestId: crypto.randomUUID(),
            opportunityId: row.id,
            channel: snapshot.draft.channel,
            version: snapshot.draft.version,
          }
        : undefined;
      const operationKey = binding
        ? JSON.stringify([
            binding.opportunityId,
            binding.channel,
            binding.version,
            binding.requestId,
          ])
        : attemptKey;
      setAttempts((old) => {
        // Verification awaited a service response. Another window/request may
        // have settled or started meanwhile; recheck the freshest durable map
        // inside the updater before reserving this attempt and dispatching.
        if (
          pendingSend(old, row.id, snapshot.draft.channel) ||
          old[attemptKey] ||
          old[sentKey] === "SENT"
        )
          throw new Error(
            "核验期间发现已有发送记录，请先核对原请求，当前未重复发送。",
          );
        return { ...old, [operationKey]: "PENDING" };
      });
      let result;
      try {
        result = binding
          ? parseSendReceipt(
              await boundedRequest(
                () =>
                  requireOutreach(service.outreach).send(snapshot.draft, {
                    requestId: binding.requestId,
                    confirmationToken: fresh.confirmationToken,
                  }),
                {
                  timeoutMessage:
                    "发送等待超时，结果尚未确定，请核对原发送结果。",
                },
              ),
              binding,
            )
          : await boundedRequest(
              () => service.send(snapshot.draft, fresh.confirmationToken),
              {
                timeoutMessage: "发送等待超时，结果尚未确定，请核对平台记录。",
              },
            );
      } catch (error) {
        const code =
          error && typeof error === "object" && "code" in error
            ? String(error.code)
            : "";
        if (
          !binding &&
          [
            "CAPABILITY_UNAVAILABLE",
            "INVALID_REQUEST",
            "FORBIDDEN",
            "UNAUTHORIZED",
            "VALIDATION_ERROR",
          ].includes(code)
        )
          setAttempts((old) => {
            const next = { ...old };
            delete next[operationKey];
            return next;
          });
        throw error;
      }
      const status = result.status.toUpperCase();
      const confirmedFailure = !!binding && status === "FAILED";
      setAttempts((old) => {
        if (status !== "SENT" && !confirmedFailure) return old;
        const next = { ...old };
        if (status === "SENT") next[sentKey] = "SENT";
        delete next[operationKey];
        return next;
      });
      if (!mounted.current || liveState.current.userId !== session.userId)
        return;
      if (confirmedFailure) {
        setProof(null);
        setChecked(false);
      }
      notify(
        status === "SENT"
          ? "渠道已确认发送成功。"
          : confirmedFailure
            ? "渠道已确认未送达，请重新核验后再决定是否发送。"
            : "发送请求已提交，结果尚待渠道确认。",
        status === "SENT" ? "success" : "info",
      );
    });
  };
  const reconcile = async () => {
    if (
      sample ||
      !session.authenticated ||
      !pending?.binding ||
      reconciliation.busy ||
      sending.busy
    )
      return;
    const original = pending.binding;
    const originalKey = pending.key;
    await reconciliation.run(async () => {
      const receipt = parseSendReceipt(
        await boundedRequest(
          () => requireOutreach(service.outreach).reconcile(original),
          { timeoutMessage: "原请求核对超时，发送保护继续保留。" },
        ),
        original,
      );
      // A confirmed outcome settles the captured user's original operation, even
      // after navigation. Missing/unknown/invalid receipts cannot remove its lock.
      if (receipt.status === "SENT" || receipt.status === "FAILED")
        setAttempts((old) => {
          const next = { ...old };
          if (receipt.status === "SENT")
            next[
              JSON.stringify([
                original.opportunityId,
                original.channel,
                original.version,
              ])
            ] = "SENT";
          delete next[originalKey];
          return next;
        });
      if (!mounted.current || liveState.current.userId !== session.userId)
        return;
      setProof(null);
      setChecked(false);
      notify(
        receipt.status === "SENT"
          ? "原请求已确认发送成功，不会重复发送。"
          : receipt.status === "FAILED"
            ? "原请求已确认未送达；请重新核验并确认后发送。"
            : "原请求结果仍未确定，发送保护继续保留。",
        receipt.status === "SENT" ? "success" : "info",
      );
    });
  };
  const reason =
    prerequisites ||
    (attempted === "SENT"
      ? "此版本内容已发送，不能重复发送。"
      : attempted
        ? "此版本发送结果尚待确认，请核对平台记录，避免重复发送。"
        : expired
          ? "核验结果已过期，请重新核验。"
          : !proof
            ? "发送前需核验渠道对象、账号与草稿版本。"
            : "");
  return (
    <Modal
      title="确认发送"
      onClose={() => {
        if (!sending.busy && !reconciliation.busy) onClose();
      }}
      footer={
        <>
          <Button
            disabled={sending.busy || reconciliation.busy}
            onClick={onClose}
          >
            返回修改
          </Button>
          <Button
            variant="primary"
            loading={sending.busy}
            disabled={
              !!reason || !checked || verify.busy || reconciliation.busy
            }
            onClick={() => void send()}
          >
            确认并发送
          </Button>
        </>
      }
    >
      <p className="muted">核对发送信息。</p>
      <dl className="detail-list">
        <div>
          <dt>渠道</dt>
          <dd>{snapshot.draft.channel === "comment" ? "评论" : "私信"}</dd>
        </div>
        <div>
          <dt>发送账号</dt>
          <dd>
            {connection?.accountName || snapshot.draft.accountId || "待确认"}
          </dd>
        </div>
        <div>
          <dt>收件对象</dt>
          <dd>
            {proof?.recipientLabel || snapshot.draft.recipient || "待核对"}
          </dd>
        </div>
        <div>
          <dt>关联来源</dt>
          <dd>
            {row.title}
            {sample ? "（公开研究样例）" : ""}
          </dd>
        </div>
      </dl>
      <h3>发送内容预览</h3>
      <pre className="draft-preview">
        {snapshot.draft.content || "尚无内容"}
      </pre>
      {!prerequisites && !attempted && (
        <Button
          loading={verify.busy}
          disabled={sending.busy}
          onClick={() => void inspect()}
        >
          {proof && !expired ? "重新核验对象" : "核验发送条件"}
        </Button>
      )}
      <label className="checkbox-label">
        <input
          type="checkbox"
          checked={checked && !changed}
          disabled={changed || sending.busy}
          onChange={(e) => setChecked(e.target.checked)}
        />
        我已核对联系对象、发送账号和内容
      </label>
      {reason && <Notice tone="warning">{reason}</Notice>}
      {pending && !sample && session.authenticated && (
        <>
          {pending.binding ? (
            <div>
              <p className="muted text-small">
                原请求编号：{pending.binding.requestId}
              </p>
              <Button
                loading={reconciliation.busy}
                disabled={sending.busy}
                onClick={() => void reconcile()}
              >
                核对原发送结果
              </Button>
            </div>
          ) : (
            <Notice>
              旧版本未记录可查询的请求编号，请联系服务管理员核对平台记录；当前不会重新发送。
            </Notice>
          )}
        </>
      )}
      {verify.error && <Notice tone="error">{verify.error}</Notice>}
      {sending.error && <Notice tone="error">{sending.error}</Notice>}
      {reconciliation.error && (
        <Notice tone="error">{reconciliation.error}</Notice>
      )}
    </Modal>
  );
}
