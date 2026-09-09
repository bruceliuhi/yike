import type { Opportunity } from "./models";

export type ContactSort = "newest" | "oldest" | "title";

export function sortContactRows(rows: Opportunity[], order: ContactSort) {
  return [...rows].sort((a, b) => {
    if (order !== "title") {
      const left = Date.parse(a.updatedAt);
      const right = Date.parse(b.updatedAt);
      if (Number.isFinite(left) !== Number.isFinite(right))
        return Number.isFinite(left) ? -1 : 1;
      if (Number.isFinite(left) && left !== right)
        return order === "newest" ? right - left : left - right;
    }
    return a.title.localeCompare(b.title, "zh-CN") || a.id.localeCompare(b.id);
  });
}
