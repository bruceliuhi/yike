import { useEffect, useMemo, useRef, useState } from "react";
import { currentDemandDate } from "../domain/candidateDemandEvidence";
import {
  ArrowSquareOut,
  Copy,
  DownloadSimple,
  MagnifyingGlass,
} from "@phosphor-icons/react";
import { useApp } from "../app/context";
import { boundedRequest } from "../app/boundedRequest";
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
import { PlatformIcon, PlatformLabel } from "../components/Platform";
import type { Opportunity, Profile } from "../domain/models";
import {
  compareDeadlines,
  deadlineFilter,
  libraryExportFields,
  matchesLibraryFilters,
} from "../domain/opportunityLibrary";
import {
  libraryFactCells,
  LibraryFilters,
  useDeadlineClock,
} from "./opportunities/LibraryFacts";
import { useCandidateReviewLedger } from "./opportunities/useCandidateReviewLedger";
import { useCandidateRequests } from "./opportunities/useCandidateRequests";
import { CandidateOriginalEvidence } from "./opportunities/CandidateOriginalEvidence";
import { CandidateAssessmentDetails } from "./opportunities/CandidateAssessmentDetails";
import { CandidateSourceVerification } from "./opportunities/CandidateSourceVerification";
import { CandidateRequestHistory } from "./opportunities/CandidateRequestHistory";
import type { CandidateRequestOperation } from "../domain/candidateRequestOperation";
import type { CandidateAssessmentDto, CandidateReviewResultDto, SourceVerificationRequest } from "../../shared/candidateReviewApi";
import { CANDIDATE_PLATFORM_LABELS } from "../services/candidateReview";
import { PendingCandidateReviews } from "./opportunities/PendingCandidateReviews";
import { ResearchLibrary } from "./opportunities/ResearchLibrary";
import { EvidenceTimeline } from "./opportunities/EvidenceTimeline";
import { ResearchDraftHandoff } from "./opportunities/ResearchDraftHandoff";
import { hasResearchScope, researchQuoteLabel } from "../domain/opportunityResearch";
import { readResearchRecord } from "../services/opportunityResearch";
import { parseOpportunitySourceEvidence } from "../domain/opportunitySourceEvidence";
import {
  RESEARCH_CATEGORIES,
  type ResearchClassification,
} from "../domain/opportunityResearch";
import {
  candidateReviewHash,
  matchingCandidateReceipt,
  type CandidateReviewOperation,
} from "../domain/candidateReviewOperation";
import { ServiceError, errorMessage } from "../services/contracts";
import { downloadText, downloadErrorMessage } from "../services/download";
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

export {
  PUBLIC_SAMPLE,
  isSample,
  opportunityStatus,
  customerCsv,
  EvidencePanel,
} from "./opportunities/OpportunityEvidence";
import {
  PUBLIC_SAMPLE,
  isSample,
  opportunityStatus,
  customerCsv,
  EvidencePanel,
  SourcePlatform,
} from "./opportunities/OpportunityEvidence";

