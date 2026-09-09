import { Button } from "../../components/ui";
export function TaskPagination({
  page,
  pages,
  total,
  pageSize,
  onPage,
  onPageSize,
}: {
  page: number;
  pages: number;
  total: number;
  pageSize: number;
  onPage: (page: number) => void;
  onPageSize: (size: number) => void;
}) {
  if (!total) return null;
  return (
    <nav className="task-pagination" aria-label="任务分页">
      <span>共 {total} 项</span>
      <div className="task-pagination-controls">
        <label className="task-page-size">
          <span>每页</span>
          <select
            aria-label="每页任务数"
            value={pageSize}
            onChange={(e) => onPageSize(Number(e.target.value))}
          >
            {[10, 20, 50].map((size) => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </select>
          <span>项</span>
        </label>
        <Button disabled={page <= 1} onClick={() => onPage(page - 1)}>
          上一页
        </Button>
        <span aria-live="polite">
          第 {page} / {pages} 页
        </span>
        <Button disabled={page >= pages} onClick={() => onPage(page + 1)}>
          下一页
        </Button>
      </div>
    </nav>
  );
}
