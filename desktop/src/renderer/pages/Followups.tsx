import { useMemo, useState } from "react";
import { Plus } from "@phosphor-icons/react";
import { useApp } from "../app/context";
import { useAction, useLocalDraft, useResource } from "../app/hooks";
import {
  Badge,
  Button,
  Drawer,
  Empty,
  Field,
  Notice,
  PageHeader,
  ResourceStatus,
  Tabs,
  formatDate,
} from "../components/ui";
import type { Followup, FollowupStatus, Opportunity } from "../domain/models";
import { isSample } from "./Opportunities";

const labels: Record<FollowupStatus, string> = {
  CONTACTED: "已联系",
  REPLIED: "已回复",
  MEETING: "已约谈",
  QUOTED: "已报价",
  LOST: "未成交",
  WON: "已成交",
};
export function FollowupsPage() {
  const { session } = useApp();
  return <FollowupWorkspace key={session.userId || "public"} />;
}
function FollowupWorkspace() {
  const { service, session, route, navigate } = useApp();
  const [tab, setTab] = useState("todo");
  const [replyTab, setReplyTab] = useState("platform");
  const [selected, setSelected] = useState<string>("");
  const [date, setDate] = useState("");
  const rows = useResource(
    () =>
      session.authenticated
        ? service.followups()
        : Promise.resolve([] as Followup[]),
    [service, session.userId, session.authenticated],
  );
  const opportunities = useResource(
    () =>
      session.authenticated
        ? service.opportunities()
        : Promise.resolve([] as Opportunity[]),
    [service, session.userId, session.authenticated],
  );
  const filtered = useMemo(
    () =>
      (rows.data || []).filter(
        (row) =>
          (tab !== "replies" || row.status === "REPLIED") &&
          (!date || row.createdAt.startsWith(date)),
      ),
    [rows.data, tab, date],
  );
  const current = filtered.find((row) => row.id === selected);
  const matching = (rows.data || []).filter(
    (row) =>
      current &&
      row.opportunityId === current.opportunityId &&
      row.kind === (replyTab === "platform" ? "platform" : "manual"),
  );
  const done = () => {
    navigate("/followups");
    void rows.reload();
  };
  return (
    <>
      <PageHeader title="跟进记录" />
      <Tabs
        active={tab}
        items={[
          { key: "todo", label: "待跟进" },
          { key: "replies", label: "回复记录" },
          { key: "all", label: "全部" },
        ]}
        onChange={setTab}
      />
      <div className="followup-layout">
        <section>
          <div className="filter-bar">
            <Field label="负责人">
              <select aria-label="筛选负责人" disabled>
                <option>当前成员</option>
              </select>
            </Field>
            <Field label="日期">
              <input
                aria-label="筛选记录日期"
                type="date"
                value={date}
                onChange={(e) => setDate(e.target.value)}
              />
            </Field>
            <Button
              variant="primary"
              onClick={() => navigate("/followups?add=1")}
            >
              <Plus />
              添加跟进
            </Button>
          </div>
          {!session.authenticated ? (
            <Empty
              title="登录后查看跟进记录"
              action={<Button onClick={() => navigate("/login")}>登录</Button>}
            />
          ) : (
            <>
              <ResourceStatus
                loading={rows.loading}
                error={rows.error}
                onRetry={rows.reload}
              />
              {!rows.loading && !rows.error && (
                <>
                  {tab === "todo" && (
                    <p className="muted text-small">
                      到期提醒尚未接通，以下为已登记的跟进记录。
                    </p>
                  )}
                  <div className="table-wrap">
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>商机</th>
                          <th>登记时间</th>
                          <th>事实类型</th>
                          <th>下次跟进</th>
                        </tr>
                      </thead>
                      <tbody>
                        {filtered.map((row) => (
                          <tr
                            key={row.id}
                            className={selected === row.id ? "selected" : ""}
                          >
                            <td>
                              <Button
                                variant="ghost"
                                onClick={() => setSelected(row.id)}
                              >
                                {row.title || "查看关联商机"}
                              </Button>
                            </td>
                            <td>{formatDate(row.createdAt)}</td>
                            <td>
                              <Badge>{labels[row.status] || row.status}</Badge>
                            </td>
                            <td>—</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {!filtered.length && (
                      <Empty
                        title="暂无跟进记录"
                        description="联系后记录下一步，避免遗漏。"
                      />
                    )}
                  </div>
                </>
              )}
            </>
          )}
        </section>
        <aside className="related-replies">
          <h2>关联回复</h2>
          <Tabs
            active={replyTab}
            items={[
              { key: "platform", label: "通道回复" },
              { key: "manual", label: "人工登记" },
            ]}
            onChange={setReplyTab}
          />
          {replyTab === "platform" ? (
            <Empty
              title="回复回流尚未接通"
              description="接通后展示真实渠道回复。"
            />
          ) : !current ? (
            <Empty title="选择一条跟进记录" />
          ) : matching.length ? (
            <div className="followup-timeline">
              {matching.map((row) => (
                <article key={row.id}>
                  <Badge>人工登记</Badge>
                  <h3>{labels[row.status]}</h3>
                  <p className="preserve-lines">{row.note}</p>
                  <small className="muted">{formatDate(row.createdAt)}</small>
                </article>
              ))}
            </div>
          ) : (
            <Empty title="暂无关联登记" />
          )}
        </aside>
      </div>
      {route.query.get("add") === "1" && (
        <FollowupEditor
          key={session.userId || "public"}
          rows={(opportunities.data || []).filter((row) => !isSample(row))}
          loading={opportunities.loading}
          error={opportunities.error}
          onRetry={opportunities.reload}
          onClose={() => navigate("/followups")}
          onSaved={done}
        />
      )}
    </>
  );
}
interface FollowupDraft {
  opportunityId: string;
  status: FollowupStatus | "";
  note: string;
  next: string;
}
function FollowupEditor({
  rows,
  loading,
  error,
  onRetry,
  onClose,
  onSaved,
}: {
  rows: Opportunity[];
  loading: boolean;
  error: string;
  onRetry: () => void;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { service, session, route, notify } = useApp();
  const action = useAction();
  const [validation, setValidation] = useState("");
  const [draft, setDraft, clear] = useLocalDraft<FollowupDraft>(
    `followup:${session.userId || "public"}`,
    () => ({
      opportunityId: route.query.get("opportunity") || "",
      status: "",
      note: "",
      next: "",
    }),
  );
  const submit = async () => {
    setValidation("");
    const row = rows.find((item) => item.id === draft.opportunityId);
    if (!session.authenticated) {
      setValidation("请先登录客户空间。");
      return;
    }
    if (!row || isSample(row) || !draft.status || !draft.note.trim()) {
      setValidation("请选择已入库商机、事实类型，并填写实际沟通内容。");
      return;
    }
    await action.run(async () => {
      await service.addFollowup(
        row.id,
        draft.status as FollowupStatus,
        draft.note.trim(),
      );
      clear();
      notify("跟进事实已保存。", "success");
      onSaved();
    });
  };
  const update = (change: Partial<FollowupDraft>) =>
    setDraft((old) => ({ ...old, ...change }));
  return (
    <Drawer
      title="添加跟进"
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose}>取消</Button>
          <Button
            variant="primary"
            loading={action.busy}
            disabled={!session.authenticated || loading || Boolean(error)}
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
      <Field label="关联商机" required>
        <select
          aria-label="关联商机"
          value={draft.opportunityId}
          disabled={!session.authenticated || loading}
          onChange={(e) => update({ opportunityId: e.target.value })}
        >
          <option value="">请选择已入库商机</option>
          {rows.map((row) => (
            <option key={row.id} value={row.id}>
              {row.title}
            </option>
          ))}
        </select>
      </Field>
      <Field label="跟进类型">
        <input aria-label="跟进类型" value="人工登记" readOnly />
      </Field>
      <Field label="事实类型" required>
        <div className="radio-group">
          {(
            ["CONTACTED", "REPLIED", "MEETING", "QUOTED"] as FollowupStatus[]
          ).map((status) => (
            <label key={status}>
              <input
                type="radio"
                name="followup-status"
                checked={draft.status === status}
                onChange={() => update({ status })}
              />
              {labels[status]}
            </label>
          ))}
        </div>
      </Field>
      <Field label="联系时间">
        <input type="datetime-local" aria-label="联系时间" disabled />
      </Field>
      <Field
        label="备注"
        required
        hint="联系时间与计划一并写入备注；暂不提供提醒。"
      >
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
        <textarea rows={2} disabled placeholder="在备注中记录下一步计划" />
      </Field>
      <Field label="下次跟进">
        <input type="date" aria-label="下次跟进" disabled />
      </Field>
      <Field label="负责人">
        <input value="当前成员" readOnly />
      </Field>
      <Notice>人工登记，与渠道回执分开；未保存内容暂存本机会话。</Notice>
      {(validation || action.error) && (
        <Notice tone="error">{validation || action.error}</Notice>
      )}
    </Drawer>
  );
}
