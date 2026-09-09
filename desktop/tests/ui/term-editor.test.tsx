// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { TermEditor } from "../../src/renderer/components/TermEditor";
import { makeTerm } from "../../src/renderer/domain/task";

afterEach(cleanup);

function editor(values: string[] = []) {
  const changed = vi.fn();
  render(<TermEditor label="搜索关键词" terms={values.map((v) => makeTerm(v))} onChange={changed} onRemove={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: "添加" }));
  return { input: screen.getByRole("textbox", { name: "新增搜索关键词" }) as HTMLInputElement, changed };
}
function paste(input: HTMLInputElement, text: string) {
  return fireEvent.paste(input, { clipboardData: { getData: (format: string) => format === "text/plain" ? text : "" } });
}

describe("multiline keyword paste", () => {
  it("keeps CRLF, LF and CR word boundaries, deduplicates and commits only on confirmation", () => {
    const { input, changed } = editor(["展台搭建"]);
    expect(paste(input, "展台搭建\r\n展区设计\n展台报价\r展区设计")).toBe(false);
    expect(input.value).toBe("展台搭建, 展区设计, 展台报价, 展区设计");
    expect(changed).not.toHaveBeenCalled();
    fireEvent.keyDown(input, { key: "Enter" });
    expect(changed).toHaveBeenCalledTimes(1);
    expect(changed.mock.calls[0][0].map((term: { value: string }) => term.value)).toEqual(["展台搭建", "展区设计", "展台报价"]);
  });
  it("replaces only the selected range and places the caret after the pasted words", () => {
    const { input, changed } = editor();
    fireEvent.change(input, { target: { value: "原词, 替换这里, 后词" } });
    input.setSelectionRange(4, 8);
    paste(input, "新词一\n新词二");
    expect(input.value).toBe("原词, 新词一, 新词二, 后词");
    expect(input.selectionStart).toBe(12);
    expect(input.selectionEnd).toBe(12);
    fireEvent.keyDown(input, { key: "Enter" });
    expect(changed.mock.calls[0][0].map((term: { value: string }) => term.value)).toEqual(["原词", "新词一", "新词二", "后词"]);
  });
  it("collapses the selection after a multiline paste even when its normalized text is unchanged", () => {
    const { input, changed } = editor();
    fireEvent.change(input, { target: { value: "设计, 搭建" } });
    input.setSelectionRange(0, input.value.length);
    paste(input, "设计\n搭建");
    expect(input.value).toBe("设计, 搭建");
    expect(input.selectionStart).toBe(input.value.length);
    expect(input.selectionEnd).toBe(input.value.length);
    expect(changed).not.toHaveBeenCalled();
    fireEvent.keyDown(input, { key: "Enter" });
    expect(changed).toHaveBeenCalledTimes(1);
    expect(changed.mock.calls[0][0].map((term: { value: string }) => term.value)).toEqual(["设计", "搭建"]);
  });
  it("retains the entire input without partial writes when more than 20 terms are pasted", () => {
    const { input, changed } = editor();
    paste(input, Array.from({ length: 21 }, (_, i) => `关键词${i}`).join("\n"));
    fireEvent.keyDown(input, { key: "Enter" });
    expect(changed).not.toHaveBeenCalled();
    expect(screen.getByRole("alert").textContent).toContain("最多可填写20个词项");
    expect(input.value).toContain("关键词20");
    fireEvent.change(input, { target: { value: "修正词一, 修正词二" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(changed).toHaveBeenCalledTimes(1);
  });
  it("does not write a partial batch when a pasted word exceeds the length limit", () => {
    const { input, changed } = editor();
    paste(input, `短词\n${"字".repeat(81)}`);
    fireEvent.blur(input);
    expect(changed).not.toHaveBeenCalled();
    expect(screen.getByRole("alert").textContent).toContain("每个词项最多80个字符");
    expect(input.value).toContain("字".repeat(81));
  });
  it("does not commit on a Chinese composition Enter, and Escape cancels the pending batch", () => {
    const { input, changed } = editor();
    paste(input, "设计\n搭建");
    fireEvent.keyDown(input, { key: "Enter", isComposing: true });
    expect(changed).not.toHaveBeenCalled();
    expect(input.isConnected).toBe(true);
    fireEvent.keyDown(input, { key: "Escape" });
    expect(changed).not.toHaveBeenCalled();
    expect(screen.queryByRole("textbox")).toBeNull();
  });
  it("leaves ordinary single-line paste to the browser", () => {
    const { input, changed } = editor();
    expect(paste(input, "设计, 搭建")).toBe(true);
    expect(changed).not.toHaveBeenCalled();
  });
});