export function OpportunitiesPage() {
  const { session, service, route } = useApp();
  if (
    (service.opportunityResearch && hasResearchScope(session.accountScope)) ||
    route.query.get("scope") === "sample"
  )
    return (
      <ResearchLibrary
        key={`${session.authenticated}:${session.userId || "public"}:${JSON.stringify(session.accountScope)}:${route.query.get("scope") || "customer"}`}
      />
    );
  return (
    <OpportunityList
      key={`${session.authenticated}:${session.userId || "public"}:${JSON.stringify(session.accountScope)}`}
    />
  );
}
function OpportunityList() {
  const { service, session, route, navigate, notify } = useApp();
  const resource = useResource(
    () =>
      session.authenticated
        ? boundedRequest(() => service.opportunities(), {
            timeoutMessage: "商机读取超时，请重试。",
          })
        : Promise.resolve([] as Opportunity[]),
    [service, session.userId, session.authenticated],
  );
  const scope = route.query.get("scope") === "sample" ? "sample" : "customer";
  const [query, setQuery] = useState(route.query.get("q") || "");
  const [platform, setPlatform] = useState(route.query.get("platform") || "");
  const [status, setStatus] = useState(route.query.get("status") || "");
  const [stage, setStage] = useState(route.query.get("stage") || "all");
  const [deadline, setDeadline] = useState(
    deadlineFilter(route.query.get("deadline")),
  );
  const now = useDeadlineClock();
  const [sort, setSort] = useState(route.query.get("sort") || "updated");
  const [page, setPage] = useState(Number(route.query.get("page")) || 1);
  const [selected, setSelected] = useState<string[]>([]);
  const [exporting, setExporting] = useState(false);
  const exportPending = useRef(false);
  const exportMounted = useRef(true);
  const exportIdentity = useRef(session.authenticated ? session.userId : null);
  exportIdentity.current = session.authenticated ? session.userId : null;
  useEffect(() => {
    exportMounted.current = true;
    return () => {
      exportMounted.current = false;
    };
  }, []);
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
            (!status || opportunityStatus(r) === status) &&
            matchesLibraryFilters(r, stage, deadline, now),
        )
        .sort((a, b) =>
          sort === "deadline"
            ? compareDeadlines(a, b)
            : sort === "title"
              ? a.title.localeCompare(b.title, "zh-CN")
              : (Date.parse(b.updatedAt || b.publishedAt) || 0) -
                (Date.parse(a.updatedAt || a.publishedAt) || 0),
        ),
    [rows, query, platform, status, stage, deadline, sort, now],
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
    setStage("all");
    setDeadline("all");
    navigate("/opportunities" + (value === "sample" ? "?scope=sample" : ""));
  };
  const open = (row: Opportunity) => {
    const back = new URLSearchParams({
      scope,
      q: query,
      platform,
      status,
      stage,
      deadline,
      sort,
      page: String(visiblePage),
    });
    navigate(
      `/opportunities/${encodeURIComponent(row.id)}?returnTo=${encodeURIComponent("/opportunities?" + back)}`,
    );
  };
  const exportRows = async () => {
    if (
      exportPending.current ||
      !session.authenticated ||
      scope !== "customer" ||
      resource.loading ||
      resource.error
    )
      return;
    const chosen = customers.filter((r) => selected.includes(r.id));
    if (!chosen.length) return;
    const identity = exportIdentity.current;
    exportPending.current = true;
    setExporting(true);
    try {
      const result = await downloadText({
        format: "csv",
        name: "意客AI-客户商机.csv",
        content: customerCsv(chosen),
      });
      if (!exportMounted.current || identity !== exportIdentity.current) return;
      if (result.status === "saved")
        notify(`已保存 ${chosen.length} 条选中客户商机。`, "success");
      else if (result.status === "initiated")
        notify(
          `已发起 ${chosen.length} 条客户商机的下载，请在浏览器中确认。`,
          "info",
        );
      else if (result.status === "error")
        notify(downloadErrorMessage(result.error), "error");
    } catch {
      if (exportMounted.current && identity === exportIdentity.current)
        notify("文件未能保存，请检查保存位置后重试。", "error");
    } finally {
      exportPending.current = false;
      if (exportMounted.current) setExporting(false);
    }
  };
  return (
    <>
      <PageHeader
        title="商机库"
        description="汇集多渠道的商机信息，支持筛选、查看和跟进。"
      />
      <Notice>
        {service.opportunityResearch && !hasResearchScope(session.accountScope)
          ? "当前账户空间尚未核验，需求分类与观察服务暂不可用。"
          : "需求分类与观察服务尚未接通。"}
        已有商机仍可查看。
      </Notice>
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
      </div>
      <LibraryFilters
        rows={rows}
        stage={stage}
        deadline={deadline}
        sort={sort}
        onStage={(value) => {
          setStage(value);
          setPage(1);
        }}
        onDeadline={(value) => {
          setDeadline(value);
          setPage(1);
        }}
        onSort={(value) => {
          setSort(value);
          setPage(1);
        }}
        active={Boolean(
          query ||
          platform ||
          status ||
          stage !== "all" ||
          deadline !== "all" ||
          sort !== "updated",
        )}
        onReset={() => {
          setQuery("");
          setPlatform("");
          setStatus("");
          setStage("all");
          setDeadline("all");
          setSort("updated");
          setPage(1);
        }}
      />
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
                    <th>阶段</th>
                    <th>状态</th>
                    <th>资料截止</th>
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
                        <SourcePlatform
                          platform={row.platform}
                          sourceLabel={
                            isSample(row) ? "湖南省商务厅官网" : undefined
                          }
                        />
                      </td>
                      <td>{libraryFactCells(row).stage}</td>
                      <td>
                        <Badge tone={isSample(row) ? "orange" : "neutral"}>
                          {opportunityStatus(row)}
                        </Badge>
                      </td>
                      <td>{libraryFactCells(row).deadline}</td>
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
                    query ||
                    platform ||
                    status ||
                    stage !== "all" ||
                    deadline !== "all"
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
                exporting ||
                scope === "sample" ||
                !selected.length ||
                resource.loading ||
                Boolean(resource.error) ||
                !session.authenticated
              }
              onClick={exportRows}
            >
              <DownloadSimple />
              {exporting ? "正在保存…" : "导出所选客户商机"}
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
    <OpportunityDetail
      key={`${session.userId || "public"}:${JSON.stringify(session.accountScope)}:${id}`}
      id={id}
    />
  );
}
function OpportunityDetail({ id }: { id: string }) {
  const { service, session, route, navigate, notify } = useApp();
  const [detailTab, setDetailTab] = useState(
    route.query.get("tab") === "changes" ? "changes" : "evidence",
  );
  const [similarOpen, setSimilarOpen] = useState(false);
  const resource = useResource(async (requestSignal) => {
    if (id === "sample")
      return {
        opportunity: PUBLIC_SAMPLE,
        classification: undefined as ResearchClassification | undefined,
      };
    if (!session.authenticated) throw new Error("请登录后查看客户商机。");
    const record = await boundedRequest(
      async (signal) => {
        const research = service.opportunityResearch && hasResearchScope(session.accountScope);
        const record = research
          ? await readResearchRecord(service.opportunityResearch!, session, id, signal)
          : {
              opportunity: await service.opportunity(id, signal),
              classification: undefined as ResearchClassification | undefined,
            };
        signal.throwIfAborted();
        let item = record.opportunity;
        if (research && item.sourceEvidence === undefined) {
          const detail = await service.opportunity(id, signal);
          signal.throwIfAborted();
          if (detail.id !== item.id || detail.profileVersionId !== item.profileVersionId)
            throw new Error("原文证据身份或画像不匹配，请重新读取。");
          // Supplement only the fixed snapshot; keep the R4 classification and bindings.
          item = { ...item, sourceEvidence: detail.sourceEvidence };
        }
        try {
          item = { ...item, sourceEvidence: parseOpportunitySourceEvidence(item.sourceEvidence, {
            opportunityId: item.id, profileVersionId: item.profileVersionId,
          }) };
        } catch {
          throw new Error("原文证据响应不完整，请重新读取。");
        }
        return { ...record, opportunity: item };
      },
      { signal: requestSignal, timeoutMessage: "机会证据读取超时，请重试。" },
    );
    const item = record.opportunity;
    if (item.id !== id || isSample(item))
      throw new Error("机会身份不匹配，请刷新重试。");
    return record;
  }, [
    id,
    service,
    session.userId,
    session.authenticated,
    JSON.stringify(session.accountScope),
  ]);
  const row = resource.data?.opportunity;
  const classification = resource.data?.classification;
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
  const researchOnly = Boolean(
    classification &&
    (classification.category !== "OPPORTUNITY" ||
      classification.review.status !== "RECOGNIZED"),
  );
  return (
    <>
      <PageHeader title={row.title} description={row.buyer} back={back} />
      <div className="action-row">
        <Button onClick={() => setSimilarOpen(true)}>多找类似</Button>
      </div>
      <div className="inline-meta">
        <Badge tone={sample ? "orange" : "blue"}>
          {sample
            ? "公开研究样例 · 待人工复核 · 未入客户库"
            : opportunityStatus(row)}
        </Badge>
        {classification && (
          <Badge tone="neutral">
            {RESEARCH_CATEGORIES[classification.category]}
          </Badge>
        )}
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
              [
                "来源状态",
                (
                  {
                    OPEN: "有效",
                    UNVERIFIED: "待核验",
                    EXPIRED: "已过期",
                    BLOCKED: "访问受阻",
                    CLOSED: "已关闭",
                  } as Record<string, string>
                )[row.sourceStatus] || "待核验",
              ],
              [
                "画像状态",
                (
                  {
                    CONFIRMED: "已确认",
                    DRAFT: "待确认",
                    UNBOUND: "未绑定",
                    STALE: "需重新确认",
                  } as Record<string, string>
                )[row.profileStatus] || "待核验",
              ],
              ["发布时间", formatDate(row.publishedAt)],
            ]
        ).map(([label, value]) => (
          <div key={label}>
            <span>{label}</span>
            <strong>
              {label === "来源平台" ? (
                <PlatformLabel platform={value || "来源待核验"} size={18} />
              ) : (
                value || "—"
              )}
            </strong>
          </div>
        ))}
      </div>
      {!sample &&
        (row.sourceStatus !== "OPEN" || row.profileStatus !== "CONFIRMED") && (
          <Notice tone="warning">
            来源或画像需要重新核验，请先确认需求仍有效。
          </Notice>
        )}
      <div
        className={`evidence-layout${similarOpen ? " research-expanded" : ""}`}
      >
        <section>
          <Tabs
            active={detailTab}
            items={[
              { key: "evidence", label: "证据详情" },
              { key: "changes", label: "项目变化" },
            ]}
            onChange={setDetailTab}
          />
          <EvidencePanel opportunity={row} compact={detailTab === "changes"} />
          {detailTab === "changes" && <EvidenceTimeline opportunity={row} />}
        </section>
        <aside className="contact-panel" hidden={similarOpen}>
          {researchOnly ? (
            <>
              <h2>研究判断</h2>
              <p>{classification!.reason}</p>
              {classification!.evidence.map((quote, i) => (
                <blockquote className="evidence-quote" key={i}>
                  {quote.field && <div className="muted text-small">{researchQuoteLabel(quote)}</div>}
                  {quote.quote}
                </blockquote>
              ))}
              <Notice>
                该记录尚不是已认可的明确需求，先保留研究证据，不进入客户触达或自动扩展。
              </Notice>
            </>
          ) : (
            <>
              <h2>
                联系准备{" "}
                <span className="muted text-small">待校对 · 尚未发送</span>
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
                    onClick={() =>
                      navigate("/outreach?opportunity=sample&channel=comment")
                    }
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
                        "/outreach?opportunity=" +
                          encodeURIComponent(row.id) +
                          "&channel=comment",
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
            </>
          )}
        </aside>
      </div>
      {similarOpen && (
        <ResearchDraftHandoff
          opportunity={row}
          onClose={() => setSimilarOpen(false)}
        />
      )}
    </>
  );
}

