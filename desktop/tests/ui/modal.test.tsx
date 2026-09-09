// @vitest-environment jsdom
import { StrictMode, useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { Button, Confirm, Modal } from "../../src/renderer/components/ui";

afterEach(() => {
  cleanup();
  document.body.style.overflow = "";
  vi.restoreAllMocks();
});
beforeEach(() => {
  vi.spyOn(HTMLElement.prototype, "getClientRects").mockImplementation(
    function () {
      return [{ width: 100, height: 30 }] as unknown as DOMRectList;
    },
  );
});
function Stack({ initialChild = false }: { initialChild?: boolean }) {
  const [outer, setOuter] = useState(false);
  const [inner, setInner] = useState(initialChild);
  return (
    <>
      <button onClick={() => setOuter(true)}>打开外层</button>
      {outer && (
        <Modal
          title="外层"
          onClose={() => setOuter(false)}
          footer={<Button>外层操作</Button>}
        >
          <button onClick={() => setInner(true)}>打开内层</button>
          {inner && (
            <Confirm
              title="内层"
              onCancel={() => setInner(false)}
              onConfirm={() => setInner(false)}
            >
              核对内容
            </Confirm>
          )}
        </Modal>
      )}
    </>
  );
}
function openOuter() {
  const trigger = screen.getByRole("button", { name: "打开外层" });
  trigger.focus();
  fireEvent.click(trigger);
  return trigger;
}
function openInner() {
  const trigger = screen.getByRole("button", { name: "打开内层" });
  trigger.focus();
  fireEvent.click(trigger);
  return trigger;
}

describe("共享弹窗键盘与焦点", () => {
  it("只向辅助功能声明最上层为模态，关闭后恢复底层", () => {
    function Siblings() {
      const [inner, setInner] = useState(false);
      return <>
        <Modal title="资料抽屉" onClose={() => {}} drawer>
          <button onClick={() => setInner(true)}>取消修改</button>
        </Modal>
        {inner && <Confirm title="放弃修改" onCancel={() => setInner(false)} onConfirm={() => setInner(false)}>未保存内容</Confirm>}
      </>;
    }
    render(<Siblings />);
    const outer = screen.getByRole("dialog", {name: "资料抽屉"});
    expect(outer.getAttribute("aria-modal")).toBe("true");
    fireEvent.click(screen.getByRole("button", {name: "取消修改"}));
    const inner = screen.getByRole("dialog", {name: "放弃修改"});
    expect(outer.getAttribute("aria-modal")).toBe("false");
    expect(inner.getAttribute("aria-modal")).toBe("true");
    expect(document.querySelectorAll('[aria-modal="true"]')).toHaveLength(1);
    fireEvent.keyDown(document, {key: "Escape"});
    expect(outer.getAttribute("aria-modal")).toBe("true");
    expect(document.activeElement).toBe(within(outer).getByRole("button", {name: "关闭资料抽屉"}));
  });
  it("Escape一次只关闭最上层，逐层恢复原按钮焦点", () => {
    render(<Stack />);
    const outer = openOuter();
    const inner = openInner();
    expect(document.activeElement).toBe(
      screen.getByRole("button", { name: "关闭内层" }),
    );
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: "内层" })).toBeNull();
    expect(screen.getByRole("dialog", { name: "外层" })).toBeTruthy();
    expect(document.activeElement).toBe(inner);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(outer);
  });
  it("父子同次挂载时以界面层级识别顶层，不依赖effect顺序", () => {
    render(<Stack initialChild />);
    openOuter();
    expect(document.activeElement).toBe(
      screen.getByRole("button", { name: "关闭内层" }),
    );
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: "内层" })).toBeNull();
    expect(screen.getByRole("dialog", { name: "外层" })).toBeTruthy();
  });
  it("StrictMode不会重复监听，最后一层关闭才恢复页面滚动", () => {
    document.body.style.overflow = "scroll";
    render(
      <StrictMode>
        <Stack />
      </StrictMode>,
    );
    openOuter();
    openInner();
    expect(document.body.style.overflow).toBe("hidden");
    fireEvent.keyDown(document, { key: "Escape" });
    expect(document.body.style.overflow).toBe("hidden");
    fireEvent.keyDown(document, { key: "Escape" });
    expect(document.body.style.overflow).toBe("scroll");
  });
  it("整个弹窗树一起卸载也回到最初按钮", () => {
    function Harness() {
      const [open, setOpen] = useState(false);
      return (
        <>
          <button onClick={() => setOpen(true)}>开始</button>
          {open && (
            <Modal title="父层" onClose={() => setOpen(false)}>
              <Modal title="子层" onClose={() => setOpen(false)}>
                <button onClick={() => setOpen(false)}>全部关闭</button>
              </Modal>
            </Modal>
          )}
        </>
      );
    }
    render(<Harness />);
    const trigger = screen.getByRole("button", { name: "开始" });
    trigger.focus();
    fireEvent.click(trigger);
    fireEvent.click(screen.getByRole("button", { name: "全部关闭" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });
  it("Tab和Shift+Tab仅在最上层可操作控件间循环", () => {
    render(<Stack />);
    openOuter();
    openInner();
    const dialog = screen.getByRole("dialog", { name: "内层" });
    const first = within(dialog).getByRole("button", { name: "关闭内层" });
    const last = within(dialog).getByRole("button", { name: "确认" });
    last.focus();
    fireEvent.keyDown(document, { key: "Tab" });
    expect(document.activeElement).toBe(first);
    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(last);
    screen.getByRole("button", { name: "打开外层" }).focus();
    expect(document.activeElement).toBe(dialog);
    fireEvent.keyDown(document, { key: "Tab" });
    expect(document.activeElement).toBe(first);
  });
  it("禁用和隐藏控件不进入键盘循环", () => {
    render(
      <Modal
        title="输入"
        onClose={() => {}}
        footer={
          <>
            <button disabled>不可用</button>
            <button hidden>隐藏</button>
          </>
        }
      >
        <input aria-label="内容" />
      </Modal>,
    );
    screen.getByLabelText("内容").focus();
    fireEvent.keyDown(document, { key: "Tab" });
    expect(document.activeElement).toBe(
      screen.getByRole("button", { name: "关闭输入" }),
    );
  });
  it("输入法正在选字时Escape不关闭弹窗", () => {
    render(<Stack />);
    openOuter();
    fireEvent.keyDown(document, { key: "Escape", isComposing: true });
    expect(screen.getByRole("dialog", { name: "外层" })).toBeTruthy();
  });
  it("由调用方决定忙碌时是否允许关闭，并读取最新onClose", () => {
    function Busy({ busy }: { busy: boolean }) {
      const [open, setOpen] = useState(true);
      return open ? (
        <Modal
          title="处理中"
          onClose={() => {
            if (!busy) setOpen(false);
          }}
        >
          处理中
        </Modal>
      ) : (
        <p>已关闭</p>
      );
    }
    const view = render(<Busy busy />);
    fireEvent.keyDown(document, { key: "Escape" });
    fireEvent.click(screen.getByRole("button", { name: "关闭处理中" }));
    expect(screen.getByRole("dialog")).toBeTruthy();
    view.rerender(<Busy busy={false} />);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByText("已关闭")).toBeTruthy();
  });
});
