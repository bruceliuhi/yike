export function inDateRange(
  value: string | null | undefined,
  from: string,
  to: string,
) {
  if (!from && !to) return true;
  const timestamp = Date.parse(value || "");
  if (!Number.isFinite(timestamp)) return false;
  const start = from ? new Date(`${from}T00:00:00`).getTime() : -Infinity;
  const end = to ? new Date(`${to}T23:59:59.999`).getTime() : Infinity;
  return timestamp >= start && timestamp <= end;
}
export function pageItems<T>(items: T[], requested: number, size: number) {
  const pages = Math.max(1, Math.ceil(items.length / size));
  const page = Math.min(Math.max(1, requested), pages);
  return { page, pages, items: items.slice((page - 1) * size, page * size) };
}
