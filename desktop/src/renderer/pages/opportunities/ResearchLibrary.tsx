import { useEffect, useMemo, useRef, useState } from "react";
import { MagnifyingGlass, DownloadSimple } from "@phosphor-icons/react";
import { useApp } from "../../app/context";
import { useResource } from "../../app/hooks";
import { boundedRequest } from "../../app/boundedRequest";
import {
  Badge,
  Button,
  Empty,
  Field,
  Notice,
  PageHeader,
  Pagination,
  ResourceStatus,
  Tabs,
} from "../../components/ui";
import { PlatformLabel } from "../../components/Platform";
import {
  hasResearchScope,
  parseResearchCollection,
  RESEARCH_CATEGORIES,
  type ResearchCategory,
  type ResearchRecord,
} from "../../domain/opportunityResearch";
import {
  customerCsv,
  PUBLIC_SAMPLE,
  opportunityStatus,
} from "./OpportunityEvidence";
import { downloadText, downloadErrorMessage } from "../../services/download";
import { errorMessage } from "../../services/contracts";
import {
  compareDeadlines,
  deadlineFilter,
  matchesLibraryFilters,
} from "../../domain/opportunityLibrary";
import {
  LibraryFilters,
  libraryFactCells,
  useDeadlineClock,
} from "./LibraryFacts";
import "./research.css";

