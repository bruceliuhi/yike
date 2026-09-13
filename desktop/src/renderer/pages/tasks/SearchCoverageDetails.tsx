import { useState } from "react";
import { Button, Notice, Tabs } from "../../components/ui";
import type {
  CoverageEvidence,
  CoverageUnit,
} from "../../domain/searchCoverage";
import { useApp } from "../../app/context";
import { boundedRequest } from "../../app/boundedRequest";
import { errorMessage } from "../../services/contracts";

export const coverageCount = (value: number | null) =>
  value === null ? "未知" : value.toLocaleString("zh-CN");

function Evidence({ rows }: { rows: CoverageEvidence[] }) {
  const { service } = useApp();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <>
      {error && <Notice tone="error">{error}</Notice>}
      {!rows.length ? (
        <p className="muted">尚无可展开的来源依据。</p>
      ) : (
        rows.map((row) => (
          <div className="coverage-evidence" key={row.id}>
            <blockquote>{row.excerpt}</blockquote>
            <p className="muted" style={{overflowWrap: "anywhere"}}>{row.url}</p>
            <Button
              variant="ghost"
              disabled={busy}
              onClick={async () => {
                setBusy(true);
                setError("");
                try {
                  await boundedRequest(() => service.openExternal(row.url), {
                    timeoutMessage: "打开来源超时，请稍后重试。",
                  });
                } catch (reason) {
                  setError(errorMessage(reason));
                } finally {
                  setBusy(false);
                }
              }}
            >
              打开原始来源
            </Button>
          </div>
        ))
      )}
    </>
  );
}

/** All quantities retain their own unit. No cross-phase or cross-platform sum. */
export function SearchCoverageDetails({ unit }: { unit: CoverageUnit }) {
  const [tab, setTab] = useState("exclusions");
  return (
    <section className="coverage-breakdown" aria-label="覆盖依据明细">
      <Tabs
        active={tab}
        onChange={setTab}
        items={[
          { key: "direction", label: "搜索方向" },
          { key: "exclusions", label: "排除明细" },
          { key: "evidence", label: "来源依据" },
        ]}
      />
      {tab === "direction" && (
        <>
          <h3>{unit.direction}</h3>
          <p>{unit.scope}</p>
          <dl className="coverage-counts">
            {(
              [
                ["请求次数", unit.counts.requests],
                ["原始内容", unit.counts.rawContents],
                ["重复内容", unit.counts.duplicates],
                ["独立来源", unit.counts.independentSources],
                ["新候选", unit.counts.newCandidates],
                ["已确认机会", unit.counts.confirmedOpportunities],
                ["待复核", unit.counts.pendingReviews],
              ] as const
            ).map(([label, value]) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd>{coverageCount(value)}</dd>
              </div>
            ))}
          </dl>
          <p className="muted">计数口径：{unit.countingBasis}</p>
        </>
      )}
      {tab === "exclusions" && (
        <>
          {!unit.exclusions.length ? (
            <p className="muted">尚无排除明细，不代表全部内容均已通过判断。</p>
          ) : (
            unit.exclusions.map((row) => (
              <details className="coverage-exclusion" key={row.id}>
                <summary>
                  <span>{row.reason}</span>
                  <span>{coverageCount(row.count)}</span>
                </summary>
                <p className="muted">
                  {row.phase === "DEDUPLICATION" ? "去重前处理" : "去重后筛选"}{" "}
                  ·{" "}
                  {row.overlapping
                    ? "可与其他分类重叠，不可相加"
                    : "本分类独立计数"}
                </p>
                <Evidence rows={row.evidence} />
              </details>
            ))
          )}
          <p className="coverage-hint">
            重复、过期与不匹配的口径分别记录；未知不计为
            0，未完成复核不计作排除。
          </p>
        </>
      )}
      {tab === "evidence" && <Evidence rows={unit.evidence} />}
    </section>
  );
}
