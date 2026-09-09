import { useEffect, useState } from "react";
import { Button, Field } from "../../components/ui";
import type { Opportunity } from "../../domain/models";
import {
  DEADLINE_FILTERS,
  deadlineText,
  libraryFactsFor,
  stageKey,
  type DeadlineFilter,
} from "../../domain/opportunityLibrary";
import "./opportunities.css";

export function libraryFactCells(row: Opportunity) {
  const state = libraryFactsFor(row);
  if (state.status !== "ready") {
    const label = state.status === "missing" ? "尚未提供" : "待核验";
    const title =
      state.status === "missing"
        ? "尚无结构化来源事实"
        : "事实格式或来源观察版本不一致，需重新核验";
    return {
      stage: (
        <span className="muted" title={title}>
          {label}
        </span>
      ),
      deadline: (
        <span className="muted" title={title}>
          {label}
        </span>
      ),
    };
  }
  const stage = state.facts.stage;
  const deadline = state.facts.materials_deadline;
  const date = deadline.status === "KNOWN" ? deadlineText(deadline.at) : null;
  return {
    stage: (
      <span
        title={
          stage.status === "KNOWN" ? stage.evidence_excerpt : "来源阶段尚待核验"
        }
      >
        {stage.status === "KNOWN" ? stage.label : "待核验"}
      </span>
    ),
    deadline:
      deadline.status === "KNOWN" && date ? (
        <time
          dateTime={deadline.at}
          title={`${date.full} · ${deadline.evidence_excerpt}`}
        >
          {date.short}
          <small>{date.zone}</small>
        </time>
      ) : (
        <span
          className="muted"
          title={
            deadline.status === "NOT_STATED"
              ? deadline.evidence_excerpt
              : "资料截止尚待核验"
          }
        >
          {deadline.status === "NOT_STATED" ? "来源未说明" : "待核验"}
        </span>
      ),
  };
}
export function useDeadlineClock() {
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(timer);
  }, []);
  return now;
}
export function LibraryFilters({
  rows,
  stage,
  deadline,
  sort,
  onStage,
  onDeadline,
  onSort,
  onReset,
  active,
}: {
  rows: Opportunity[];
  stage: string;
  deadline: DeadlineFilter;
  sort: string;
  onStage(value: string): void;
  onDeadline(value: DeadlineFilter): void;
  onSort(value: string): void;
  onReset(): void;
  active: boolean;
}) {
  const stageOptions = [
    ...new Set(rows.map(stageKey).filter((key) => key.startsWith("known:"))),
  ];
  if (stage.startsWith("known:") && !stageOptions.includes(stage))
    stageOptions.push(stage);
  return (
    <div className="opportunity-library-filters">
      <Field label="阶段">
        <select
          aria-label="筛选阶段"
          value={stage}
          onChange={(e) => onStage(e.target.value)}
        >
          <option value="all">全部</option>
          {stageOptions.map((key) => (
            <option key={key} value={key}>
              {key.slice(6)}
            </option>
          ))}
          <option value="missing">尚未提供</option>
          <option value="unverified">待核验</option>
        </select>
      </Field>
      <Field label="资料截止">
        <select
          aria-label="筛选资料截止"
          value={deadline}
          onChange={(e) => onDeadline(e.target.value as DeadlineFilter)}
        >
          {Object.entries(DEADLINE_FILTERS).map(([key, label]) => (
            <option key={key} value={key}>
              {label}
            </option>
          ))}
        </select>
      </Field>
      <Field label="排序">
        <select
          aria-label="排序方式"
          value={sort}
          onChange={(e) => onSort(e.target.value)}
        >
          <option value="updated">最近更新</option>
          <option value="deadline">资料截止最早</option>
          <option value="title">标题排序</option>
        </select>
      </Field>
      {active && (
        <Button variant="ghost" onClick={onReset}>
          重置筛选
        </Button>
      )}
    </div>
  );
}
