import { useEffect, useState } from "react";
import { Badge, Button, Empty, Notice, formatDate } from "../../components/ui";
import { PLATFORMS, type TaskRun } from "../../domain/models";
import { inDateRange, pageItems } from "./listState";
import { TaskPagination } from "./TaskPagination";
export function TaskEvents({ run }: { run: TaskRun }) {
  const [platform, setPlatform] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(10);
  useEffect(() => setPage(1), [platform, from, to, run.id]);
  const invalid = !!from && !!to && from > to;
  const events = (run.events || []).filter(
    (event) =>
      !invalid &&
      (!platform || event.platform === platform) &&
      inDateRange(event.occurredAt, from, to),
  );
  const pages = pageItems(events, page, size);
  return (
    <section aria-label="执行记录">
      <div className="section-heading">
        <h2>执行记录</h2>
        <span className="muted text-small">
          最近运行 {formatDate(run.lastRunAt || "")}
        </span>
      </div>
      {!!run.events?.length && (
        <div className="filter-bar">
          <label className="task-filter-field">
            平台
            <select
              aria-label="筛选执行记录平台"
              value={platform}
              onChange={(e) => setPlatform(e.target.value)}
            >
              <option value="">全部平台</option>
              {PLATFORMS.filter((p) => run.platforms.includes(p.id)).map(
                (p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ),
              )}
            </select>
          </label>
          <label className="task-filter-field">
            发生日期
            <input
              type="date"
              aria-label="记录开始日期"
              value={from}
              onChange={(e) => setFrom(e.target.value)}
            />
          </label>
          <label className="task-filter-field">
            至
            <input
              type="date"
              aria-label="记录结束日期"
              value={to}
              onChange={(e) => setTo(e.target.value)}
            />
          </label>
          {(platform || from || to) && (
            <Button
              variant="ghost"
              onClick={() => {
                setPlatform("");
                setFrom("");
                setTo("");
              }}
            >
              清除记录筛选
            </Button>
          )}
        </div>
      )}
      {invalid && <Notice tone="error">开始日期不能晚于结束日期。</Notice>}
      {events.length ? (
        <div className="table-scroll">
          <table className="monitor-events-table">
            <thead>
              <tr>
                <th>时间</th>
                <th>平台</th>
                <th>事件</th>
                <th>级别</th>
              </tr>
            </thead>
            <tbody>
              {pages.items.map((event, index) => (
                <tr key={`${event.id}:${index}`}>
                  <td>{formatDate(event.occurredAt || "")}</td>
                  <td>
                    {event.platform
                      ? PLATFORMS.find((p) => p.id === event.platform)?.name ||
                        event.platform
                      : "任务"}
                  </td>
                  <td>{event.message}</td>
                  <td>
                    {event.level ? (
                      <Badge
                        tone={
                          event.level === "error"
                            ? "red"
                            : event.level === "warning"
                              ? "orange"
                              : "neutral"
                        }
                      >
                        {event.level === "error"
                          ? "错误"
                          : event.level === "warning"
                            ? "提醒"
                            : "信息"}
                      </Badge>
                    ) : (
                      "—"
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <Empty
          title={run.events?.length ? "没有匹配记录" : "暂无运行记录"}
          description={
            run.events?.length
              ? "调整平台或发生日期筛选。"
              : "执行服务返回阶段和事件后，会在这里展示。"
          }
        />
      )}
      <TaskPagination
        page={pages.page}
        pages={pages.pages}
        total={events.length}
        pageSize={size}
        onPage={setPage}
        onPageSize={(value) => {
          setSize(value);
          setPage(1);
        }}
      />
    </section>
  );
}
