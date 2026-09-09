import { sessionTaskContentAtRisk } from "./sessionTaskContent";

function record(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value);
}
function text(value: unknown): value is string {
  return typeof value === "string";
}

/** Detect ephemeral user work only; this never validates or authorizes business data. */
export function sessionContentAtRisk(key: string, value: unknown, written = false): boolean {
  if (sessionTaskContentAtRisk(key, value)) return true;
  if (key.startsWith("materials."))
    return Array.isArray(value) && value.some((item) =>
      record(item) && text(item.name) && !!item.name.trim() &&
      text(item.text) && !!item.text.trim(),
    );
  if (key.startsWith("profile.") && record(value) &&
      record(value.fields) && record(value.baseline)) {
    const fields = value.fields, baseline = value.baseline;
    return ["service", "customer", "regions", "preference", "exclusions"].some(
      (field) => text(fields[field]) && text(baseline[field]) &&
        fields[field] !== baseline[field],
    );
  }
  if (key.startsWith("contact-note:")) return text(value) && !!value.trim();
  if (key.startsWith("contact:") && record(value))
    return [value.comment, value.dm].some((draft) =>
      record(draft) && text(draft.content) && text(draft.savedContent) &&
      draft.content !== draft.savedContent,
    );
  // Follow-up editors start from a server record when correcting. Merely
  // opening one puts that initial value in memory; only explicit writes (or
  // previously persisted drafts) are ephemeral work. Clearing after submission
  // removes both the value and this write marker.
  if (key.startsWith("followup:v3:") && written && record(value))
    return ["opportunityId", "status", "note", "contact", "nextStep", "nextDate", "ownerId", "reason"].every(
      (field) => text(value[field]),
    );
  return false;
}
