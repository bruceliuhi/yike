import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowSquareOut,
  Copy,
  DownloadSimple,
  MagnifyingGlass,
} from "@phosphor-icons/react";
import { useApp } from "../app/context";
import { useResource, useUnsavedChanges } from "../app/hooks";
import {
  Badge,
  Button,
  Confirm,
  Empty,
  Field,
  Modal,
  Notice,
  PageHeader,
  Pagination,
  ResourceStatus,
  Tabs,
  formatDate,
} from "../components/ui";
import type { Opportunity, Profile } from "../domain/models";
import { ServiceError, errorMessage } from "../services/contracts";
import {
  CANDIDATE_EVIDENCE_LABELS,
  CANDIDATE_STATUS_LABELS,
  EMPTY_CANDIDATE_EVIDENCE,
  assessmentMatches,
  completeCandidateEvidence,
  completedCandidateReview,
  reviewSnapshot,
  sameReviewSnapshot,
  type Candidate,
  type CandidateAssessment,
  type CandidateEvidence,
  type CandidatePage,
  type CandidateReceipt,
  type CandidateReview,
  type CandidateStatus,
} from "../domain/candidates";

// Source verified on 2026-09-09. This public inquiry is never a customer record.
export const PUBLIC_SAMPLE: Opportunity = {
  id: "sample",
  sample: true,
  title: "180㎡高交会展区设计搭建预算询价",
  buyer: "湖南省商务厅对外贸易发展处",
  summary: "180㎡展区，涵盖设计、搭建、维护、撤展和组展服务。",
  excerpt: "本次报价仅用于预算测算。",
  matchReason: "买方公开征询服务方案与成本；适配需结合地域、施工及组展能力。",
  actionSignal: "9月15日18:00前递交资料，可评估是否参与预算询价。",
  value: "适合提前了解需求；预算、合同和收入尚未确定。",
  risk: "预算金额未公开，需进一步核实。本次不确定供应商、不签合同，参与不带来后续招标优先资格。",
  contactPath: "以官方公告的采购咨询、资料递交要求为准。",
  url: "https://swt.hunan.gov.cn/swt/hnswt/85753/fdzdgknr/caizhengxinxi/zfcgh/202609/t20260908_44997689265690696.html",
  platform: "公开网站",
  sourceStatus: "UNVERIFIED",
  profileStatus: "UNBOUND",
  profileVersionId: "",
  reviewer: "",
  reviewedAt: "",
  publishedAt: "2026-09-08T16:54:00+08:00",
  updatedAt: "",
  intentStatus: "PENDING_REVIEW",
  comment:
    "您好，关注到本次高交会展区预算询价。请问展位技术资料及组展服务范围如何获取？我们会先核实自身能力，再按公告要求准备资料。理解此次仅用于预算编制，后续采购以正式公告为准。",
  dm: "",
};
export function isSample(row: Opportunity) {
  return row.sample === true || row.id === "sample";
}
export function opportunityStatus(row: Opportunity) {
  if (isSample(row)) return "待复核";
  return (
    (
      {
        NEW: "新商机",
        REVIEW: "待复核",
        READY: "可联系",
        CONTACTED: "已联系",
        CLOSED: "已关闭",
        REPLIED: "已回复",
        MEETING: "已约谈",
        QUOTED: "已报价",
        WON: "已成交",
        LOST: "已关闭",
        PENDING_REVIEW: "待复核",
      } as Record<string, string>
    )[row.intentStatus] ||
    row.intentStatus ||
    "状态待核验"
  );
}
export function customerCsv(rows: Opportunity[]) {
  const cell = (value: string) =>
    '"' +
    (/^[\s]*[=+\-@\t\r]/.test(value) ? "'" + value : value).replaceAll(
      '"',
      '""',
    ) +
    '"';
  const fields = [
    ["商机标题", "需求方", "来源平台", "状态", "来源链接", "原文摘录"],
    ...rows
      .filter((r) => !isSample(r))
      .map((r) => [
        r.title,
        r.buyer,
        r.platform,
        opportunityStatus(r),
        r.url,
        r.excerpt,
      ]),
  ];
  return "\uFEFF" + fields.map((row) => row.map(cell).join(",")).join("\r\n");
}
export function EvidencePanel({
  opportunity: row,
  compact = false,
}: {
  opportunity: Opportunity;
  compact?: boolean;
}) {
  const { service, notify } = useApp();
  const open = async () => {
    try {
      await service.openExternal(row.url);
    } catch (error) {
      notify(errorMessage(error), "error");
    }
  };
  return (
    <section className="evidence-panel">
      <div className="section-heading">
        <h2>{compact ? "原文证据" : "原文证据"}</h2>
        <Button variant="ghost" disabled={!row.url} onClick={() => void open()}>
          查看{compact ? "" : "官方"}原文 <ArrowSquareOut />
        </Button>
      </div>
      <blockquote className="evidence-quote">
        {row.excerpt || "尚未提供原始摘录"}
      </blockquote>
      <p className="muted source-meta">
        {isSample(row) ? "湖南省商务厅官网" : row.platform || "来源待核验"} ·
        发布于 {formatDate(row.publishedAt)}
      </p>
      {!compact && (
        <>
          <h3>需求概述</h3>
          <p>{row.summary || "尚未提供需求概述"}</p>
          <h3>证据评估</h3>
          <dl className="detail-list">
            <div>
              <dt>匹配依据</dt>
              <dd>{row.matchReason || "尚未复核"}</dd>
            </div>
            <div>
              <dt>行动信号</dt>
              <dd>{row.actionSignal || "尚未核实"}</dd>
            </div>
            <div>
              <dt>机会价值</dt>
              <dd>{row.value || "尚未判断"}</dd>
            </div>
          </dl>
          <Notice tone="warning">{row.risk || "风险与未知项尚未核实"}</Notice>
          <h3>联系渠道</h3>
          <p>{row.contactPath || "尚未核实联系渠道"}</p>
        </>
      )}
    </section>
  );
}

