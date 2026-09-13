import type { StrategyExecutionLimitsDraft } from "../../domain/models";
import { validStrategyExecutionLimits } from "../../domain/strategyExecutionLimits";
import { Button, Field, Notice } from "../../components/ui";
import "./research-settings.css";

const SUGGESTED_LIMITS: StrategyExecutionLimitsDraft = {
  max_records: 100,
  max_runtime_seconds: 900,
};

export function StrategyExecutionLimits({ value, onChange }: {
  value?: StrategyExecutionLimitsDraft;
  onChange: (value: StrategyExecutionLimitsDraft) => void;
}) {
  const draftValue = value ?? {
    max_records: null,
    max_runtime_seconds: null,
  };
  const update = (
    key: keyof StrategyExecutionLimitsDraft,
    rawValue: string,
  ) => {
    onChange({
      ...draftValue,
      [key]: rawValue === "" ? null : Number(rawValue),
    });
  };

  return (
    <section className="research-settings" aria-label="处理范围">
      {!validStrategyExecutionLimits(value) && <>
        <p className="field-hint">请采用推荐设置，或展开高级设置调整处理范围。</p>
        <Button variant="ghost" onClick={() => onChange({ ...SUGGESTED_LIMITS })}>使用推荐设置</Button>
      </>}
      <details className="usage-advanced">
        <summary>
          高级设置：处理范围
        </summary>
        <Field label="最多处理记录数" className="usage-cap">
          <div className="soubei-input">
            <input
              type="number"
              aria-label="最多处理记录数"
              min={1}
              max={10_000}
              step={1}
              placeholder="建议 100"
              value={draftValue.max_records ?? ""}
              onChange={(event) => update("max_records", event.target.value)}
            />
            <span>条</span>
          </div>
        </Field>
        <Field label="最长运行秒数" className="usage-cap">
          <div className="soubei-input">
            <input
              type="number"
              aria-label="最长运行秒数"
              min={1}
              max={86_400}
              step={1}
              placeholder="建议 900"
              value={draftValue.max_runtime_seconds ?? ""}
              onChange={(event) =>
                update("max_runtime_seconds", event.target.value)
              }
            />
            <span>秒</span>
          </div>
        </Field>
        <Button
          variant="ghost"
          onClick={() => onChange({ ...SUGGESTED_LIMITS })}
        >
          采用建议执行上限
        </Button>
        {!validStrategyExecutionLimits(value) && (
          <Notice tone="warning">
            记录数需为 1 至 10,000 的整数，运行秒数需为 1 至 86,400 的整数。
          </Notice>
        )}
      </details>
    </section>
  );
}
