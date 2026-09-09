import { useEffect, useMemo, useRef, useState } from "react";
import { Plus } from "@phosphor-icons/react";
import { useApp } from "../app/context";
import { useResource } from "../app/hooks";
import { boundedRequest } from "../app/boundedRequest";
import {
  Badge,
  Button,
  Empty,
  Field,
  Notice,
  PageHeader,
  ResourceStatus,
  Tabs,
  formatDate,
} from "../components/ui";
import {
  legacyRecord,
  readSnapshot,
  FOLLOWUP_LABELS,
  type FollowupRecord,
  type FollowupView,
} from "../domain/followup";
import type { Opportunity } from "../domain/models";
import { FollowupEditor } from "./followups/FollowupEditor";
import { RelatedReplies } from "./followups/RelatedReplies";
import { useFollowupOperation } from "./followups/useFollowupOperation";
import { isSample } from "./Opportunities";
import "./followups/followups.css";
function localDay(value: string) {
  const time = new Date(value);
  return `${time.getFullYear()}-${String(time.getMonth() + 1).padStart(2, "0")}-${String(time.getDate()).padStart(2, "0")}`;
}
export function FollowupsPage() {
  const { service, session } = useApp();
  const identity = useMemo(
    () => crypto.randomUUID(),
    [
      service,
      service.followup,
      session.authenticated,
      session.userId,
      session.accountScope?.id,
      session.accountScope?.version,
    ],
  );
  return <FollowupWorkspace key={identity} />;
}
function FollowupWorkspace() {
  const { service, session, route, navigate } = useApp();
  const [tab, setTab] = useState(() =>
    route.query.get("tab") === "replies" ? "replies" : "todo",
  );
  const [selected, setSelected] = useState("");
  const [owner, setOwner] = useState("");
  const [date, setDate] = useState("");
  const [correction, setCorrection] = useState<FollowupRecord>();
  const operation = useFollowupOperation();
  const target =
    route.query.get("add") === "1" ? "" : route.query.get("opportunity") || "";
  const intent = JSON.stringify([target, route.query.get("tab")]);
  const handledIntent = useRef("");
  const [focused, setFocused] = useState("");
  const [missingTarget, setMissingTarget] = useState(false);
  const resource = useResource(async () => {
    if (!session.authenticated)
      return {
        records: [] as FollowupView[],
        members: [] as { id: string; name: string }[],
      };
    if (service.followup)
      return readSnapshot(
        await boundedRequest(() => service.followup!.list(), {
          timeoutMessage: "跟进记录读取超时，请刷新重试。",
        }),
      );
    const records = await boundedRequest(() => service.followups(), {
      timeoutMessage: "跟进记录读取超时，请刷新重试。",
    });
    if (new Set(records.map((r) => r.id)).size !== records.length)
      throw new Error("服务返回重复登记，请刷新核对。");
    return {
      records: records.filter((r) => r.kind === "manual").map(legacyRecord),
      members: [],
    };
  }, [
    service,
    session.userId,
    session.authenticated,
    session.accountScope?.id,
    session.accountScope?.version,
  ]);
  const opportunities = useResource(
    () =>
      session.authenticated
        ? boundedRequest(() => service.opportunities(), {
            timeoutMessage: "商机读取超时，请重试。",
          })
        : Promise.resolve([] as Opportunity[]),
    [
      service,
      session.userId,
      session.authenticated,
      session.accountScope?.id,
      session.accountScope?.version,
    ],
  );
  const records: FollowupView[] = resource.data?.records || [];
  const members = resource.data?.members || [];
  useEffect(() => {
    if (resource.loading || resource.error || handledIntent.current === intent)
      return;
    handledIntent.current = intent;
    if (!target) {
      setFocused("");
      setMissingTarget(false);
      return;
    }
    const latest = records
      .filter(
        (r) => r.opportunityId === target && !r.sample && target !== "sample",
      )
      .sort((a, b) => Date.parse(b.createdAt) - Date.parse(a.createdAt))[0];
    setTab(route.query.get("tab") === "replies" ? "replies" : "todo");
    setOwner("");
    setDate("");
    setSelected(latest?.id || "");
    setFocused(latest?.id || "");
    setMissingTarget(!latest);
  }, [intent, resource.data, resource.loading, resource.error]);
  const localSelection = () => {
    setFocused("");
    setMissingTarget(false);
  };
  const visible = records
    .filter(
      (row) =>
        !row.sample &&
        row.opportunityId !== "sample" &&
        (!owner || row.ownerId === owner) &&
        (!date || localDay(row.occurredAt || row.createdAt) === date) &&
        (row.id === focused ||
          (tab === "all" || tab === "replies"
            ? tab !== "replies" || row.status === "REPLIED" || !!row.replyCount
            : !service.followup ||
              (!!row.nextFollowupAt &&
                row.state === "ACTIVE" &&
                !["LOST", "WON"].includes(row.status)))),
    )
    .sort(
      (a, b) =>
        Date.parse(b.occurredAt || b.createdAt) -
        Date.parse(a.occurredAt || a.createdAt),
    );
  const current = visible.find((r) => r.id === selected);
  const reload = () => {
    void resource.reload();
  };
  const saved = () => {
    setCorrection(undefined);
    navigate("/followups");
    reload();
  };
  const pending = Object.keys(operation.pending);
  return (
    <>
      <PageHeader title="跟进记录" />
      <Tabs
        active={tab}
        onChange={(value) => {
          localSelection();
          setTab(value);
        }}
        items={[
          { key: "todo", label: "待跟进" },
          { key: "replies", label: "回复记录" },
          { key: "all", label: "全部" },
        ]}
      />
      {missingTarget && (
        <Notice tone="warning">
          未找到目标商机的跟进记录，请核对商机是否已登记或仍可访问。
        </Notice>
      )}
      {focused && (
        <p className="muted text-small">已定位目标商机的最新登记。</p>
      )}
      {(operation.storageError || operation.historical.length > 0) && (
        <section className="followup-pending">
          <Notice tone="warning">
            {operation.storageError ||
              "旧跟进操作尚未绑定当前客户空间或版本，不能在此核对或重复保存。请返回原空间版本核对；归属未知时需由服务管理员核实。"}
          </Notice>
          {operation.historical.map((entry, index) => (
            <Field key={index} label={`待核对原请求 ${index + 1}`}>
              <input
                aria-label={`待核对原请求 ${index + 1}`}
                readOnly
                value={entry.binding.requestId}
              />
              <small>
                {entry.accountScope === "unbound"
                  ? "旧版本：客户空间归属未绑定"
                  : entry.accountScope
                    ? `原空间 ${entry.accountScope.id} · 版本 ${entry.accountScope.version}`
                    : "原会话未提供客户空间"}
              </small>
            </Field>
          ))}
          <Button onClick={operation.refresh}>重新读取操作记录</Button>
        </section>
      )}
      {pending.length > 0 && (
        <section className="followup-pending">
          <Notice tone="warning">
            有跟进操作结果待确认，请先核对原请求，避免重复登记。
          </Notice>
          {pending.map((key) => (
            <Button
              key={key}
              loading={operation.action.busy}
              onClick={() =>
                void operation.reconcile(key).then((result) => {
                  if (
                    operation.current() &&
                    ["SUCCEEDED", "FAILED"].includes(result || "")
                  )
                    reload();
                })
              }
            >
              核对原跟进操作
            </Button>
          ))}
          {operation.action.error && (
            <Notice tone="error">{operation.action.error}</Notice>
          )}
        </section>
      )}
      <div className="followup-layout">
        <section>
          <div className="filter-bar">
            <Field label="负责人">
              <select
                aria-label="筛选负责人"
                value={owner}
                onChange={(e) => {
                  localSelection();
                  setOwner(e.target.value);
                }}
              >
                <option value="">全部</option>
                {members.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="日期">
              <input
                aria-label="筛选记录日期"
                type="date"
                value={date}
                onChange={(e) => {
                  localSelection();
                  setDate(e.target.value);
                }}
              />
            </Field>
            <div className="followup-filter-actions">
              <Button onClick={reload} loading={resource.loading}>
                刷新
              </Button>
              <Button
                variant="primary"
                onClick={() => navigate("/followups?add=1")}
              >
                <Plus />
                添加跟进
              </Button>
            </div>
          </div>
          {!session.authenticated ? (
            <Empty
              title="登录后查看跟进记录"
              action={<Button onClick={() => navigate("/login")}>登录</Button>}
            />
          ) : (
            <>
              <ResourceStatus
                loading={resource.loading}
                error={resource.error}
                onRetry={reload}
              />
              {!resource.loading && !resource.error && (
                <>
                  {tab === "todo" && !service.followup && (
                    <p className="muted text-small">
                      结构化计划尚未接通，以下为已登记的人工跟进，不代表到期提醒。
                    </p>
                  )}
                  <div className="table-wrap">
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>商机</th>
                          <th>最近联系</th>
                          <th>客户回复</th>
                          <th>下次跟进</th>
                          <th>负责人</th>
                        </tr>
                      </thead>
                      <tbody>
                        {visible.map((row) => (
                          <tr
                            key={row.id}
                            className={selected === row.id ? "selected" : ""}
                          >
                            <td>
                              <Button
                                variant="ghost"
                                onClick={() => {
                                  localSelection();
                                  setSelected(row.id);
                                }}
                              >
                                {row.title || "查看关联商机"}
                              </Button>
                              <small>
                                {FOLLOWUP_LABELS[row.status]}
                                {row.state !== "ACTIVE"
                                  ? ` · ${row.state === "VOID" ? "已撤销" : "已纠正"}`
                                  : ""}
                              </small>
                            </td>
                            <td>
                              {row.occurredAt ? (
                                formatDate(row.occurredAt)
                              ) : (
                                <>
                                  <span>未填写</span>
                                  <small>
                                    登记 {formatDate(row.createdAt)}
                                  </small>
                                </>
                              )}
                            </td>
                            <td>
                              {row.replyCount !== undefined
                                ? `${row.replyCount} 条通道回复`
                                : row.status === "REPLIED"
                                  ? "人工登记已回复"
                                  : "—"}
                            </td>
                            <td>
                              {row.nextFollowupAt ? (
                                <>
                                  {formatDate(row.nextFollowupAt)}
                                  {Date.parse(row.nextFollowupAt) <
                                    Date.now() &&
                                    row.state === "ACTIVE" && (
                                      <Badge tone="orange">已到期</Badge>
                                    )}
                                </>
                              ) : (
                                "—"
                              )}
                            </td>
                            <td>{row.ownerName || "未提供"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {!visible.length && (
                      <Empty
                        title={
                          owner || date ? "没有符合筛选的记录" : "暂无跟进记录"
                        }
                        description="联系后记录下一步，避免遗漏。"
                      />
                    )}
                  </div>
                </>
              )}
            </>
          )}
        </section>
        <RelatedReplies
          key={session.userId || "public"}
          current={current}
          records={records}
          onCorrect={setCorrection}
          onChanged={reload}
        />
      </div>
      {(route.query.get("add") === "1" || correction) && (
        <FollowupEditor
          key={`${session.userId}:${correction?.id || route.query.get("opportunity") || "new"}`}
          rows={(opportunities.data || []).filter((row) => !isSample(row))}
          members={members}
          correction={correction}
          loading={
            opportunities.loading || (!!service.followup && resource.loading)
          }
          error={
            opportunities.error || (service.followup && resource.error) || ""
          }
          onRetry={() => {
            void opportunities.reload();
            reload();
          }}
          onClose={() => {
            setCorrection(undefined);
            if (route.query.get("add") === "1") navigate("/followups");
          }}
          onSaved={saved}
        />
      )}
    </>
  );
}