export function OpportunitiesPage() {
  const { session } = useApp();
  return <OpportunityList key={session.userId || "public"} />;
}
function OpportunityList() {
  const { service, session, route, navigate, notify } = useApp();
  const resource = useResource(
    () =>
      session.authenticated
        ? service.opportunities()
        : Promise.resolve([] as Opportunity[]),
    [service, session.userId, session.authenticated],
  );
  const scope = route.query.get("scope") === "sample" ? "sample" : "customer";
  const [query, setQuery] = useState(route.query.get("q") || "");
  const [platform, setPlatform] = useState(route.query.get("platform") || "");
  const [status, setStatus] = useState(route.query.get("status") || "");
  const [sort, setSort] = useState(route.query.get("sort") || "updated");
  const [page, setPage] = useState(Number(route.query.get("page")) || 1);
  const [selected, setSelected] = useState<string[]>([]);
  const customers = (resource.data || []).filter((r) => !isSample(r));
  const rows = scope === "sample" ? [PUBLIC_SAMPLE] : customers;
  const filtered = useMemo(
    () =>
      rows
        .filter(
          (r) =>
            (!query ||
              [r.title, r.buyer, r.excerpt]
                .join(" ")
                .toLowerCase()
                .includes(query.trim().toLowerCase())) &&
            (!platform || r.platform === platform) &&
            (!status || opportunityStatus(r) === status),
        )
        .sort((a, b) =>
          sort === "title"
            ? a.title.localeCompare(b.title, "zh-CN")
            : (Date.parse(b.updatedAt || b.publishedAt) || 0) -
              (Date.parse(a.updatedAt || a.publishedAt) || 0),
        ),
    [rows, query, platform, status, sort],
  );
  const visiblePage = Math.min(
    Math.max(1, page),
    Math.max(1, Math.ceil(filtered.length / 10)),
  );
  const visible = filtered.slice((visiblePage - 1) * 10, visiblePage * 10);
  const changeScope = (value: string) => {
    setSelected([]);
    setPage(1);
    setPlatform("");
    setStatus("");
    navigate("/opportunities" + (value === "sample" ? "?scope=sample" : ""));
  };
  const open = (row: Opportunity) => {
    const back = new URLSearchParams({
      scope,
      q: query,
      platform,
      status,
      sort,
      page: String(visiblePage),
    });
    navigate(
      `/opportunities/${encodeURIComponent(row.id)}?returnTo=${encodeURIComponent("/opportunities?" + back)}`,
    );
  };
  const exportRows = () => {
    if (
      !session.authenticated ||
      scope !== "customer" ||
      resource.loading ||
      resource.error
    )
      return;
    const chosen = customers.filter((r) => selected.includes(r.id));
    if (!chosen.length) return;
    const url = URL.createObjectURL(
      new Blob([customerCsv(chosen)], { type: "text/csv;charset=utf-8;" }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = "意客AI-客户商机.csv";
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    notify(`已导出 ${chosen.length} 条选中客户商机。`, "success");
  };
  return (
    <>
      <PageHeader
        title="商机库"
        description="汇集多渠道的商机信息，支持筛选、查看和跟进。"
      />
      <div className="filter-bar">
        <div className="search-input">
          <MagnifyingGlass />
          <input
            aria-label="搜索商机"
            placeholder="搜索需求、买方或关键词"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setPage(1);
            }}
          />
        </div>
        <Field label="平台">
          <select
            aria-label="筛选平台"
            value={platform}
            onChange={(e) => {
              setPlatform(e.target.value);
              setPage(1);
            }}
          >
            <option value="">全部</option>
            {[...new Set(rows.map((r) => r.platform))].map((p) => (
              <option key={p}>{p}</option>
            ))}
          </select>
        </Field>
        <Field label="状态">
          <select
            aria-label="筛选状态"
            value={status}
            onChange={(e) => {
              setStatus(e.target.value);
              setPage(1);
            }}
          >
            <option value="">全部</option>
            {[...new Set(rows.map(opportunityStatus))].map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
        </Field>
        <select
          aria-label="排序方式"
          value={sort}
          onChange={(e) => setSort(e.target.value)}
        >
          <option value="updated">最近更新</option>
          <option value="title">标题排序</option>
        </select>
      </div>
      <Tabs
        active={scope}
        items={[
          { key: "customer", label: "客户商机" },
          { key: "sample", label: "公开研究样例" },
        ]}
        onChange={changeScope}
      />
      {scope === "customer" && !session.authenticated ? (
        <Empty
          title="登录后查看客户商机"
          action={<Button onClick={() => navigate("/login")}>登录</Button>}
        />
      ) : (
        <>
          {scope === "customer" && (
            <ResourceStatus
              loading={resource.loading}
              error={resource.error}
              onRetry={resource.reload}
            />
          )}
          {(scope === "sample" || (!resource.loading && !resource.error)) && (
            <div className="table-wrap">
              <table className="data-table opportunity-table">
                <thead>
                  <tr>
                    <th>
                      <input
                        type="checkbox"
                        aria-label="选择本页客户商机"
                        disabled={scope === "sample" || !visible.length}
                        checked={
                          visible.length > 0 &&
                          scope === "customer" &&
                          visible.every((r) => selected.includes(r.id))
                        }
                        onChange={(e) =>
                          setSelected(
                            e.target.checked
                              ? [
                                  ...new Set([
                                    ...selected,
                                    ...visible.map((r) => r.id),
                                  ]),
                                ]
                              : selected.filter(
                                  (id) => !visible.some((r) => r.id === id),
                                ),
                          )
                        }
                      />
                    </th>
                    <th>商机标题</th>
                    <th>来源</th>
                    <th>阶段 / 状态</th>
                    <th>更新时间</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {visible.map((row) => (
                    <tr key={row.id}>
                      <td>
                        <input
                          type="checkbox"
                          aria-label={`选择${row.title}`}
                          disabled={isSample(row)}
                          checked={!isSample(row) && selected.includes(row.id)}
                          onChange={(e) =>
                            setSelected(
                              e.target.checked
                                ? [...selected, row.id]
                                : selected.filter((id) => id !== row.id),
                            )
                          }
                        />
                      </td>
                      <td>
                        <strong>{row.title}</strong>
                        {isSample(row) && (
                          <small className="muted">
                            公开研究样例 · 未入客户库
                          </small>
                        )}
                      </td>
                      <td>
                        {isSample(row)
                          ? "湖南省商务厅官网"
                          : row.platform || "—"}
                      </td>
                      <td>
                        <Badge tone={isSample(row) ? "orange" : "neutral"}>
                          {opportunityStatus(row)}
                        </Badge>
                      </td>
                      <td>{formatDate(row.updatedAt || row.publishedAt)}</td>
                      <td>
                        <Button variant="ghost" onClick={() => open(row)}>
                          查看证据
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!visible.length && (
                <Empty
                  title={
                    query || platform || status
                      ? "没有符合条件的商机"
                      : "暂无客户商机"
                  }
                  description="完成采集与人工复核后，商机会出现在这里。"
                />
              )}
            </div>
          )}
          <div className="table-footer">
            {scope === "sample" ? (
              <span className="muted">
                研究样例未绑定客户画像，不计入客户商机。
              </span>
            ) : (
              <span className="muted">
                已选{" "}
                {
                  selected.filter((id) => customers.some((r) => r.id === id))
                    .length
                }{" "}
                条
              </span>
            )}
            <Button
              disabled={
                scope === "sample" ||
                !selected.length ||
                resource.loading ||
                Boolean(resource.error) ||
                !session.authenticated
              }
              onClick={exportRows}
            >
              <DownloadSimple />
              导出所选客户商机
            </Button>
            <Pagination
              page={visiblePage}
              total={filtered.length}
              onChange={setPage}
            />
          </div>
        </>
      )}
    </>
  );
}

export function OpportunityDetailPage() {
  const { route, session } = useApp();
  let id = route.path.split("/").at(-1) || "";
  try {
    id = decodeURIComponent(id);
  } catch {
    /* An invalid identifier remains a service not-found result. */
  }
  return (
    <OpportunityDetail key={`${session.userId || "public"}:${id}`} id={id} />
  );
}
function OpportunityDetail({ id }: { id: string }) {
  const { service, session, route, navigate, notify } = useApp();
  const resource = useResource(
    () =>
      id === "sample"
        ? Promise.resolve(PUBLIC_SAMPLE)
        : service.opportunity(id),
    [id, service, session.userId],
  );
  const row = resource.data;
  const back = () => {
    const value = route.query.get("returnTo");
    navigate(value?.startsWith("/opportunities?") ? value : "/opportunities");
  };
  const copy = async () => {
    if (!row) return;
    try {
      await service.copy(row.comment || row.dm);
      notify("草稿已复制；尚未发送。", "success");
    } catch (error) {
      notify(errorMessage(error), "error");
    }
  };
  if (id !== "sample" && !session.authenticated)
    return (
      <Empty
        title="登录后查看客户商机"
        action={<Button onClick={() => navigate("/login")}>登录</Button>}
      />
    );
  if (resource.loading || resource.error || !row)
    return (
      <>
        <PageHeader title="机会详情" back={back} />
        <ResourceStatus
          loading={resource.loading}
          error={resource.error}
          onRetry={resource.reload}
        />
      </>
    );
  const sample = isSample(row);
  return (
    <>
      <PageHeader title={row.title} description={row.buyer} back={back} />
      <div className="inline-meta">
        <Badge tone={sample ? "orange" : "blue"}>
          {sample
            ? "公开研究样例 · 待人工复核 · 未入客户库"
            : opportunityStatus(row)}
        </Badge>
        {!sample && (
          <span className="muted">
            复核人 {row.reviewer || "未记录"} · {formatDate(row.reviewedAt)}
          </span>
        )}
      </div>
      <div className="fact-strip">
        {(sample
          ? [
              ["需求阶段", "预算编制市场询价"],
              ["项目地点", "深圳国际会展中心"],
              ["展区面积", "180㎡"],
              ["资料截止", "2026-09-15 18:00"],
            ]
          : [
              ["来源平台", row.platform],
              ["来源状态", row.sourceStatus],
              ["画像状态", row.profileStatus],
              ["发布时间", formatDate(row.publishedAt)],
            ]
        ).map(([label, value]) => (
          <div key={label}>
            <span>{label}</span>
            <strong>{value || "—"}</strong>
          </div>
        ))}
      </div>
      {!sample &&
        (row.sourceStatus !== "OPEN" || row.profileStatus !== "CONFIRMED") && (
          <Notice tone="warning">
            来源或画像需要重新核验，请先确认需求仍有效。
          </Notice>
        )}
      <div className="evidence-layout">
        <EvidencePanel opportunity={row} />
        <aside className="contact-panel">
          <h2>
            联系准备 <span className="muted text-small">待校对 · 尚未发送</span>
          </h2>
          <Field label="询问草稿">
            <textarea
              aria-label="询问草稿"
              rows={8}
              value={row.comment || row.dm || ""}
              readOnly
              placeholder="尚无联系草稿"
            />
          </Field>
          <div className="action-row">
            <Button
              disabled={!row.comment && !row.dm}
              onClick={() => void copy()}
            >
              <Copy />
              复制草稿
            </Button>
          </div>
          <p className="muted">按公告要求联系采购方</p>
          <hr />
          {sample ? (
            <>
              <h3>样例状态</h3>
              <p>仅供研究查看，尚未绑定客户画像。</p>
              <Button
                variant="ghost"
                onClick={() => navigate("/outreach?opportunity=sample")}
              >
                查看样例联系准备
              </Button>
            </>
          ) : (
            <div className="action-row">
              <Button
                variant="primary"
                onClick={() =>
                  navigate(
                    "/outreach?opportunity=" + encodeURIComponent(row.id),
                  )
                }
              >
                生成联系草稿
              </Button>
              <Button
                onClick={() =>
                  navigate(
                    "/followups?add=1&opportunity=" +
                      encodeURIComponent(row.id),
                  )
                }
              >
                添加跟进
              </Button>
            </div>
          )}
        </aside>
      </div>
    </>
  );
}

export function CandidatesPage() {
  const { session } = useApp();
  return <CandidateWorkbench key={session.userId || "public"} />;
}

interface CandidateEditor {
  profileId: string;
  assessment?: CandidateAssessment;
  evidence: CandidateEvidence;
  baseline: CandidateEvidence;
  pending?: CandidateReceipt;
}
type DecisionReview = Extract<
  CandidateReview,
  { action: "INCLUDE" | "EXCLUDE" }
>;
interface CandidateConfirmation {
  action: "INCLUDE" | "EXCLUDE";
  rows: Candidate[];
  reviews: DecisionReview[];
  acknowledged: boolean;
  reason: string;
}
const sampleCandidate: Candidate = {
  id: "sample",
  revision: 1,
  sample: true,
  status: "PENDING_REVIEW",
  title: PUBLIC_SAMPLE.title,
  buyer: PUBLIC_SAMPLE.buyer,
  platform: "公开网站",
  sourceLabel: "湖南省商务厅官网",
  sourceId: "public-sample",
  sourceVersionId: "public-sample-20260908",
  sourceStatus: "UNVERIFIED",
  url: PUBLIC_SAMPLE.url,
  excerpt: PUBLIC_SAMPLE.excerpt,
  summary: PUBLIC_SAMPLE.summary,
  publishedAt: PUBLIC_SAMPLE.publishedAt,
  collectedAt: "",
  location: "深圳国际会展中心",
  deadline: "2026-09-15T18:00:00+08:00",
  stage: "预算编制市场询价",
};
const candidateSample = (row: Candidate) => row.sample || row.id === "sample";
function candidateEditor(row: Candidate): CandidateEditor {
  const evidence = {
    ...(row.assessment?.evidence || EMPTY_CANDIDATE_EVIDENCE),
  };
  return {
    profileId: row.assessment?.profileId || "",
    assessment: row.assessment,
    evidence,
    baseline: { ...evidence },
    pending:
      row.lastReview &&
      ["PROCESSING", "UNKNOWN"].includes(row.lastReview.status)
        ? row.lastReview
        : undefined,
  };
}
async function candidateTimeout<T>(promise: Promise<T>): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    return await Promise.race([
      promise,
      new Promise<never>((_, reject) => {
        timer = setTimeout(
          () =>
            reject(
              new ServiceError(
                "REQUEST_TIMEOUT",
                "请求已超时，请核对结果后再继续。",
                408,
              ),
            ),
          20_000,
        );
      }),
    ]);
  } finally {
    if (timer) clearTimeout(timer);
  }
}
function uncertainReview(error: unknown): boolean {
  return !(
    error instanceof ServiceError &&
    ((error.status >= 400 && error.status < 500 && error.status !== 408) ||
      error.status === 501)
  );
}

function CandidateWorkbench() {
  const { service, session, route, navigate, notify } = useApp();
  const sample = route.query.get("scope") === "sample";
  const [query, setQuery] = useState("");
  const [platform, setPlatform] = useState("");
  const [status, setStatus] = useState<CandidateStatus | "">("PENDING_REVIEW");
  const [page, setPage] = useState(1);
  const [selectedId, setSelectedId] = useState("");
  const [checked, setChecked] = useState<string[]>([]);
  const [drafts, setDrafts] = useState<Record<string, CandidateEditor>>({});
  const draftsRef = useRef(drafts);
  draftsRef.current = drafts;
  const [busy, setBusy] = useState<string | null>(null);
  const lock = useRef(false);
  const live = useRef(true);
  const [error, setError] = useState("");
  const [outcome, setOutcome] = useState<{
    message: string;
    opportunityId?: string;
  } | null>(null);
  const [confirmation, setConfirmation] =
    useState<CandidateConfirmation | null>(null);
  const [replaceAssessment, setReplaceAssessment] = useState<{
    candidate: Candidate;
    profile: Profile;
  } | null>(null);
  const profiles = useResource(
    () =>
      session.authenticated && !sample
        ? service.profiles()
        : Promise.resolve([] as Profile[]),
    [service, session.userId, session.authenticated, sample],
  );
  const resource = useResource(
    () =>
      sample
        ? Promise.resolve<CandidatePage>({
            items: [sampleCandidate],
            total: 1,
            page: 1,
            pageSize: 10,
          })
        : session.authenticated
          ? service.candidates({
              query: query.trim(),
              platform: platform || undefined,
              status: status || undefined,
              page,
              pageSize: 10,
            })
          : Promise.resolve<CandidatePage>({
              items: [],
              total: 0,
              page: 1,
              pageSize: 10,
            }),
    [
      service,
      session.userId,
      session.authenticated,
      sample,
      query,
      platform,
      status,
      page,
    ],
  );
  const confirmedProfiles = (profiles.data || []).filter(
    (p) => p.status === "CONFIRMED",
  );
  const unsafeSample = !sample && resource.data?.items.some(candidateSample);
  const rows = unsafeSample ? [] : resource.data?.items || [];
  const selected = rows.find((row) => row.id === selectedId) || rows[0];
  const editor = selected
    ? drafts[selected.id] || candidateEditor(selected)
    : undefined;
  const selectedProfile = confirmedProfiles.find(
    (p) => p.id === editor?.profileId,
  );
  const dirty = Object.values(drafts).some(
    (draft) =>
      JSON.stringify(draft.evidence) !== JSON.stringify(draft.baseline) ||
      !!draft.pending,
  );
  useUnsavedChanges(dirty || !!busy);
  useEffect(() => {
    live.current = true;
    return () => {
      live.current = false;
    };
  }, []);
  useEffect(() => {
    setChecked([]);
    setSelectedId("");
  }, [query, platform, status, page, sample]);
  const updateDraft = (
    candidate: Candidate,
    update: (old: CandidateEditor) => CandidateEditor,
  ) =>
    setDrafts((old) => ({
      ...old,
      [candidate.id]: update(old[candidate.id] || candidateEditor(candidate)),
    }));
  const getDraft = (candidate: Candidate) =>
    draftsRef.current[candidate.id] || candidateEditor(candidate);
  const blockers = (
    candidate: Candidate,
    action: "INCLUDE" | "EXCLUDE",
  ): string[] => {
    const draft = getDraft(candidate);
    const profile = confirmedProfiles.find((p) => p.id === draft.profileId);
    const reasons: string[] = [];
    if (candidateSample(candidate)) reasons.push("公开样例不可修改或入库");
    if (candidate.status !== "PENDING_REVIEW") reasons.push("当前候选已处理");
    if (draft.pending) reasons.push("上次复核结果尚未核对");
    if (!profile) reasons.push("请绑定已确认画像");
    else if (
      !assessmentMatches(
        candidate,
        draft.assessment,
        profile.id,
        profile.version,
      ) ||
      !draft.assessment?.id
    )
      reasons.push("需要按当前画像和来源重新判断");
    if (!completeCandidateEvidence(draft.evidence))
      reasons.push("请补齐五项复核依据");
    if (
      !candidate.sourceId.trim() ||
      !candidate.sourceVersionId.trim() ||
      !candidate.excerpt.trim() ||
      !/^https?:\/\//i.test(candidate.url)
    )
      reasons.push("原始摘录或来源信息缺失");
    if (action === "INCLUDE" && candidate.sourceStatus !== "OPEN")
      reasons.push("来源尚未核实可访问");
    return reasons;
  };
  const assess = async (candidate: Candidate, profile: Profile) => {
    if (
      lock.current ||
      candidateSample(candidate) ||
      candidate.status !== "PENDING_REVIEW" ||
      getDraft(candidate).pending
    )
      return;
    lock.current = true;
    setBusy(candidate.id);
    setError("");
    updateDraft(candidate, (old) => ({ ...old, profileId: profile.id }));
    const request: CandidateReview = {
      action: "ASSESS",
      candidateId: candidate.id,
      candidateRevision: candidate.revision,
      sourceVersionId: candidate.sourceVersionId,
      profileId: profile.id,
      profileVersion: profile.version,
      requestId: crypto.randomUUID(),
    };
    try {
      const result = await candidateTimeout(service.reviewCandidate(request));
      if (!live.current) return;
      if (
        result.kind !== "assessment" ||
        result.requestId !== request.requestId ||
        result.candidateId !== candidate.id ||
        !result.assessment.id ||
        !assessmentMatches(
          candidate,
          result.assessment,
          profile.id,
          profile.version,
        )
      )
        throw new ServiceError(
          "STALE_ASSESSMENT",
          "判断结果与当前画像或来源不一致，请重新判断。",
          409,
        );
      updateDraft(candidate, (old) => ({
        ...old,
        profileId: profile.id,
        assessment: result.assessment,
        evidence: { ...result.assessment.evidence },
        baseline: { ...result.assessment.evidence },
      }));
    } catch (e) {
      if (live.current) setError(errorMessage(e));
    } finally {
      lock.current = false;
      if (live.current) setBusy(null);
    }
  };
  const requestAssessment = (candidate: Candidate, profile: Profile) => {
    const draft = getDraft(candidate);
    if (JSON.stringify(draft.evidence) !== JSON.stringify(draft.baseline))
      setReplaceAssessment({ candidate, profile });
    else void assess(candidate, profile);
  };
  const prepare = (candidates: Candidate[], action: "INCLUDE" | "EXCLUDE") => {
    setError("");
    if (!candidates.length) return;
    const invalid = candidates.find(
      (candidate) => blockers(candidate, action).length,
    );
    if (invalid) {
      setError(`${invalid.title}：${blockers(invalid, action).join("；")}。`);
      setSelectedId(invalid.id);
      return;
    }
    const reviews: DecisionReview[] = candidates.map((candidate) => {
      const draft = getDraft(candidate);
      const profile = confirmedProfiles.find((p) => p.id === draft.profileId)!;
      return {
        action,
        candidateId: candidate.id,
        candidateRevision: candidate.revision,
        sourceVersionId: candidate.sourceVersionId,
        profileId: profile.id,
        profileVersion: profile.version,
        requestId: crypto.randomUUID(),
        assessmentId: draft.assessment!.id,
        evidence: { ...draft.evidence },
        reason: "",
        humanConfirmed: true,
      };
    });
    setConfirmation({
      action,
      rows: candidates,
      reviews,
      acknowledged: false,
      reason: "",
    });
  };
  const applyDecision = (candidate: Candidate, receipt: CandidateReceipt) => {
    updateDraft(candidate, (old) => ({
      ...old,
      pending: undefined,
      baseline: { ...old.evidence },
    }));
    resource.setData((old) => {
      if (!old) return old;
      const remove = !!status && candidate.status !== status;
      return {
        ...old,
        items: remove
          ? old.items.filter((row) => row.id !== candidate.id)
          : old.items.map((row) => (row.id === candidate.id ? candidate : row)),
        total: Math.max(
          0,
          old.total -
            (remove && old.items.some((row) => row.id === candidate.id)
              ? 1
              : 0),
        ),
      };
    });
    setChecked((old) => old.filter((id) => id !== candidate.id));
    setOutcome({
      message:
        receipt.outcome === "EXCLUDED"
          ? "候选已排除。"
          : receipt.outcome === "ALREADY_IMPORTED"
            ? "该来源已入库，未重复创建商机。"
            : "已确认入库。",
      opportunityId: receipt.opportunityId || candidate.opportunityId,
    });
  };
  const submit = async () => {
    const snapshot = confirmation;
    if (
      !snapshot?.acknowledged ||
      lock.current ||
      (snapshot.action === "EXCLUDE" && !snapshot.reason.trim())
    )
      return;
    const invalid = snapshot.rows.find(
      (row) => blockers(row, snapshot.action).length,
    );
    if (invalid) {
      setError("复核条件已变化，请取消并重新检查。");
      return;
    }
    lock.current = true;
    setError("");
    let completed = 0;
    try {
      for (let i = 0; i < snapshot.rows.length; i++) {
        const candidate = snapshot.rows[i];
        const request: DecisionReview = {
          ...snapshot.reviews[i],
          reason: snapshot.reason.trim(),
        };
        setBusy(candidate.id);
        const receipt: CandidateReceipt = {
          requestId: request.requestId,
          action: request.action,
          status: "PROCESSING",
          review: reviewSnapshot(request),
        };
        updateDraft(candidate, (old) => ({ ...old, pending: receipt }));
        try {
          const result = await candidateTimeout(
            service.reviewCandidate(request),
          );
          if (!live.current) return;
          if (
            result.kind === "pending" &&
            result.requestId === request.requestId &&
            result.candidateId === candidate.id
          ) {
            updateDraft(candidate, (old) => ({
              ...old,
              pending: { ...receipt, status: result.status },
            }));
            throw new ServiceError(
              "RESULT_UNKNOWN",
              "复核仍在处理，请先核对本次结果。",
              408,
            );
          }
          if (
            result.kind !== "decision" ||
            result.requestId !== request.requestId ||
            result.candidate.id !== candidate.id ||
            result.receipt.requestId !== request.requestId ||
            result.receipt.action !== request.action ||
            !completedCandidateReview(result.candidate, result.receipt) ||
            !sameReviewSnapshot(receipt.review, result.receipt.review)
          )
            throw new ServiceError(
              "RESULT_UNKNOWN",
              "服务结果尚不能确认，请核对本次复核。",
              408,
            );
          applyDecision(result.candidate, result.receipt);
          completed++;
        } catch (e) {
          if (!live.current) return;
          if (uncertainReview(e))
            updateDraft(candidate, (old) => ({
              ...old,
              pending: { ...receipt, status: "UNKNOWN" },
            }));
          else
            updateDraft(candidate, (old) => ({ ...old, pending: undefined }));
          setError(
            `${errorMessage(e)}${snapshot.rows.length > 1 ? ` 本批已完成 ${completed} 条，其余未继续提交。` : ""}`,
          );
          break;
        }
      }
    } finally {
      lock.current = false;
      if (live.current) {
        setBusy(null);
        setConfirmation(null);
      }
    }
  };
  const reconcile = async (candidate: Candidate) => {
    const pending = getDraft(candidate).pending;
    if (!pending || lock.current) return;
    lock.current = true;
    setBusy(candidate.id);
    setError("");
    try {
      const page = await candidateTimeout(
        service.candidates({
          ids: [candidate.id],
          reviewRequestId: pending.requestId,
          page: 1,
          pageSize: 1,
        }),
      );
      if (!live.current) return;
      const latest = page.items.find(
        (item) => item.id === candidate.id && !candidateSample(item),
      );
      const receipt = latest?.lastReview;
      if (
        !latest ||
        !receipt ||
        receipt.requestId !== pending.requestId ||
        receipt.action !== pending.action
      ) {
        setError("尚未获得本次复核的确定结果，请稍后再次核对。");
        return;
      }
      if (
        completedCandidateReview(latest, receipt) &&
        (!pending.review || sameReviewSnapshot(pending.review, receipt.review))
      ) {
        applyDecision(latest, receipt);
        return;
      }
      if (receipt.status === "FAILED") {
        updateDraft(candidate, (old) => ({ ...old, pending: undefined }));
        resource.setData((old) =>
          old
            ? {
                ...old,
                items: old.items.map((row) =>
                  row.id === latest.id ? latest : row,
                ),
              }
            : old,
        );
        setError(
          receipt.message ||
            "服务端确认本次复核失败，当前信息已保留，可检查后重新提交。",
        );
        return;
      }
      setError("复核仍在处理中或结果未知，尚未重新提交。");
    } catch (e) {
      if (live.current) setError(errorMessage(e));
    } finally {
      lock.current = false;
      if (live.current) setBusy(null);
    }
  };
  const openSource = async (candidate: Candidate) => {
    try {
      await service.openExternal(candidate.url);
    } catch (e) {
      setError(errorMessage(e));
    }
  };
  const currentBlockers = selected ? blockers(selected, "INCLUDE") : [];
  return (
    <>
      <PageHeader
        title="原始线索"
        description="先核对原文与画像，再确认是否进入客户商机库。"
        back={() => navigate("/collection")}
      />
      <Tabs
        active={sample ? "sample" : "customer"}
        items={[
          { key: "customer", label: "待复核线索" },
          { key: "sample", label: "公开研究样例" },
        ]}
        onChange={(value) =>
          navigate("/candidates" + (value === "sample" ? "?scope=sample" : ""))
        }
      />
      <div className="filter-bar">
        <Field label="来源">
          <select
            aria-label="候选来源筛选"
            value={platform}
            disabled={sample}
            onChange={(e) => {
              setPlatform(e.target.value);
              setPage(1);
            }}
          >
            <option value="">全部</option>
            {["小红书", "抖音", "B站", "知乎", "公开网站"].map((name) => (
              <option key={name}>{name}</option>
            ))}
          </select>
        </Field>
        <Field label="复核状态">
          <select
            aria-label="候选复核状态筛选"
            value={status}
            disabled={sample}
            onChange={(e) => {
              setStatus(e.target.value as CandidateStatus | "");
              setPage(1);
            }}
          >
            <option value="">全部</option>
            {Object.entries(CANDIDATE_STATUS_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </Field>
        <div className="search-input">
          <MagnifyingGlass />
          <input
            aria-label="搜索原始线索"
            placeholder="搜索需求或需求方"
            disabled={sample}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setPage(1);
            }}
          />
        </div>
      </div>
      {!sample && !session.authenticated ? (
        <Empty
          title="登录后查看原始线索"
          action={<Button onClick={() => navigate("/login")}>登录</Button>}
        />
      ) : (
        <>
          <ResourceStatus
            loading={resource.loading}
            error={resource.error}
            onRetry={resource.reload}
          />
          {unsafeSample && (
            <Notice tone="error">
              服务返回了公开样例，已阻止其进入客户候选列表。
            </Notice>
          )}
          {error && <Notice tone="error">{error}</Notice>}
          {outcome && (
            <Notice
              tone="success"
              action={
                outcome.opportunityId ? (
                  <Button
                    variant="ghost"
                    onClick={() =>
                      navigate(
                        "/opportunities/" +
                          encodeURIComponent(outcome.opportunityId!),
                      )
                    }
                  >
                    查看商机
                  </Button>
                ) : undefined
              }
            >
              {outcome.message}
            </Notice>
          )}
          {!resource.loading && !resource.error && !unsafeSample && (
            <div className="candidate-layout">
              <section aria-label="原始线索列表">
                <div className="section-heading">
                  <span>
                    共 {resource.data?.total || 0} 条
                    {sample ? "公开样例" : "线索"}
                  </span>
                  {!sample && (
                    <Button
                      disabled={!checked.length || !!busy}
                      onClick={() =>
                        prepare(
                          rows.filter((row) => checked.includes(row.id)),
                          "INCLUDE",
                        )
                      }
                    >
                      批量确认入库（{checked.length}）
                    </Button>
                  )}
                </div>
                {!sample && (
                  <label className="check-row">
                    <input
                      type="checkbox"
                      aria-label="选择本页待复核候选"
                      disabled={
                        !rows.some((row) => row.status === "PENDING_REVIEW")
                      }
                      checked={
                        rows.some((row) => row.status === "PENDING_REVIEW") &&
                        rows
                          .filter((row) => row.status === "PENDING_REVIEW")
                          .every((row) => checked.includes(row.id))
                      }
                      onChange={(e) =>
                        setChecked(
                          e.target.checked
                            ? rows
                                .filter(
                                  (row) => row.status === "PENDING_REVIEW",
                                )
                                .map((row) => row.id)
                            : [],
                        )
                      }
                    />
                    选择本页待复核候选
                  </label>
                )}
                {rows.map((row) => (
                  <div
                    className={`list-item ${row.id === selected?.id ? "selected" : ""}`}
                    key={row.id}
                  >
                    {!sample && (
                      <input
                        type="checkbox"
                        aria-label={`选择候选${row.title}`}
                        disabled={row.status !== "PENDING_REVIEW"}
                        checked={checked.includes(row.id)}
                        onChange={(e) =>
                          setChecked((old) =>
                            e.target.checked
                              ? [...new Set([...old, row.id])]
                              : old.filter((id) => id !== row.id),
                          )
                        }
                      />
                    )}
                    <button
                      className="candidate-row-button"
                      aria-label={`查看候选${row.title}`}
                      onClick={() => setSelectedId(row.id)}
                    >
                      <h3>{row.title}</h3>
                      <p className="muted">
                        {row.sourceLabel || row.platform} ·{" "}
                        {formatDate(row.publishedAt)}
                      </p>
                      <Badge
                        tone={
                          row.status === "PENDING_REVIEW"
                            ? "orange"
                            : row.status === "IMPORTED"
                              ? "green"
                              : "neutral"
                        }
                      >
                        {candidateSample(row) ? "公开研究样例 · " : ""}
                        {CANDIDATE_STATUS_LABELS[row.status]}
                      </Badge>
                    </button>
                  </div>
                ))}
                {!rows.length && (
                  <Empty
                    title={
                      query || platform || status !== "PENDING_REVIEW"
                        ? "没有符合条件的线索"
                        : "暂无待复核线索"
                    }
                    description="完成真实采集后，在这里核对原文与画像。"
                  />
                )}
                <Pagination
                  page={resource.data?.page || page}
                  total={resource.data?.total || 0}
                  pageSize={resource.data?.pageSize || 10}
                  onChange={setPage}
                />
              </section>
              <aside aria-label="候选证据与人工复核">
                {selected ? (
                  <>
                    <div className="section-heading">
                      <h2>线索复核</h2>
                      <Badge tone="orange">
                        {CANDIDATE_STATUS_LABELS[selected.status]}
                      </Badge>
                    </div>
                    <h2>{selected.title}</h2>
                    <p className="muted">{selected.buyer}</p>
                    <div className="fact-strip">
                      <div>
                        <span>发布来源</span>
                        <strong>
                          {selected.sourceLabel || selected.platform}
                        </strong>
                      </div>
                      <div>
                        <span>发布时间</span>
                        <strong>{formatDate(selected.publishedAt)}</strong>
                      </div>
                      {selected.location && (
                        <div>
                          <span>项目地点</span>
                          <strong>{selected.location}</strong>
                        </div>
                      )}
                      {selected.deadline && (
                        <div>
                          <span>资料截止</span>
                          <strong>{formatDate(selected.deadline)}</strong>
                        </div>
                      )}
                    </div>
                    <div className="section-heading">
                      <h3>原始内容与证据</h3>
                      <Button
                        variant="ghost"
                        disabled={!selected.url}
                        onClick={() => void openSource(selected)}
                      >
                        查看原文 <ArrowSquareOut />
                      </Button>
                    </div>
                    <blockquote className="evidence-quote">
                      {selected.excerpt || "原始摘录缺失，需补充证据。"}
                    </blockquote>
                    <p>{selected.summary}</p>
                    {selected.stage && (
                      <p className="muted">采购阶段：{selected.stage}</p>
                    )}
                    {!sample && selected.sourceStatus !== "OPEN" && (
                      <Notice tone="warning">
                        {
                          (
                            {
                              EXPIRED: "原文已过期",
                              BLOCKED: "原文访问受阻",
                              UNVERIFIED: "原文可访问性尚未核实",
                            } as Record<string, string>
                          )[selected.sourceStatus]
                        }
                        ，暂不能确认入库。打开链接不会自动解除此限制。
                      </Notice>
                    )}
                    {sample ? (
                      <>
                        <dl className="detail-list">
                          <div>
                            <dt>需求方</dt>
                            <dd>{PUBLIC_SAMPLE.buyer}</dd>
                          </div>
                          <div>
                            <dt>需核实事项</dt>
                            <dd>{PUBLIC_SAMPLE.risk}</dd>
                          </div>
                        </dl>
                        <Field label="目标业务画像">
                          <select disabled aria-label="样例业务画像">
                            <option>公开样例不绑定客户画像</option>
                          </select>
                        </Field>
                        <Notice>
                          公开样例只供查看，不能确认入库或排除客户线索。
                        </Notice>
                        <div className="action-row">
                          <Button disabled>排除</Button>
                          <Button variant="primary" disabled>
                            确认入库
                          </Button>
                        </div>
                      </>
                    ) : (
                      <>
                        <ResourceStatus
                          loading={profiles.loading}
                          error={profiles.error}
                          onRetry={profiles.reload}
                        />
                        <Field label="目标业务画像" required>
                          <select
                            aria-label="候选目标业务画像"
                            disabled={
                              !!busy ||
                              !!editor?.pending ||
                              selected.status !== "PENDING_REVIEW"
                            }
                            value={editor?.profileId || ""}
                            onChange={(e) => {
                              const profile = confirmedProfiles.find(
                                (p) => p.id === e.target.value,
                              );
                              if (profile) requestAssessment(selected, profile);
                            }}
                          >
                            <option value="">选择已确认画像</option>
                            {confirmedProfiles.map((profile) => (
                              <option key={profile.id} value={profile.id}>
                                版本 {profile.version} ·{" "}
                                {profile.fields.service || "业务画像"}
                              </option>
                            ))}
                          </select>
                        </Field>
                        {!profiles.loading &&
                          !profiles.error &&
                          !confirmedProfiles.length && (
                            <Notice
                              action={
                                <Button
                                  variant="ghost"
                                  onClick={() => navigate("/profile")}
                                >
                                  完善画像
                                </Button>
                              }
                            >
                              尚无已确认画像，请先保存并确认业务画像。
                            </Notice>
                          )}
                        {selected.status === "PENDING_REVIEW" && (
                          <Button
                            disabled={
                              !selectedProfile || !!busy || !!editor?.pending
                            }
                            loading={busy === selected.id}
                            onClick={() =>
                              selectedProfile &&
                              requestAssessment(selected, selectedProfile)
                            }
                          >
                            按画像重新判断
                          </Button>
                        )}
                        {editor?.assessment &&
                          selected.status === "PENDING_REVIEW" && (
                            <p className="field-hint">
                              判断建议 · 画像版本{" "}
                              {editor.assessment.profileVersion} ·{" "}
                              {formatDate(editor.assessment.assessedAt)} ·
                              待人工校对
                            </p>
                          )}
                        {selected.status === "PENDING_REVIEW" &&
                        editor?.assessment ? (
                          <fieldset
                            className="profile-fieldset"
                            disabled={!!busy || !!editor.pending}
                          >
                            {(
                              Object.keys(
                                CANDIDATE_EVIDENCE_LABELS,
                              ) as (keyof CandidateEvidence)[]
                            ).map((key) => (
                              <Field
                                key={key}
                                label={CANDIDATE_EVIDENCE_LABELS[key]}
                                required
                              >
                                <textarea
                                  aria-label={`候选${CANDIDATE_EVIDENCE_LABELS[key]}`}
                                  rows={2}
                                  maxLength={2000}
                                  value={editor.evidence[key]}
                                  onChange={(e) =>
                                    updateDraft(selected, (old) => ({
                                      ...old,
                                      evidence: {
                                        ...old.evidence,
                                        [key]: e.target.value,
                                      },
                                    }))
                                  }
                                />
                              </Field>
                            ))}
                          </fieldset>
                        ) : selected.lastReview?.review ||
                          selected.assessment ? (
                          <dl className="detail-list">
                            {(
                              Object.keys(
                                CANDIDATE_EVIDENCE_LABELS,
                              ) as (keyof CandidateEvidence)[]
                            ).map((key) => (
                              <div key={key}>
                                <dt>{CANDIDATE_EVIDENCE_LABELS[key]}</dt>
                                <dd>
                                  {selected.lastReview?.review?.evidence[key] ||
                                    selected.assessment?.evidence[key] ||
                                    "—"}
                                </dd>
                              </div>
                            ))}
                          </dl>
                        ) : (
                          <p className="muted">
                            绑定已确认画像后获取证据判断；服务未返回前不会生成结论。
                          </p>
                        )}
                        {selected.lastReview?.action === "EXCLUDE" &&
                          selected.lastReview.review?.reason && (
                            <p>排除原因：{selected.lastReview.review.reason}</p>
                          )}
                        {editor?.pending && (
                          <Notice
                            tone="warning"
                            action={
                              <Button
                                loading={busy === selected.id}
                                onClick={() => void reconcile(selected)}
                              >
                                核对本次结果
                              </Button>
                            }
                          >
                            本次复核结果尚未确定，已保留请求记录；核对前不会再次提交。
                          </Notice>
                        )}
                        {selected.lastReview?.reviewedBy && (
                          <p className="muted">
                            服务端复核记录：{selected.lastReview.reviewedBy} ·{" "}
                            {formatDate(selected.lastReview.reviewedAt || "")}
                          </p>
                        )}
                        {selected.status === "PENDING_REVIEW" ? (
                          <>
                            <p className="field-hint">
                              {currentBlockers.length
                                ? currentBlockers.join("；")
                                : "五项依据可人工修改，确认后才进入客户商机库。"}
                            </p>
                            <div className="action-row">
                              <Button
                                disabled={
                                  !!busy ||
                                  blockers(selected, "EXCLUDE").length > 0
                                }
                                onClick={() => prepare([selected], "EXCLUDE")}
                              >
                                排除
                              </Button>
                              <Button
                                variant="primary"
                                disabled={!!busy || currentBlockers.length > 0}
                                onClick={() => prepare([selected], "INCLUDE")}
                              >
                                确认入库
                              </Button>
                            </div>
                          </>
                        ) : (
                          <Notice>
                            {selected.status === "DUPLICATE"
                              ? "该候选与已有商机重复，不能重复入库。"
                              : selected.status === "EXCLUDED"
                                ? "该候选已排除。"
                                : "该候选已入客户商机库。"}
                            {selected.opportunityId && (
                              <Button
                                variant="ghost"
                                onClick={() =>
                                  navigate(
                                    "/opportunities/" +
                                      encodeURIComponent(
                                        selected.opportunityId!,
                                      ),
                                  )
                                }
                              >
                                查看已有商机
                              </Button>
                            )}
                          </Notice>
                        )}
                      </>
                    )}
                  </>
                ) : (
                  <Empty title="选择线索查看证据" />
                )}
              </aside>
            </div>
          )}
        </>
      )}
      {replaceAssessment && (
        <Confirm
          title="重新判断并替换人工修改？"
          confirmText="重新判断"
          onCancel={() => setReplaceAssessment(null)}
          onConfirm={() => {
            const next = replaceAssessment;
            setReplaceAssessment(null);
            void assess(next.candidate, next.profile);
          }}
        >
          <p>
            当前五项复核依据包含人工修改。新判断成功返回后才替换这些内容；请求失败保留现有文字。
          </p>
        </Confirm>
      )}
      {confirmation && (
        <Modal
          title={
            confirmation.action === "EXCLUDE"
              ? "确认排除候选"
              : confirmation.rows.length > 1
                ? `批量确认 ${confirmation.rows.length} 条入库`
                : "确认候选入库"
          }
          onClose={() => {
            if (!busy) setConfirmation(null);
          }}
          footer={
            <>
              <Button disabled={!!busy} onClick={() => setConfirmation(null)}>
                取消
              </Button>
              <Button
                variant={
                  confirmation.action === "EXCLUDE" ? "danger" : "primary"
                }
                loading={!!busy}
                disabled={
                  !confirmation.acknowledged ||
                  (confirmation.action === "EXCLUDE" &&
                    !confirmation.reason.trim())
                }
                onClick={() => void submit()}
              >
                {confirmation.action === "EXCLUDE" ? "确认排除" : "确认入库"}
              </Button>
            </>
          }
        >
          {confirmation.rows.map((row, index) => (
            <section key={row.id}>
              <h3>{row.title}</h3>
              <p className="muted">
                画像版本 {confirmation.reviews[index].profileVersion} · 来源版本{" "}
                {row.sourceVersionId}
              </p>
              <dl className="detail-list">
                {(
                  Object.keys(
                    CANDIDATE_EVIDENCE_LABELS,
                  ) as (keyof CandidateEvidence)[]
                ).map((key) => (
                  <div key={key}>
                    <dt>{CANDIDATE_EVIDENCE_LABELS[key]}</dt>
                    <dd>{confirmation.reviews[index].evidence[key]}</dd>
                  </div>
                ))}
              </dl>
            </section>
          ))}
          {confirmation.action === "EXCLUDE" && (
            <Field label="排除原因" required>
              <textarea
                aria-label="候选排除原因"
                rows={3}
                maxLength={1000}
                value={confirmation.reason}
                onChange={(e) =>
                  setConfirmation((old) =>
                    old ? { ...old, reason: e.target.value } : old,
                  )
                }
              />
            </Field>
          )}
          <label className="check-row">
            <input
              type="checkbox"
              checked={confirmation.acknowledged}
              onChange={(e) =>
                setConfirmation((old) =>
                  old ? { ...old, acknowledged: e.target.checked } : old,
                )
              }
            />
            我已逐条核对原始证据、画像与以上复核依据
          </label>
          <p className="field-hint">
            复核人、时间和最终结果由客户服务记录。批量操作逐条提交，任一结果未知即停止后续提交。
          </p>
          {error && <Notice tone="error">{error}</Notice>}
        </Modal>
      )}
    </>
  );
}
