// @vitest-environment jsdom
import { useEffect } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import {
  App,
  AppErrorBoundary,
  LazyPage,
  parentRoute,
  semanticRouteKey,
} from "../../src/renderer/app/App";
import { useApp, type AppContextValue } from "../../src/renderer/app/context";
import { parseRoute } from "../../src/renderer/domain/routes";
import { service } from "../../src/renderer/services/client";
vi.mock("../../src/renderer/app/context", () => ({ useApp: vi.fn() }));
vi.mock("../../src/renderer/pages/Profile", () => ({
  ProfilePage: () => <h1>测试画像页</h1>,
}));
vi.mock("../../src/renderer/pages/Workbench", () => ({
  WorkbenchPage: () => <h1>测试工作台</h1>,
}));
vi.mock("../../src/renderer/pages/TaskWizard", () => ({
  TaskWizardPage: () => <h1>测试任务配置</h1>,
}));
vi.mock("../../src/renderer/pages/Opportunities", () => ({
  OpportunityDetailPage: () => <h1>测试商机详情</h1>,
  OpportunitiesPage: () => <h1>测试商机列表</h1>,
}));
let context: AppContextValue;
beforeEach(() => {
  context = {
    service,
    session: { authenticated: true, userId: "navigation-user" },
    sessionReady: true,
    route: parseRoute("#/workbench"),
    navigate: vi.fn(),
    notify: vi.fn(),
    refreshSession: vi.fn().mockResolvedValue({ authenticated: false }),
  };
  vi.mocked(useApp).mockImplementation(() => context);
  Object.defineProperty(window, "scrollY", {
    value: 0,
    writable: true,
    configurable: true,
  });
  Object.defineProperty(window, "scrollX", {
    value: 0,
    writable: true,
    configurable: true,
  });
  vi.spyOn(window, "scrollTo").mockImplementation(
    (x?: number | ScrollToOptions, y?: number) => {
      Object.defineProperty(window, "scrollY", {
        value: typeof x === "number" ? y || 0 : x?.top || 0,
        writable: true,
        configurable: true,
      });
    },
  );
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function errorSilence() {
  vi.spyOn(console, "error").mockImplementation(() => {});
}
describe("页面加载恢复边界", () => {
  it("懒加载失败显示错误；重试重新调用加载器后可成功打开", async () => {
    errorSilence();
    const loader = vi
      .fn()
      .mockRejectedValueOnce(new Error("asset missing"))
      .mockResolvedValue({ Screen: () => <h1>恢复的页面</h1> });
    render(<LazyPage load={loader} name="Screen" onHome={vi.fn()} />);
    await screen.findByRole("alert");
    expect(screen.queryByText("页面正在准备")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "重试打开" }));
    await screen.findByText("恢复的页面");
    expect(loader).toHaveBeenCalledTimes(2);
  });
  it("缺少页面导出时提供工作台恢复入口", async () => {
    errorSilence();
    const home = vi.fn();
    render(<LazyPage load={async () => ({})} name="Missing" onHome={home} />);
    await screen.findByRole("alert");
    fireEvent.click(screen.getByRole("button", { name: "返回商机工作台" }));
    expect(home).toHaveBeenCalledOnce();
  });
  it("运行时渲染错误也能重试恢复，不显示内部异常详情", () => {
    errorSilence();
    let broken = true;
    function Screen() {
      if (broken) throw new Error("private implementation detail");
      return <h1>可用页面</h1>;
    }
    render(
      <AppErrorBoundary>
        <Screen />
      </AppErrorBoundary>,
    );
    expect(screen.getByRole("alert")).toBeTruthy();
    expect(screen.queryByText("private implementation detail")).toBeNull();
    broken = false;
    fireEvent.click(screen.getByRole("button", { name: "重试打开" }));
    expect(screen.getByText("可用页面")).toBeTruthy();
  });
  it("切换路由会清除前一页错误状态", () => {
    errorSilence();
    function Broken(): never {
      throw new Error("broken");
    }
    const view = render(
      <AppErrorBoundary resetKey="first">
        <Broken />
      </AppErrorBoundary>,
    );
    expect(screen.getByRole("alert")).toBeTruthy();
    view.rerender(
      <AppErrorBoundary resetKey="second">
        <h1>第二页</h1>
      </AppErrorBoundary>,
    );
    expect(screen.getByText("第二页")).toBeTruthy();
  });
  it("加载完成回调只在组件真实挂载后触发", async () => {
    const mounted = vi.fn();
    const ready = vi.fn();
    function Screen() {
      useEffect(() => {
        mounted();
      }, []);
      return <h1>已装入</h1>;
    }
    const loader = vi.fn().mockResolvedValue({ Screen });
    render(
      <LazyPage load={loader} name="Screen" onHome={vi.fn()} onReady={ready} />,
    );
    await screen.findByText("已装入");
    expect(ready).toHaveBeenCalledOnce();
    expect(mounted).toHaveBeenCalledOnce();
  });
});