export function CandidatesPage() {
  const { session, route } = useApp();
  return (
    <CandidateWorkbench
      key={`${session.authenticated}:${session.userId || "public"}:${JSON.stringify(session.accountScope)}:${route.query.get('task')||''}:${route.query.get('scope')||''}`}
    />
  );
}

interface CandidateEditor {
  binding?: string;
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
const liveCandidate = (row: Candidate) =>
  !candidateSample(row) && row.currentBindingValid !== undefined;
const candidateIdentity = (row: Candidate) =>
  JSON.stringify([
    row.id,
    row.revision,
    row.sourceVersionId,
    row.profileId,
    row.profileVersion,
    row.strategyVersionId,
    row.historical,
    row.currentBindingValid,
    row.assessmentStale,
  ]);
function candidateEditor(row: Candidate): CandidateEditor {
  const evidence = {
    ...(row.assessment?.evidence || EMPTY_CANDIDATE_EVIDENCE),
  };
  return {
    binding: candidateIdentity(row),
    profileId: row.profileId || row.assessment?.profileId || "",
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
    ((error.code === "REVIEW_REJECTED" &&
      error.status >= 400 &&
      error.status < 500 &&
      error.status !== 408) ||
      (error.code === "CAPABILITY_UNAVAILABLE" && error.status === 501))
  );
}

function CandidateWorkbench() {
  const { service, session, route, navigate, notify } = useApp();
  const sample = route.query.get("scope") === "sample";
  const requestedId = sample ? null : route.query.get("candidate");
  const taskId = sample ? null : route.query.get('task');
  const task = useResource(
    (signal) => session.authenticated && taskId && service.taskFeed
      ? service.taskFeed.get(taskId, signal) : Promise.resolve(null),
    [service, session.userId, session.authenticated, session.accountScope?.id, session.accountScope?.version, taskId],
  );
  const reviewLedger = useCandidateReviewLedger(
    session.authenticated ? session.userId : undefined,
  );
  const requests = useCandidateRequests("P07");
  const scopeRef = useRef("");
  scopeRef.current = JSON.stringify([
    session.userId,
    session.authenticated,
    sample,
    requestedId,
  ]);
  const [query, setQuery] = useState("");
  const [platform, setPlatform] = useState("");
  const [status, setStatus] = useState<CandidateStatus | "">(taskId ? '' : "PENDING_REVIEW");
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
  const [sourceOpening,setSourceOpening]=useState(false);
  const sourceOpeningLock=useRef(false);
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
  const [retryKey, setRetryKey] = useState<string | null>(null);
  const profiles = useResource(
    () =>
      session.authenticated && !sample
        ? service.profiles()
        : Promise.resolve([] as Profile[]),
    [service, session.userId, session.authenticated, sample],
  );
  const resource = useResource(
    (signal) =>
      sample
        ? Promise.resolve<CandidatePage>({
            items: [sampleCandidate],
            total: 1,
            page: 1,
            pageSize: 10,
          })
        : session.authenticated
          ? boundedRequest(
              (requestSignal) =>
                service.candidates(
                  requestedId
                    ? { ids: [requestedId], page: 1, pageSize: 10, ...(taskId?{taskId}:{}) }
                    : {
                        ...(taskId?{taskId}:{}),
                        query: query.trim(),
                        platform: platform || undefined,
                        status: status || undefined,
                        page,
                        pageSize: 10,
                      },
                  requestSignal,
                ),
              { signal, timeoutMessage: "线索读取超时，请重试。" },
            ).then((result) => {
              if (result.taskId !== (taskId || undefined))
                throw new Error('返回线索与采集任务不匹配，请刷新重试。');
              if (
                requestedId &&
                (result.items.length > 1 ||
                  result.items.some((row) => row.id !== requestedId))
              )
                throw new Error("返回线索与待办目标不匹配，请刷新重试。");
              return result;
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
      requestedId,
      taskId,
    ],
  );
  const confirmedProfiles = (profiles.data || []).filter(
    (p) => p.status === "CONFIRMED",
  );
  const unsafeSample = !sample && resource.data?.items.some(candidateSample);
  const rows = unsafeSample ? [] : resource.data?.items || [];
  const rowsRef = useRef(rows);
  rowsRef.current = rows;
  const verifiedCandidateIds = rows.map((row) => row.id);
  const scopedReviewRecords = taskId
    ? reviewLedger.records.filter((record) =>
        verifiedCandidateIds.includes(record.candidateId),
      )
    : reviewLedger.records;
  const scopedRequestOperations = taskId
    ? requests.operations.filter((operation) =>
        verifiedCandidateIds.includes(operation.candidateId),
      )
    : requests.operations;
  const hasUnscopedHistory = Boolean(
    taskId &&
      (scopedReviewRecords.length !== reviewLedger.records.length ||
        scopedRequestOperations.length !== requests.operations.length),
  );
  const selected = rows.find((row) => row.id === selectedId) || rows[0];
  const original = useResource(
    (signal) =>
      selected && liveCandidate(selected) && service.rawCandidateEvidence
        ? service.rawCandidateEvidence(
            {
              candidateId: selected.id,
              candidateRevision: selected.revision,
              sourceVersionId: selected.sourceVersionId,
              profileId: selected.profileId,
              strategyVersionId: selected.strategyVersionId,
            },
            signal,
          )
        : Promise.resolve(null),
    [
      service,
      session.userId,
      JSON.stringify(session.accountScope),
      sample,
      selected ? candidateIdentity(selected) : "",
    ],
  );
  const withPending = (
    row: Candidate,
    draft: CandidateEditor,
  ): CandidateEditor => {
    if (liveCandidate(row) && draft.binding !== candidateIdentity(row))
      draft = candidateEditor(row);
    const record = reviewLedger.records.find(
      (record) => record.candidateId === row.id,
    );
    return record && draft.pending?.requestId !== record.requestId
      ? {
          ...draft,
          pending: {
            requestId: record.requestId,
            action: record.action,
            status: "UNKNOWN",
          },
        }
      : draft;
  };
  const editor = selected
    ? withPending(selected, drafts[selected.id] || candidateEditor(selected))
    : undefined;
  const selectedProfile = confirmedProfiles.find(
    (p) => p.id === editor?.profileId,
  );
  const viewKey = JSON.stringify([
    session.userId,
    session.authenticated,
    session.accountScope,
    sample,
    requestedId,
    taskId,
    query,
    platform,
    status,
    page,
    selectedId,
  ]);
  const viewEpoch = useRef({ key: viewKey, version: 0 });
  if (viewEpoch.current.key !== viewKey)
    viewEpoch.current = {
      key: viewKey,
      version: viewEpoch.current.version + 1,
    };
  scopeRef.current = JSON.stringify([viewKey, viewEpoch.current.version]);
  const dirty = Object.values(drafts).some(
    (draft) =>
      JSON.stringify(draft.evidence) !== JSON.stringify(draft.baseline) ||
      !!draft.pending,
  );
  useUnsavedChanges(dirty || !!busy || requests.busy);
  useEffect(() => {
    live.current = true;
    return () => {
      live.current = false;
    };
  }, []);
  useEffect(() => {
    setChecked([]);
    setSelectedId("");
    setConfirmation(null);
    setReplaceAssessment(null);
  }, [query, platform, status, page, sample, requestedId, taskId]);
  const updateDraft = (
    candidate: Candidate,
    update: (old: CandidateEditor) => CandidateEditor,
  ) =>
    setDrafts((old) => ({
      ...old,
      [candidate.id]: update(
        withPending(candidate, old[candidate.id] || candidateEditor(candidate)),
      ),
    }));
  const getDraft = (candidate: Candidate) =>
    withPending(
      candidate,
      draftsRef.current[candidate.id] || candidateEditor(candidate),
    );
  const unresolvedRequest = (candidate: Candidate) =>
    liveCandidate(candidate) &&
    requests.operations.some(
      (op) =>
        op.candidateId === candidate.id &&
        op.state !== "RECORDED" &&
        !requests.operations.some(
          (child) => child.retryOf[0] === (op.invocationId ?? op.requestId),
        ),
    );
  const blockers = (
    candidate: Candidate,
    action: "INCLUDE" | "EXCLUDE",
  ): string[] => {
    const draft = getDraft(candidate);
    const profile = confirmedProfiles.find((p) => p.id === draft.profileId);
    const reasons: string[] = [];
    if (candidateSample(candidate)) reasons.push("公开样例不可修改或入库");
    if (candidate.status !== "PENDING_REVIEW") reasons.push("当前候选已处理");
    if (liveCandidate(candidate)) {
      if (!requests.available) reasons.push("真实复核服务尚未接通");
      if (candidate.historical || !candidate.currentBindingValid)
        reasons.push("历史或失效绑定只读，请读取当前版本");
      if (candidate.assessmentStale)
        reasons.push("判断已过期，请按当前版本重新判断");
      if (
        draft.assessment &&
        draft.assessment.strategyVersionId !== candidate.strategyVersionId
      )
        reasons.push("判断策略版本不一致，请重新判断");
      if (unresolvedRequest(candidate)) reasons.push("原请求尚未核对完成");
      if (
        profile &&
        (candidate.profileId !== profile.id ||
          candidate.profileVersion !== profile.version)
      )
        reasons.push("所选画像不是当前来源绑定版本");
    }
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
      !candidate.url ||
      !/^https?:\/\//i.test(candidate.url)
    )
      reasons.push("原始摘录或来源信息缺失");
    if (action === "INCLUDE" && candidate.sourceStatus !== "OPEN")
      reasons.push("来源尚未核实可访问");
    if (action === "INCLUDE" && liveCandidate(candidate)) {
      if (
        candidate.id === selected?.id &&
        (original.loading || original.error || !original.data)
      )
        reasons.push("请先成功读取当前版本原文证据");
      const verification = candidate.sourceVerification;
      const now = Date.now(),
        published = candidate.publishedAt ? Date.parse(candidate.publishedAt) :
          (currentDemandDate(candidate, draft.assessment, now) ?? NaN);
      if (verification?.demandEvidence && draft.assessment?.demandEvidenceId !== verification.id)
        reasons.push("人工补证已更新，请按当前补证重新判断");
      if (
        !Number.isFinite(published) ||
        published > now ||
        now - published > 60 * 86_400_000
      )
        reasons.push("本人发布时间未知或已超过60天");
      if (
        !verification ||
        verification.status !== "OPEN" ||
        verification.contactMethod === "NONE" ||
        verification.binding.candidateId !== candidate.id ||
        verification.binding.candidateRevision !== candidate.revision ||
        verification.binding.sourceVersionId !== candidate.sourceVersionId ||
        verification.binding.profileId !== profile?.id ||
        verification.binding.profileVersion !== profile?.version ||
        Date.parse(verification.checkedAt) > now ||
        now - Date.parse(verification.checkedAt) > 86_400_000
      )
        reasons.push("需要当前版本24小时内的人工来源核验和联系路径");
    }
    return reasons;
  };
  const assess = async (candidate: Candidate, profile: Profile) => {
    if (
      lock.current ||
      requests.busy ||
      candidateSample(candidate) ||
      candidate.status !== "PENDING_REVIEW" ||
      getDraft(candidate).pending ||
      unresolvedRequest(candidate)
    )
      return;
    if (
      liveCandidate(candidate) &&
      (candidate.historical ||
        !candidate.currentBindingValid ||
        candidate.profileId !== profile.id ||
        candidate.profileVersion !== profile.version)
    ) {
      setError("请返回当前来源绑定的已确认画像后判断。");
      return;
    }
    const scope = scopeRef.current;
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
      const result = liveCandidate(candidate)
        ? await requests.submit(request)
        : await candidateTimeout(service.reviewCandidate(request));
      if (!live.current || scopeRef.current !== scope) return;
      if (
        liveCandidate(candidate) &&
        !rowsRef.current.some(
          (row) => candidateIdentity(row) === candidateIdentity(candidate),
        )
      )
        return;
      if (!result) return;
      if (result.kind === "pending" || result.kind === "failure") {
        setError("判断结果尚未确定，请从原请求记录核对；不会自动重新调用。");
        return;
      }
      if (
        result.kind !== "assessment" ||
        result.requestId !== request.requestId ||
        result.candidateId !== candidate.id ||
        !result.assessment.id ||
        (liveCandidate(candidate) &&
          result.assessment.strategyVersionId !==
            candidate.strategyVersionId) ||
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
      if (liveCandidate(candidate))
        resource.setData(
          (old) =>
            old && {
              ...old,
              items: old.items.map((row) =>
                row.id === candidate.id
                  ? {
                      ...row,
                      assessment: result.assessment,
                      assessmentStale: false,
                    }
                  : row,
              ),
            },
        );
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
    if (requests.busy) return;
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
        ...(liveCandidate(candidate)
          ? { sourceVerificationId: candidate.sourceVerification?.id ?? null }
          : {}),
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
    const scope = scopeRef.current;
    const current = () => live.current && scopeRef.current === scope;
    if (
      !snapshot?.acknowledged ||
      lock.current ||
      (snapshot.action === "EXCLUDE" && !snapshot.reason.trim())
    )
      return;
    const invalid = snapshot.rows.find((row, index) => {
      const latest = rowsRef.current.find((value) => value.id === row.id);
      if (
        !latest ||
        candidateIdentity(latest) !== candidateIdentity(row) ||
        blockers(latest, snapshot.action).length
      )
        return true;
      const draft = getDraft(latest),
        request = snapshot.reviews[index];
      return (
        liveCandidate(latest) &&
        (latest.sourceVerification?.id !== row.sourceVerification?.id ||
          draft.profileId !== request.profileId ||
          draft.assessment?.id !== request.assessmentId ||
          JSON.stringify(draft.evidence) !== JSON.stringify(request.evidence))
      );
    });
    if (invalid) {
      setError("复核条件已变化，请取消并重新检查。");
      return;
    }
    lock.current = true;
    setError("");
    let completed = 0;
    try {
      for (let i = 0; i < snapshot.rows.length; i++) {
        if (!current()) return;
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
        let operation: CandidateReviewOperation | undefined;
        try {
          if (liveCandidate(candidate)) {
            const result = await requests.submit(request);
            if (!current()) return;
            if (!result || result.kind !== "decision") {
              setError(
                `本次结果尚未确定，请核对原请求。本批已完成 ${completed} 条，其余未继续提交。`,
              );
              break;
            }
            if (
              !rowsRef.current.some(
                (row) =>
                  candidateIdentity(row) === candidateIdentity(candidate),
              )
            ) {
              setOutcome({
                message:
                  "原请求已记录，候选版本已变化；未覆盖当前线索，请从原请求记录核对。",
                opportunityId: result.receipt.opportunityId,
              });
              break;
            }
            applyDecision(
              {
                ...result.candidate,
                platform: CANDIDATE_PLATFORM_LABELS[result.candidate.platform],
                sourceLabel:
                  CANDIDATE_PLATFORM_LABELS[result.candidate.platform],
              },
              result.receipt,
            );
            completed++;
            continue;
          }
          operation = await reviewLedger.begin(request, current);
          if (!current()) {
            reviewLedger.release(operation);
            return;
          }
          updateDraft(candidate, (old) => ({ ...old, pending: receipt }));
          const result = await candidateTimeout(
            service.reviewCandidate(request),
          );
          if (!current()) return;
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
            !sameReviewSnapshot(receipt.review, result.receipt.review) ||
            !(await matchingCandidateReceipt(operation, result.receipt))
          )
            throw new ServiceError(
              "RESULT_UNKNOWN",
              "服务结果尚不能确认，请核对本次复核。",
              408,
            );
          if (!current()) return;
          reviewLedger.release(operation);
          applyDecision(result.candidate, result.receipt);
          completed++;
        } catch (e) {
          if (!current()) return;
          if (operation && uncertainReview(e))
            updateDraft(candidate, (old) => ({
              ...old,
              pending: { ...receipt, status: "UNKNOWN" },
            }));
          else if (operation) {
            try {
              reviewLedger.release(operation);
            } catch (releaseError) {
              setError(errorMessage(releaseError));
              break;
            }
            updateDraft(candidate, (old) => ({ ...old, pending: undefined }));
          }
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
  const reconcileOperation = async (operation: CandidateReviewOperation) => {
    if (lock.current) return;
    const scope = scopeRef.current;
    const current = () => live.current && scopeRef.current === scope;
    lock.current = true;
    setBusy(operation.candidateId);
    setError("");
    try {
      const page = await candidateTimeout(
        service.candidates({
          ids: [operation.candidateId],
          reviewRequestId: operation.requestId,
          page: 1,
          pageSize: 1,
          ...(taskId ? { taskId } : {}),
        }),
      );
      if (!current()) return;
      const latest =
        page.taskId === (taskId || undefined) &&
        page.items.length === 1 &&
        page.items[0].id === operation.candidateId &&
        !candidateSample(page.items[0])
          ? page.items[0]
          : undefined;
      const receipt = latest?.lastReview;
      if (
        !latest ||
        !receipt ||
        !(await matchingCandidateReceipt(operation, receipt))
      ) {
        setError("尚未获得本次复核的确定结果，请稍后再次核对。");
        return;
      }
      if (!current()) return;
      if (completedCandidateReview(latest, receipt)) {
        reviewLedger.release(operation);
        applyDecision(latest, receipt);
        return;
      }
      if (receipt.status === "FAILED" && latest.status === "PENDING_REVIEW") {
        reviewLedger.release(operation);
        updateDraft(latest, (old) => ({ ...old, pending: undefined }));
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
      if (current()) setError(errorMessage(e));
    } finally {
      lock.current = false;
      if (live.current) setBusy(null);
    }
  };
  const reconcile = async (candidate: Candidate) => {
    const operation = reviewLedger.records.find(
      (record) => record.candidateId === candidate.id,
    );
    if (operation) return reconcileOperation(operation);
    const pending = getDraft(candidate).pending;
    // Legacy/server-only receipts must carry the original confirmed snapshot.
    if (!pending?.review) {
      setError("旧复核缺少原始确认版本，请在服务端核对；当前不能重新提交。");
      return;
    }
    try {
      const hash = await candidateReviewHash(pending.review);
      if (!live.current) return;
      return reconcileOperation({
        key: JSON.stringify([
          candidate.id,
          pending.action,
          pending.requestId,
          hash,
        ]),
        candidateId: candidate.id,
        action: pending.action,
        requestId: pending.requestId,
        reviewHash: hash,
      });
    } catch {
      if (live.current) setError("原始复核记录无效，请在服务端核对。");
    }
  };
  const openSource = async (candidate: Candidate) => {
    if (!candidate.url || sourceOpeningLock.current) return;
    const scope=scopeRef.current;
    sourceOpeningLock.current=true;setSourceOpening(true);
    try {
      if((candidate.platform==='XIAOHONGSHU' || candidate.platform===CANDIDATE_PLATFORM_LABELS.XIAOHONGSHU) && !candidate.sample){
        if(!service.openSourceView || !candidate.profileId || !candidate.strategyVersionId)throw new Error('请在最新版客户端中查看小红书原文。');
        const result=await service.openSourceView({candidateId:candidate.id,candidateRevision:candidate.revision,
          sourceVersionId:candidate.sourceVersionId,profileId:candidate.profileId,strategyVersionId:candidate.strategyVersionId});
        if(!live.current || scopeRef.current!==scope)return;
        if(result.state==='BUSY')throw new Error('平台正在使用中，请关闭原文窗口或等当前任务结束后再试。');
        if(result.state==='FAILED')throw new Error(result.error==='SOURCE_STOP_FAILED'?'原文窗口尚未关闭，请关闭后重启客户端。':'暂时无法定位这条原文，可稍后重试。');
        setOutcome({message:result.sourceKind==='COMMENT'?'已打开所属原帖，未定位该评论':'已打开原帖'});
      }else await service.openExternal(candidate.url);
    } catch (e) {
      if(live.current && scopeRef.current===scope)setError(errorMessage(e));
    } finally {
      sourceOpeningLock.current=false;if(live.current)setSourceOpening(false);
    }
  };
  const saveVerification = async (request: SourceVerificationRequest) => {
    const scope = scopeRef.current;
    const candidate = rowsRef.current.find(
      (row) => row.id === request.candidateId,
    );
    if (!candidate || candidate.historical || !candidate.currentBindingValid)
      return;
    const identity = candidateIdentity(candidate);
    setConfirmation(null);
    const result = await requests.submit(request);
    if (
      !live.current ||
      scopeRef.current !== scope ||
      result?.kind !== "sourceVerification"
    )
      return;
    if (!rowsRef.current.some((row) => candidateIdentity(row) === identity)) {
      setOutcome({
        message:
          "原核验请求已记录，候选版本已变化；未覆盖当前核验，请从原请求记录核对。",
      });
      return;
    }
    resource.setData(
      (old) =>
        old && {
          ...old,
          items: old.items.map((row) =>
            row.id === result.candidateId &&
            row.revision === result.binding.candidateRevision &&
            row.sourceVersionId === result.binding.sourceVersionId &&
            row.profileId === result.binding.profileId &&
            row.profileVersion === result.binding.profileVersion
              ? {
                  ...row,
                  sourceStatus: result.status,
                  sourceVerification: result,
                }
              : row,
          ),
        },
    );
  };
  const showRecovered = (result: CandidateReviewResultDto | null) => {
    if (!result) return;
    setError("");
    setOutcome(null);
    setConfirmation(null);
    if (result.kind === "decision") {
      setOutcome({
        message:
          "原请求已核对成功；以下列表重新读取当前版本，原回执不授权新版本操作。",
        opportunityId: result.receipt.opportunityId,
      });
      void resource.reload();
    } else if (
      result.kind === "assessment" ||
      result.kind === "sourceVerification"
    ) {
      setOutcome({
        message:
          "已找回原请求记录，正在读取当前版本；历史判断与核验不自动应用到新来源。",
      });
      void resource.reload();
    } else
      setError(
        result.kind === "failure"
          ? "原分析请求失败，可明确确认后重新判断。"
          : `原请求${result.status === "PROCESSING" ? "仍在处理" : "结果未知"}，未重新提交。`,
      );
  };
  const reconcileRequest = async (operation: CandidateRequestOperation) => {
    const scope = scopeRef.current;
    const result = await requests.reconcile(operation.key);
    if (!live.current || scopeRef.current !== scope || !result) return;
    if (taskId) {
      try {
        const page = await candidateTimeout(
          service.candidates({
            ids: [operation.candidateId],
            taskId,
            page: 1,
            pageSize: 1,
          }),
        );
        if (
          !live.current ||
          scopeRef.current !== scope ||
          page.taskId !== taskId ||
          page.items.length !== 1 ||
          page.items[0].id !== operation.candidateId ||
          candidateSample(page.items[0])
        )
          return;
      } catch (e) {
        if (live.current && scopeRef.current === scope) setError(errorMessage(e));
        return;
      }
    }
    showRecovered(result);
  };
  const currentBlockers = selected ? blockers(selected, "INCLUDE") : [];
  return (
    <>
      <PageHeader
        title={taskId ? `${task.data?.name || '本次采集'} · 发现线索` : "原始线索"}
        description="先核对原文与画像，再确认是否进入客户商机库。"
        back={() => navigate(taskId ? `/collection?task=${taskId}` : "/collection")}
      />
      {taskId && <Notice action={<Button variant="ghost" onClick={()=>navigate(`/collection?task=${taskId}`)}>返回采集任务</Button>}>
        本次任务发现的线索（展示最新内容）。
      </Notice>}
      {taskId && task.error && <Notice tone="warning">任务名称读取未完成；线索范围仍按当前任务编号核验。</Notice>}
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
            value={requestedId ? "" : platform}
            disabled={sample || !!requestedId}
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
            value={requestedId ? "" : status}
            disabled={sample || !!requestedId}
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
            disabled={sample || !!requestedId}
            value={requestedId ? "" : query}
            onChange={(e) => {
              setQuery(e.target.value);
              setPage(1);
            }}
          />
        </div>
      </div>
      {requestedId && (
        <Notice
          action={
            <Button variant="ghost" onClick={() => navigate("/candidates")}>
              查看全部线索
            </Button>
          }
        >
          当前仅查看待办关联的线索。
        </Notice>
      )}
      {!sample && !session.authenticated ? (
        <Empty
          title="登录后查看原始线索"
          action={<Button onClick={() => navigate("/login")}>登录</Button>}
        />
      ) : (
        <>
          {!sample && (
            <PendingCandidateReviews
              records={scopedReviewRecords}
              visibleIds={selected ? [selected.id] : []}
              busy={!!busy}
              onReconcile={(operation) => void reconcileOperation(operation)}
            />
          )}
          {!sample && requests.available && scopedRequestOperations.length > 0 && (
            <CandidateRequestHistory
              operations={scopedRequestOperations}
              busy={requests.busy || !!busy}
              onReconcile={(key) => {
                const operation = scopedRequestOperations.find(
                  (record) => record.key === key,
                );
                if (operation) void reconcileRequest(operation);
              }}
              onRetry={setRetryKey}
            />
          )}
          {!sample && hasUnscopedHistory && (
            <Notice
              action={
                <Button variant="ghost" onClick={() => navigate("/candidates")}>
                  前往全部线索核对
                </Button>
              }
            >
              其他线索有处理记录，可前往全部线索查看。
            </Notice>
          )}
          {!sample && requests.error && (
            <Notice tone="error">{requests.error}</Notice>
          )}
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
                        <SourcePlatform
                          platform={row.platform}
                          sourceLabel={row.sourceLabel}
                        />{" "}
                        · {formatDate(row.publishedAt)}
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
                      requestedId
                        ? "未找到待办关联的线索"
                        : query || platform || status !== "PENDING_REVIEW"
                          ? "没有符合条件的线索"
                          : "暂无待复核线索"
                    }
                    description={
                      requestedId
                        ? "线索可能已移除或当前账号无权查看，请返回全部线索核对。"
                        : "完成真实采集后，在这里核对原文与画像。"
                    }
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
                          <SourcePlatform
                            platform={selected.platform}
                            sourceLabel={selected.sourceLabel}
                          />
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
                      {liveCandidate(selected) && (
                        <Button
                          onClick={() => {
                            setConfirmation(null);
                            void resource.reload();
                          }}
                        >
                          刷新当前版本
                        </Button>
                      )}
                      <Button
                        variant="ghost"
                        disabled={!selected.url || sourceOpening}
                        onClick={() => void openSource(selected)}
                      >
                        查看原文 <ArrowSquareOut />
                      </Button>
                    </div>
                    {liveCandidate(selected) ? (
                      <>
                        <ResourceStatus
                          loading={original.loading}
                          error={original.error}
                          onRetry={original.reload}
                        />
                        {original.data && (
                          <CandidateOriginalEvidence evidence={original.data} />
                        )}
                        {original.error && (
                          <Notice tone="warning">
                            原文或绑定可能已变化，请刷新候选；不会用摘要替代缺失原文。
                            <Button onClick={() => void resource.reload()}>
                              读取当前候选
                            </Button>
                          </Notice>
                        )}
                        {selected.historical ||
                        !selected.currentBindingValid ? (
                          <Notice tone="warning">
                            当前是历史或失效绑定，只能查看。
                            <Button onClick={() => void resource.reload()}>
                              读取当前版本
                            </Button>
                          </Notice>
                        ) : null}
                      </>
                    ) : (
                      <blockquote className="evidence-quote">
                        {selected.excerpt || "原始摘录缺失，需补充证据。"}
                      </blockquote>
                    )}
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
                        ，请核对来源后再确认入库。
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
                              requests.busy ||
                              unresolvedRequest(selected) ||
                              !!editor?.pending ||
                              selected.status !== "PENDING_REVIEW"
                            }
                            value={editor?.profileId || ""}
                            onChange={(e) => {
                              const profile = confirmedProfiles.find(
                                (p) => p.id === e.target.value,
                              );
                              if (profile) {
                                if (liveCandidate(selected)) {
                                  setConfirmation(null);
                                  setReplaceAssessment(null);
                                  updateDraft(selected, (old) => ({
                                    ...old,
                                    profileId: profile.id,
                                  }));
                                } else requestAssessment(selected, profile);
                              }
                            }}
                          >
                            <option value="">选择已确认画像</option>
                            {confirmedProfiles.map((profile) => (
                              <option key={profile.id} value={profile.id}>
                                {profile.businessName || profile.fields.service || "业务画像"}
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
                              !selectedProfile ||
                              !!busy ||
                              requests.busy ||
                              unresolvedRequest(selected) ||
                              !!editor?.pending ||
                              (liveCandidate(selected) &&
                                (selected.historical ||
                                  !selected.currentBindingValid))
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
                        {liveCandidate(selected) && (
                          <>
                            <CandidateAssessmentDetails
                              assessment={
                                editor?.assessment as
                                  CandidateAssessmentDto | undefined
                              }
                              stale={
                                selected.assessmentStale ||
                                !selected.currentBindingValid ||
                                selected.historical ||
                                editor?.assessment?.profileId !==
                                  editor?.profileId
                              }
                            />
                            <CandidateSourceVerification
                              allowDemandEvidence={!!original.data && !original.loading && !original.error &&
                                original.data.candidate.candidate_id === selected.id &&
                                original.data.candidate.kind === "PAGE" &&
                                original.data.observations.items.some(item =>
                                  item.observation_id === original.data!.candidate.current_observation_id &&
                                  item.normalizer_version === "dynamic-public-read-v1" &&
                                  item.collector_version === "public-web-agent-v1")}
                              key={`${candidateIdentity(selected)}:${editor?.profileId}`}
                              binding={{
                                candidateId: selected.id,
                                candidateRevision: selected.revision,
                                sourceVersionId: selected.sourceVersionId,
                                profileId: selected.profileId!,
                                profileVersion: selected.profileVersion!,
                              }}
                              verification={selected.sourceVerification}
                              disabled={
                                !!busy ||
                                requests.busy ||
                                unresolvedRequest(selected) ||
                                selected.historical ||
                                !selected.currentBindingValid ||
                                selected.status !== "PENDING_REVIEW" ||
                                editor?.profileId !== selected.profileId
                              }
                              onChange={() => setConfirmation(null)}
                              onSubmit={saveVerification}
                            />
                          </>
                        )}
                        {editor?.assessment &&
                          selected.status === "PENDING_REVIEW" && (
                            <p className="field-hint">
                              判断建议 ·{" "}
                              {formatDate(editor.assessment.assessedAt)} ·
                              待人工校对
                            </p>
                          )}
                        {selected.status === "PENDING_REVIEW" &&
                        editor?.assessment ? (
                          <fieldset
                            className="profile-fieldset"
                            disabled={
                              !!busy ||
                              requests.busy ||
                              !!editor.pending ||
                              (liveCandidate(selected) &&
                                (selected.historical ||
                                  !selected.currentBindingValid))
                            }
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
                                  onChange={(e) => {
                                    setConfirmation(null);
                                    updateDraft(selected, (old) => ({
                                      ...old,
                                      evidence: {
                                        ...old.evidence,
                                        [key]: e.target.value,
                                      },
                                    }));
                                  }}
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
                                  requests.busy ||
                                  blockers(selected, "EXCLUDE").length > 0
                                }
                                onClick={() => prepare([selected], "EXCLUDE")}
                              >
                                排除
                              </Button>
                              <Button
                                variant="primary"
                                disabled={
                                  !!busy ||
                                  requests.busy ||
                                  currentBlockers.length > 0
                                }
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
      {retryKey && (
        <Confirm
          title="重新发起判断？"
          confirmText="核对后重新判断"
          loading={requests.busy}
          onCancel={() => setRetryKey(null)}
          onConfirm={() => {
            const key = retryKey;
            void requests.retryAssessment(key, true).then((result) => {
              setRetryKey(null);
              showRecovered(result);
            });
          }}
        >
          <p>
            先核对上次结果。仅失败或结果未知时重新判断，可能再次消耗用量；仍在处理时不重发。
          </p>
        </Confirm>
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
                    old
                      ? { ...old, reason: e.target.value, acknowledged: false }
                      : old,
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
