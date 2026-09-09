// @vitest-environment jsdom
import { useState } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { taskDraftSchema } from "../../src/renderer/app/taskDraft";
import {
  newTaskDraft,
  type StrategyExecutionLimitsDraft,
} from "../../src/renderer/domain/models";
import { validStrategyExecutionLimits } from "../../src/renderer/domain/strategyExecutionLimits";
import { StrategyExecutionLimits } from "../../src/renderer/pages/tasks/StrategyExecutionLimits";

afterEach(cleanup);

function Editor({ initial }: { initial?: StrategyExecutionLimitsDraft }) {
  const [value, setValue] = useState(initial);
  return (
    <>
      <StrategyExecutionLimits value={value} onChange={setValue} />
      <output aria-label="当前执行保护上限">
        {value === undefined ? "undefined" : JSON.stringify(value)}
      </output>
    </>
  );
}

describe("strategy execution limit draft storage", () => {
  it("keeps legacy and new drafts unconfirmed until the user explicitly chooses limits", () => {
    const legacy = newTaskDraft();

    expect(legacy).not.toHaveProperty("executionLimits");
    expect(taskDraftSchema.parse(legacy)).toEqual(legacy);
  });

  it("preserves finite incomplete values and nulls instead of rewriting the draft", () => {
    const incomplete = {
      ...newTaskDraft(),
      executionLimits: {
        max_records: 10_000.5,
        max_runtime_seconds: null,
      },
    };

    expect(taskDraftSchema.parse(incomplete)).toEqual(incomplete);
  });

  it.each([Number.NaN, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY])(
    "rejects a non-finite draft limit: %s",
    (invalid) => {
      const draft = {
        ...newTaskDraft(),
        executionLimits: {
          max_records: invalid,
          max_runtime_seconds: 900,
        },
      };

      expect(taskDraftSchema.safeParse(draft).success).toBe(false);
    },
  );
});

describe("strategy execution limit editor", () => {
  it("shows unconfirmed suggested values and adopts them only after an explicit action", () => {
    render(<Editor />);
    fireEvent.click(screen.getByText("执行保护上限"));

    const records = screen.getByRole("spinbutton", {
      name: "最多处理记录数",
    }) as HTMLInputElement;
    const seconds = screen.getByRole("spinbutton", {
      name: "最长运行秒数",
    }) as HTMLInputElement;
    expect(records.value).toBe("");
    expect(seconds.value).toBe("");
    expect(records.placeholder).toContain("100");
    expect(seconds.placeholder).toContain("900");
    expect(screen.getByLabelText("当前执行保护上限").textContent).toBe(
      "undefined",
    );
    expect(screen.getByText(/不是搜贝上限/).textContent).toMatch(
      /不是研究来源、时长或模型调用硬上限/,
    );

    fireEvent.click(
      screen.getByRole("button", { name: "采用建议执行上限" }),
    );
    expect(records.value).toBe("100");
    expect(seconds.value).toBe("900");
    expect(screen.getByLabelText("当前执行保护上限").textContent).toBe(
      '{"max_records":100,"max_runtime_seconds":900}',
    );
  });

  it("keeps both inputs independent and preserves an empty input as null", () => {
    render(
      <Editor initial={{ max_records: 25, max_runtime_seconds: 1_200 }} />,
    );
    fireEvent.click(screen.getByText("执行保护上限"));
    const records = screen.getByRole("spinbutton", {
      name: "最多处理记录数",
    }) as HTMLInputElement;
    const seconds = screen.getByRole("spinbutton", {
      name: "最长运行秒数",
    }) as HTMLInputElement;

    expect(records.min).toBe("1");
    expect(records.max).toBe("10000");
    expect(records.step).toBe("1");
    expect(seconds.min).toBe("1");
    expect(seconds.max).toBe("86400");
    expect(seconds.step).toBe("1");
    fireEvent.change(records, { target: { value: "" } });
    expect(seconds.value).toBe("1200");
    expect(screen.getByLabelText("当前执行保护上限").textContent).toBe(
      '{"max_records":null,"max_runtime_seconds":1200}',
    );
    fireEvent.change(seconds, { target: { value: "86401" } });
    expect(records.value).toBe("");
    expect(screen.getByText(/1 至 86,400 的整数/)).toBeTruthy();
  });
});

describe("strategy execution limit wire validation", () => {
  it.each([
    [{ max_records: 1, max_runtime_seconds: 1 }, { max_records: 1, max_runtime_seconds: 1 }],
    [
      { max_records: 10_000, max_runtime_seconds: 86_400 },
      { max_records: 10_000, max_runtime_seconds: 86_400 },
    ],
  ] as const)("accepts inclusive integer boundaries", (draftValue, expected) => {
    expect(validStrategyExecutionLimits(draftValue)).toEqual(expected);
  });

  it.each([
    undefined,
    { max_records: null, max_runtime_seconds: 900 },
    { max_records: 0, max_runtime_seconds: 900 },
    { max_records: 10_001, max_runtime_seconds: 900 },
    { max_records: 1.5, max_runtime_seconds: 900 },
    { max_records: 100, max_runtime_seconds: null },
    { max_records: 100, max_runtime_seconds: 0 },
    { max_records: 100, max_runtime_seconds: 86_401 },
    { max_records: 100, max_runtime_seconds: 1.5 },
  ])("rejects incomplete or out-of-range limits: %j", (value) => {
    expect(validStrategyExecutionLimits(value)).toBeNull();
  });
});