describe("应用路由与会话边界", () => {
  it("未知或异常编码路由仍有可操作的工作台入口", () => {
    context.route = parseRoute("#/%E0%A4%A");
    render(<App />);
    expect(
      screen.getByText("这个页面地址无法识别，请从主导航重新打开。"),
    ).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "返回商机工作台" }));
    expect(context.navigate).toHaveBeenCalledWith("/workbench");
  });
  it("初始化阶段不挂载客户编辑页，会话就绪后再显示", async () => {
    context.route = parseRoute("#/profile");
    context.sessionReady = false;
    context.session = { authenticated: false };
    const view = render(<App />);
    expect(screen.getByRole("status").textContent).toBe("正在打开工作空间…");
    expect(screen.queryByText("测试画像页")).toBeNull();
    context = {
      ...context,
      sessionReady: true,
      session: { authenticated: true, userId: "resolved-user" },
    };
    view.rerender(<App />);
    await screen.findByText("测试画像页");
  });
  it("兼容未提供optional sessionReady的调用方", async () => {
    delete context.sessionReady;
    render(<App />);
    await screen.findByText("测试工作台");
  });
  it("页头返回按钮可以返回带筛选条件的商机列表", async () => {
    context.route = parseRoute(
      "#/opportunities/test?returnTo=%2Fopportunities%3Fstatus%3DNEW%26page%3D2",
    );
    render(<App />);
    await screen.findByText("测试商机详情");
    fireEvent.click(screen.getByRole("button", { name: "返回上级" }));
    expect(context.navigate).toHaveBeenCalledWith(
      "/opportunities?status=NEW&page=2",
    );
  });
  it("首次新页面回到顶部，返回已访问路由恢复位置", async () => {
    context.route = parseRoute("#/opportunities?status=NEW&page=2");
    const view = render(<App />);
    await screen.findByText("测试商机列表");
    window.scrollTo(0, 420);
    context = { ...context, route: parseRoute("#/tasks/new?mode=monitor") };
    view.rerender(<App />);
    expect(window.scrollY).toBe(0);
    await screen.findByText("测试任务配置");
    window.scrollTo(0, 150);
    context = {
      ...context,
      route: parseRoute("#/opportunities?page=2&status=NEW"),
    };
    view.rerender(<App />);
    await screen.findByText("测试商机列表");
    expect(window.scrollY).toBe(420);
  });
  it("任务新步骤首次从顶部开始，同用户返回条件页恢复位置", async () => {
    context.route = parseRoute("#/tasks/new?mode=monitor");
    const view = render(<App />);
    await screen.findByText("测试任务配置");
    window.scrollTo(0, 380);
    context = {
      ...context,
      route: parseRoute("#/tasks/new?mode=monitor&step=confirm"),
    };
    view.rerender(<App />);
    expect(window.scrollY).toBe(0);
    context = { ...context, route: parseRoute("#/tasks/new?mode=monitor") };
    view.rerender(<App />);
    expect(window.scrollY).toBe(380);
  });
  it("监控各步骤保持导航归属，切为单次确认后标题与侧栏同步切换", async () => {
    context.route = parseRoute("#/tasks/new?mode=monitor");
    const view = render(<App />);
    await screen.findByText("测试任务配置");
    for (const step of ["", "connect", "confirm"]) {
      context = {...context, route: parseRoute("#/tasks/new?mode=monitor" + (step ? "&step=" + step : ""))};
      view.rerender(<App />);
      expect(screen.getByRole("button", {name: "监控任务"}).getAttribute("aria-current")).toBe("page");
      expect(screen.getByRole("button", {name: "线索采集"}).hasAttribute("aria-current")).toBe(false);
      expect(document.title).toMatch(/^监控任务/);
    }
    context = {...context, route: parseRoute("#/tasks/new?step=confirm")};
    view.rerender(<App />);
    expect(screen.getByRole("button", {name: "线索采集"}).getAttribute("aria-current")).toBe("page");
    expect(document.title).toMatch(/^线索采集/);
  });
  it("用户主动滚动后内容变化不会强行拉回", async () => {
    let resized!: () => void;
    vi.stubGlobal(
      "ResizeObserver",
      class {
        constructor(callback: () => void) {
          resized = callback;
        }
        observe() {}
        disconnect() {}
      },
    );
    render(<App />);
    await screen.findByText("测试工作台");
    fireEvent.wheel(window);
    window.scrollTo(0, 210);
    resized();
    expect(window.scrollY).toBe(210);
  });
  it("不同用户的同一路由不复用滚动位置", async () => {
    const view = render(<App />);
    await screen.findByText("测试工作台");
    window.scrollTo(0, 300);
    context = {
      ...context,
      session: { authenticated: true, userId: "another-user" },
    };
    view.rerender(<App />);
    await screen.findByText("测试工作台");
    expect(window.scrollY).toBe(0);
  });
});

describe("父级路径契约", () => {
  it.each([
    ["/tasks/new?mode=monitor&step=confirm", "/tasks/new?mode=monitor"],
    ["/tasks/new?step=connect", "/tasks/new"],
    ["/tasks/new?mode=monitor", "/monitors"],
    ["/tasks/new", "/collection"],
    ["/opportunities/item", "/opportunities"],
    ["/opportunities/item?returnTo=https://other.example", "/opportunities"],
    ["/monitors/item", "/monitors"],
    ["/candidates", "/collection"],
    ["/profile?tab=materials", "/profile"],
    ["/outreach?opportunity=item&confirm=send", "/outreach?opportunity=item"],
    ["/followups?add=1", "/followups"],
    [
      "/connections?connect=xhs&returnTo=%2Ftasks%2Fnew%3Fstep%3Dconnect",
      "/tasks/new?step=connect",
    ],
    ["/settings", "/connections"],
  ])("%s 返回 %s", (path, parent) => {
    expect(parentRoute(parseRoute("#" + path))).toBe(parent);
  });
  it("同一组查询条件的排列不创建不同滚动记录", () => {
    expect(
      semanticRouteKey(parseRoute("#/opportunities?status=NEW&page=2")),
    ).toBe(semanticRouteKey(parseRoute("#/opportunities?page=2&status=NEW")));
  });
});
