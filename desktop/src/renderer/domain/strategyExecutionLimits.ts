import type { TaskDraft } from "./models";

export type ValidStrategyExecutionLimits = {
  max_records: number;
  max_runtime_seconds: number;
};

export function validStrategyExecutionLimits(
  value: TaskDraft["executionLimits"],
): ValidStrategyExecutionLimits | null {
  if (!value) return null;
  const { max_records, max_runtime_seconds } = value;
  if (
    typeof max_records !== "number" ||
    !Number.isInteger(max_records) ||
    max_records < 1 ||
    max_records > 10_000 ||
    typeof max_runtime_seconds !== "number" ||
    !Number.isInteger(max_runtime_seconds) ||
    max_runtime_seconds < 1 ||
    max_runtime_seconds > 86_400
  ) {
    return null;
  }
  return { max_records, max_runtime_seconds };
}
