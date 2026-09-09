function record(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value);
}
function task(value: unknown): boolean {
  if (!record(value) || typeof value.id !== "string" || !value.id) return false;
  return (
    (typeof value.revision === "number" && value.revision > 1) ||
    ["name", "profileId", "links", "savedAt"].some(
      (field) => typeof value[field] === "string" && !!value[field].trim(),
    ) ||
    ["terms", "exclusions", "platforms"].some(
      (field) => Array.isArray(value[field]) && value[field].length > 0,
    )
  );
}

/** Only identifies loss risk; never authorizes a task or restores invalid data. */
export function sessionTaskContentAtRisk(key: string, value: unknown): boolean {
  if (key.startsWith("task.")) return task(value);
  if (key.startsWith("task-library.")) return Array.isArray(value) && value.some(task);
  if (key.startsWith("task-templates."))
    return Array.isArray(value) && value.some((item) =>
      record(item) && typeof item.id === "string" && !!item.id,
    );
  return false;
}
