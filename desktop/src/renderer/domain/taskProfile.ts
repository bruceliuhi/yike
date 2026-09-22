import { z } from "zod";
import type { TaskRun } from "./models";

const identifier = z
  .string()
  .min(1)
  .max(512)
  .refine(
    (value) => value.trim() === value && !/[\u0000-\u001f\u007f]/.test(value),
  );
const version = z.number().int().positive().max(Number.MAX_SAFE_INTEGER);
const profileVersion = z.object({
  id: identifier,
  profileEntityId: identifier.optional(),
  version,
  status: z.enum(["DRAFT", "CONFIRMED", "REVOKED"]),
});
export type TaskProfileVersion = z.infer<typeof profileVersion>;
export type TaskProfileComparison =
  | { status: "UNKNOWN"; reason: string }
  | { status: "NO_CONFIRMED"; bound: TaskProfileVersion }
  | {
      status: "CURRENT" | "HISTORICAL";
      bound: TaskProfileVersion;
      current: TaskProfileVersion;
    };

function compareBoundProfile(
  bound: TaskProfileVersion,
  profiles: readonly TaskProfileVersion[],
): TaskProfileComparison {
  if (!bound.profileEntityId)
    return {
      status: "UNKNOWN",
      reason: "画像缺少业务实体关联，无法判断是否有新版本。",
    };
  const currentRows = profiles.filter(
    (row) =>
      row.profileEntityId === bound.profileEntityId &&
      row.status === "CONFIRMED",
  );
  if (!currentRows.length) return { status: "NO_CONFIRMED", bound };
  if (currentRows.length !== 1)
    return {
      status: "UNKNOWN",
      reason: "同一业务画像返回了多个已确认版本，请重新核对。",
    };
  const current = currentRows[0];
  if (current.id === bound.id && current.version === bound.version)
    return { status: "CURRENT", bound, current };
  if (bound.status !== "REVOKED" || current.version <= bound.version)
    return {
      status: "UNKNOWN",
      reason: "画像版本关系不一致，当前关系待核对。",
    };
  return { status: "HISTORICAL", bound, current };
}

export function parseTaskProfiles(value: unknown): TaskProfileVersion[] {
  const result = z.array(profileVersion).max(5000).safeParse(value);
  if (!result.success) throw new Error("画像版本响应不完整，当前关系待核对。");
  return result.data;
}

/** Compare a plan bound to a profile version row, as used by native monitors. */
export function compareTaskProfileVersion(
  profileVersionId: string,
  profiles: readonly TaskProfileVersion[],
): TaskProfileComparison {
  if (!identifier.safeParse(profileVersionId).success)
    return {
      status: "UNKNOWN",
      reason: "任务尚未返回完整的画像绑定，当前版本关系待核对。",
    };
  const boundRows = profiles.filter((row) => row.id === profileVersionId);
  if (boundRows.length !== 1)
    return {
      status: "UNKNOWN",
      reason: "未找到与任务绑定一致的画像版本，当前版本关系待核对。",
    };
  return compareBoundProfile(boundRows[0], profiles);
}

/** Compare only a proven entity lineage. Numeric versions are not globally ordered. */
export function compareTaskProfile(
  run: Pick<TaskRun, "profileId" | "profileVersion">,
  profiles: readonly TaskProfileVersion[],
): TaskProfileComparison {
  const profileId = run.profileId;
  const profileVersion = run.profileVersion;
  if (
    typeof profileId !== "string" ||
    !identifier.safeParse(profileId).success ||
    typeof profileVersion !== "number" ||
    !version.safeParse(profileVersion).success
  )
    return {
      status: "UNKNOWN",
      reason: "任务尚未返回完整的画像绑定，当前版本关系待核对。",
    };
  const comparison = compareTaskProfileVersion(profileId, profiles);
  if (
    (comparison.status === "CURRENT" || comparison.status === "HISTORICAL" ||
      comparison.status === "NO_CONFIRMED") &&
    comparison.bound.version !== profileVersion
  )
    return {
      status: "UNKNOWN",
      reason: "未找到与任务绑定一致的画像版本，当前版本关系待核对。",
    };
  return comparison;
}

export function taskProfileComparisonKey(
  value: TaskProfileComparison,
): string | null {
  return value.status === "HISTORICAL"
    ? JSON.stringify([
        value.bound.profileEntityId,
        value.bound.id,
        value.bound.version,
        value.current.id,
        value.current.version,
      ])
    : null;
}