export const SAMPLE_RESEARCH: ResearchRecord = {
  opportunity: PUBLIC_SAMPLE,
  classification: {
    category: "OPPORTUNITY",
    type: "预算询价",
    reason: "预算询价不等于正式采购或已确认商机。",
    ruleVersion: "public-example-v1",
    evidence: [
      {
        sourceUrl: PUBLIC_SAMPLE.url,
        evidenceVersion: PUBLIC_SAMPLE.sourceEvidenceVersion!,
        quote: PUBLIC_SAMPLE.excerpt,
      },
    ],
    review: { status: "PENDING", reviewer: "", reviewedAt: null },
  },
};
const REVIEW = {
  PENDING: "待复核",
  RECOGNIZED: "已认可",
  NEEDS_EVIDENCE: "待补证",
};
export function ResearchLibrary() {
  const { service, session, route, navigate, notify } = useApp();
  const sample = route.query.get("scope") === "sample";
  const [category, setCategory] = useState<ResearchCategory>(() =>
    Object.hasOwn(RESEARCH_CATEGORIES, route.query.get("category") || "")
      ? (route.query.get("category") as ResearchCategory)
      : "OPPORTUNITY",
  );
  const [query, setQuery] = useState(route.query.get("q") || "");
  const [platform, setPlatform] = useState(route.query.get("platform") || "");
  const [type, setType] = useState(route.query.get("type") || "");
  const [review, setReview] = useState(route.query.get("review") || "");
  const [stage, setStage] = useState(route.query.get("stage") || "all");
  const [deadline, setDeadline] = useState(
    deadlineFilter(route.query.get("deadline")),
  );
  const [sort, setSort] = useState(route.query.get("sort") || "updated");
  const [page, setPage] = useState(Number(route.query.get("page")) || 1);
  const [selectedId, setSelectedId] = useState(
    route.query.get("selected") || "",
  );
  const [checked, setChecked] = useState<string[]>([]);
  const [exporting, setExporting] = useState(false);
  const active = useRef({ user: session.userId, sample });
  active.current = { user: session.userId, sample };
  const exportingRef = useRef(false);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  const now = useDeadlineClock();
  const resource = useResource(async () => {
    if (sample || !session.authenticated || !session.userId) return null;
    if (!hasResearchScope(session.accountScope))
      throw new Error("当前账户空间尚未核验，研究服务暂不可用。");
    if (!service.opportunityResearch)
      throw new Error("需求分类与观察服务尚未接通。");
    const data = await boundedRequest(
      (signal) => service.opportunityResearch!.list(signal),
      { timeoutMessage: "研究分类读取超时，请重试。" },
    );
    return parseResearchCollection(
      data,
      session.userId,
      Date.now(),
      session.accountScope,
    );
  }, [
    service,
    session.userId,
    session.authenticated,
    JSON.stringify(session.accountScope),
    sample,
  ]);
  const records = sample ? [SAMPLE_RESEARCH] : resource.data?.records || [];
  const stale =
    !sample &&
    Boolean(resource.data && Date.parse(resource.data.expiresAt) <= now);
  const filtered = useMemo(
    () =>
      records
        .filter(
          ({ opportunity: r, classification: c }) =>
            c.category === category &&
            (!query ||
              [r.title, r.buyer, r.excerpt]
                .join(" ")
                .toLowerCase()
                .includes(query.trim().toLowerCase())) &&
            (!platform || r.platform === platform) &&
            (!type || c.type === type) &&
            (!review || c.review.status === review) &&
            matchesLibraryFilters(r, stage, deadline, now),
        )
        .sort((a, b) =>
          sort === "deadline"
            ? compareDeadlines(a.opportunity, b.opportunity)
            : sort === "title"
              ? a.opportunity.title.localeCompare(b.opportunity.title, "zh-CN")
              : (Date.parse(
                  b.opportunity.updatedAt || b.opportunity.publishedAt,
                ) || 0) -
                (Date.parse(
                  a.opportunity.updatedAt || a.opportunity.publishedAt,
                ) || 0),
        ),
    [
      records,
      category,
      query,
      platform,
      type,
      review,
      stage,
      deadline,
      now,
      sort,
    ],
  );
  const currentPage = Math.min(
    Math.max(1, page),
    Math.max(1, Math.ceil(filtered.length / 10)),
  );
  const visible = filtered.slice((currentPage - 1) * 10, currentPage * 10);
  const selected =
    filtered.find((r) => r.opportunity.id === selectedId) || visible[0];
  const changeCategory = (value: string) => {
    setCategory(value as ResearchCategory);
    setType("");
    setPage(1);
    setChecked([]);
  };
  const open = (record: ResearchRecord) => {
    const back = new URLSearchParams({
      scope: sample ? "sample" : "customer",
      category,
      q: query,
      platform,
      type,
      review,
      stage,
      deadline,
      sort,
      page: String(currentPage),
      selected: record.opportunity.id,
    });
    navigate(
      `/opportunities/${encodeURIComponent(record.opportunity.id)}?returnTo=${encodeURIComponent("/opportunities?" + back)}`,
    );
  };
  const exportSelected = async () => {
    if (
      sample ||
      stale ||
      !session.authenticated ||
      resource.loading ||
      resource.error ||
      exportingRef.current
    )
      return;
    const rows = records
      .filter(
        (r) =>
          checked.includes(r.opportunity.id) &&
          r.classification.category === "OPPORTUNITY",
      )
      .map((r) => r.opportunity);
    if (!rows.length) return;
    const identity = active.current;
    exportingRef.current = true;
    setExporting(true);
    try {
      const result = await downloadText({
        format: "csv",
        name: "意客AI-客户商机.csv",
        content: customerCsv(rows),
      });
      if (
        !mounted.current ||
        active.current.user !== identity.user ||
        active.current.sample !== identity.sample
      )
        return;
      if (result.status === "saved")
        notify(`已保存 ${rows.length} 条选中客户商机。`, "success");
      else if (result.status === "initiated")
        notify("已发起文件下载，请在浏览器中确认。");
      else if (result.status === "error")
        notify(downloadErrorMessage(result.error), "error");
    } catch (e) {
      if (mounted.current && active.current.user === identity.user)
        notify(errorMessage(e), "error");
    } finally {
      exportingRef.current = false;
      if (mounted.current) setExporting(false);
    }
  };
  return (
    <>
      <PageHeader
        title="商机库"
        description="区分明确需求与业务变化，先看依据再跟进。"
      />
      <Tabs
        active={sample ? "sample" : "customer"}
        items={[
          { key: "customer", label: "客户商机" },
          { key: "sample", label: "公开研究样例" },
        ]}
        onChange={(key) =>
          navigate("/opportunities" + (key === "sample" ? "?scope=sample" : ""))
        }
      />
      <Tabs
        active={category}
        items={Object.entries(RESEARCH_CATEGORIES)
          .filter(
            ([key]) =>
              key !== "UNASSESSED" ||
              records.some((r) => r.classification.category === "UNASSESSED"),
          )
          .map(([key, label]) => ({ key, label }))}
        onChange={changeCategory}
      />
      {!sample && !session.authenticated ? (
        <Empty
          title="登录后查看客户商机"
          action={<Button onClick={() => navigate("/login")}>登录</Button>}
        />
      ) : (
        <>
          {!sample && (
            <ResourceStatus
              loading={resource.loading}
              error={resource.error}
              onRetry={resource.reload}
            />
          )}
          {stale && (
            <Notice tone="warning">
              研究快照已过期，请刷新后继续。
              <Button onClick={resource.reload}>刷新</Button>
            </Notice>
          )}
          {(sample || (!resource.loading && !resource.error && !stale)) && (
            <div className="research-library-layout">
              <section className="research-library-main">
                <div className="research-filter-row">
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
                      {[
                        ...new Set(records.map((r) => r.opportunity.platform)),
                      ].map((p) => (
                        <option key={p}>{p}</option>
                      ))}
                    </select>
                  </Field>
                  <Field label="需求类型">
                    <select
                      aria-label="筛选需求类型"
                      value={type}
                      onChange={(e) => {
                        setType(e.target.value);
                        setPage(1);
                      }}
                    >
                      <option value="">全部</option>
                      {[
                        ...new Set(
                          records
                            .filter(
                              (r) => r.classification.category === category,
                            )
                            .map((r) => r.classification.type)
                            .filter(Boolean),
                        ),
                      ].map((t) => (
                        <option key={t}>{t}</option>
                      ))}
                    </select>
                  </Field>
                  <Field label="复核状态">
                    <select
                      aria-label="筛选复核状态"
                      value={review}
                      onChange={(e) => {
                        setReview(e.target.value);
                        setPage(1);
                      }}
                    >
                      <option value="">全部</option>
                      {Object.entries(REVIEW).map(([value, label]) => (
                        <option key={value} value={value}>
                          {label}
                        </option>
                      ))}
                    </select>
                  </Field>
                </div>
                <LibraryFilters
                  rows={records.map((r) => r.opportunity)}
                  stage={stage}
                  deadline={deadline}
                  sort={sort}
                  onStage={setStage}
                  onDeadline={setDeadline}
                  onSort={setSort}
                  active={Boolean(
                    query ||
                    platform ||
                    type ||
                    review ||
                    stage !== "all" ||
                    deadline !== "all" ||
                    sort !== "updated",
                  )}
                  onReset={() => {
                    setQuery("");
                    setPlatform("");
                    setType("");
                    setReview("");
                    setStage("all");
                    setDeadline("all");
                    setSort("updated");
                    setPage(1);
                  }}
                />
                <div className="table-wrap">
                  <table className="data-table research-table">
                    <thead>
                      <tr>
                        <th>
                          <input
                            type="checkbox"
                            aria-label="选择本页客户商机"
                            disabled={
                              sample ||
                              category !== "OPPORTUNITY" ||
                              !visible.length
                            }
                            checked={
                              !sample &&
                              visible.length > 0 &&
                              visible.every((r) =>
                                checked.includes(r.opportunity.id),
                              )
                            }
                            onChange={(e) =>
                              setChecked(
                                e.target.checked
                                  ? [
                                      ...new Set([
                                        ...checked,
                                        ...visible.map((r) => r.opportunity.id),
                                      ]),
                                    ]
                                  : checked.filter(
                                      (id) =>
                                        !visible.some(
                                          (r) => r.opportunity.id === id,
                                        ),
                                    ),
                              )
                            }
                          />
                        </th>
                        <th>需求与来源</th>
                        <th>需求类型</th>
                        <th>复核状态</th>
                        <th>下一步</th>
                      </tr>
                    </thead>
                    <tbody>
                      {visible.map((record) => (
                        <tr
                          key={record.opportunity.id}
                          className={record === selected ? "is-selected" : ""}
                        >
                          <td>
                            <input
                              type="checkbox"
                              aria-label={`选择${record.opportunity.title}`}
                              disabled={sample || category !== "OPPORTUNITY"}
                              checked={
                                !sample &&
                                checked.includes(record.opportunity.id)
                              }
                              onChange={(e) =>
                                setChecked(
                                  e.target.checked
                                    ? [
                                        ...new Set([
                                          ...checked,
                                          record.opportunity.id,
                                        ]),
                                      ]
                                    : checked.filter(
                                        (id) => id !== record.opportunity.id,
                                      ),
                                )
                              }
                            />
                          </td>
                          <td>
                            <strong>{record.opportunity.title}</strong>
                            <small>
                              <PlatformLabel
                                platform={record.opportunity.platform}
                                size={16}
                              />
                            </small>
                            <small className="muted">
                              {sample ? (
                                "公开研究样例 · 未入客户库"
                              ) : (
                                <>
                                  {libraryFactCells(record.opportunity).stage} ·{" "}
                                  {opportunityStatus(record.opportunity)}
                                </>
                              )}
                            </small>
                          </td>
                          <td>{record.classification.type || "尚未判断"}</td>
                          <td>
                            <Badge
                              tone={
                                record.classification.review.status ===
                                "RECOGNIZED"
                                  ? "blue"
                                  : "orange"
                              }
                            >
                              {REVIEW[record.classification.review.status]}
                            </Badge>
                          </td>
                          <td>
                            <Button
                              variant="ghost"
                              onClick={() =>
                                setSelectedId(record.opportunity.id)
                              }
                            >
                              查看证据
                            </Button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {!visible.length && (
                  <Empty
                    title={`暂无符合条件的${RESEARCH_CATEGORIES[category]}记录`}
                    description={
                      category === "OBSERVATION"
                        ? "仅有业务变化时保留观察，获得需求证据并经人工确认后再升级。"
                        : undefined
                    }
                  />
                )}
                <div className="table-footer">
                  <Button
                    disabled={
                      sample ||
                      category !== "OPPORTUNITY" ||
                      !checked.length ||
                      exporting
                    }
                    onClick={() => void exportSelected()}
                  >
                    <DownloadSimple />
                    {exporting ? "正在保存…" : "导出所选客户商机"}
                  </Button>
                  <Pagination
                    page={currentPage}
                    total={filtered.length}
                    onChange={setPage}
                  />
                </div>
              </section>
              <aside className="research-evidence-summary">
                <h2>判断依据</h2>
                {selected ? (
                  <>
                    {selected.classification.evidence.map((q, i) => (
                      <blockquote className="evidence-quote" key={i}>
                        {q.quote}
                      </blockquote>
                    ))}
                    <h3>已知</h3>
                    {sample ? (
                      <dl className="detail-list">
                        <div>
                          <dt>项目范围</dt>
                          <dd>180㎡</dd>
                        </div>
                        <div>
                          <dt>资料截止</dt>
                          <dd>
                            {libraryFactCells(selected.opportunity).deadline}
                          </dd>
                        </div>
                      </dl>
                    ) : (
                      <p>{selected.classification.reason}</p>
                    )}
                    <h3>未知</h3>
                    <p className="muted">
                      {sample
                        ? "实际采购预算、技术资料获取方式"
                        : selected.opportunity.risk || "其他事实仍需逐项核验。"}
                    </p>
                    <Notice>
                      {sample
                        ? SAMPLE_RESEARCH.classification.reason
                        : `分类：${RESEARCH_CATEGORIES[selected.classification.category]}；复核：${REVIEW[selected.classification.review.status]}。`}
                    </Notice>
                    <Button onClick={() => open(selected)}>查看完整证据</Button>
                    {sample && (
                      <p className="muted">
                        公开研究样例仅供查看，不可转入客户商机。
                      </p>
                    )}
                  </>
                ) : (
                  <p className="muted">选择记录查看分类证据。</p>
                )}
              </aside>
            </div>
          )}
          <section className="research-observation-note">
            <div>
              <h2>观察池接收什么</h2>
              <p>
                开店、扩产、参展等业务变化，尚无明确采购表达时先观察并补证。
              </p>
            </div>
            <Button
              variant="ghost"
              onClick={() => changeCategory("OBSERVATION")}
            >
              查看观察池
            </Button>
          </section>
        </>
      )}
    </>
  );
}
