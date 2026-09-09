import {
  Component,
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type ComponentType,
  type ReactNode,
} from "react";
import {
  House,
  User,
  MagnifyingGlass,
  Bell,
  FolderSimple,
  PaperPlaneTilt,
  FileText,
  Gear,
  Buildings,
  SidebarSimple,
  ArrowLeft,
  SignIn,
} from "@phosphor-icons/react";
import logo from "../assets/logo.png";
import { useApp } from "./context";
import { NAV, safeReturnTo, type AppRoute } from "../domain/routes";
import { Empty, Button } from "../components/ui";

const loaders = import.meta.glob("../pages/*.tsx");
const missingLoader = async (): Promise<unknown> => {
  throw new Error("Page module is unavailable");
};

/** Keep a failed import or render inside the workspace and offer a real retry. */
export class AppErrorBoundary extends Component<
  {
    children: ReactNode;
    onRetry?: () => void;
    onHome?: () => void;
    resetKey?: string;
  },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidUpdate(previous: Readonly<{ resetKey?: string }>) {
    if (previous.resetKey !== this.props.resetKey && this.state.failed)
      this.setState({ failed: false });
  }
  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <section role="alert" className="page-error">
        <Empty
          title="页面未能打开"
          description="请重新打开此页，或返回商机工作台继续。"
          action={
            <div className="heading-actions">
              <Button
                onClick={() => {
                  this.props.onRetry?.();
                  this.setState({ failed: false });
                }}
              >
                重试打开
              </Button>
              <Button
                variant="primary"
                onClick={() =>
                  this.props.onHome
                    ? this.props.onHome()
                    : window.location.assign("#/workbench")
                }
              >
                返回商机工作台
              </Button>
            </div>
          }
        />
      </section>
    );
  }
}
function PageLoaded({ onReady }: { onReady?: () => void }) {
  useLayoutEffect(() => {
    onReady?.();
  }, [onReady]);
  return null;
}
export function LazyPage({
  load,
  name,
  onHome,
  onReady,
  resetKey,
}: {
  load: () => Promise<unknown>;
  name: string;
  onHome: () => void;
  onReady?: () => void;
  resetKey?: string;
}) {
  const [attempt, setAttempt] = useState(0);
  const PageComponent = useMemo(
    () =>
      lazy(async () => {
        const module = await load();
        const component =
          module && typeof module === "object"
            ? (module as Record<string, unknown>)[name]
            : undefined;
        if (
          typeof component !== "function" &&
          !(
            component &&
            typeof component === "object" &&
            "$$typeof" in component
          )
        )
          throw new Error("Page export is unavailable");
        return { default: component as ComponentType };
      }),
    [load, name, attempt],
  );
  return (
    <AppErrorBoundary
      key={attempt}
      resetKey={resetKey}
      onRetry={() => setAttempt((value) => value + 1)}
      onHome={onHome}
    >
      <Suspense
        fallback={
          <div className="loading-state" role="status">
            正在打开页面…
          </div>
        }
      >
        <PageComponent />
        <PageLoaded onReady={onReady} />
      </Suspense>
    </AppErrorBoundary>
  );
}
function Page({
  file,
  name,
  onReady,
}: {
  file: string;
  name: string;
  onReady: () => void;
}) {
  const { navigate, route } = useApp();
  return (
    <LazyPage
      key={`${file}:${name}`}
      load={loaders[`../pages/${file}.tsx`] || missingLoader}
      name={name}
      onHome={() => navigate("/workbench")}
      onReady={onReady}
      resetKey={semanticRouteKey(route)}
    />
  );
}
const icons = {
  House,
  User,
  MagnifyingGlass,
  Bell,
  FolderSimple,
  PaperPlaneTilt,
  FileText,
};
const titleByPage: Record<string, string> = {
  P01: "登录",
  P02: "商机工作台",
  P03: "业务画像",
  P04: "业务画像 / 资料与案例",
  P05: "线索采集",
  P06: "线索采集 / 新建任务",
  P07: "线索采集 / 原始线索",
  P08: "监控任务",
  P09: "监控任务 / 任务详情",
  P10: "商机库",
  P11: "商机库 / 机会证据",
  P12: "触达中心",
  P13: "触达中心 / 发送确认",
  P14: "跟进记录",
  P15: "跟进记录 / 添加跟进",
  P16: "账号与授权 / 平台连接",
  P17: "账号与授权 / 连接平台",
  P18: "账号与授权",
  P19: "线索采集 / 确认任务",
  P20: "监控任务 / 新建任务",
};
function routePage(page: string, onReady: () => void, onHome: () => void) {
  if (page === "P01")
    return <Page file="Login" name="LoginPage" onReady={onReady} />;
  if (page === "P02")
    return <Page file="Workbench" name="WorkbenchPage" onReady={onReady} />;
  if (page === "P03" || page === "P04")
    return <Page file="Profile" name="ProfilePage" onReady={onReady} />;
  if (["P06", "P19", "P20"].includes(page))
    return <Page file="TaskWizard" name="TaskWizardPage" onReady={onReady} />;
  if (["P05", "P08", "P09"].includes(page))
    return <Page file="Tasks" name="TasksPage" onReady={onReady} />;
  if (page === "P07")
    return (
      <Page file="Opportunities" name="CandidatesPage" onReady={onReady} />
    );
  if (page === "P10")
    return (
      <Page file="Opportunities" name="OpportunitiesPage" onReady={onReady} />
    );
  if (page === "P11")
    return (
      <Page
        file="Opportunities"
        name="OpportunityDetailPage"
        onReady={onReady}
      />
    );
  if (page === "P12" || page === "P13")
    return <Page file="Outreach" name="OutreachPage" onReady={onReady} />;
  if (page === "P14" || page === "P15")
    return <Page file="Followups" name="FollowupsPage" onReady={onReady} />;
  if (page === "P16" || page === "P17")
    return <Page file="Connections" name="ConnectionsPage" onReady={onReady} />;
  if (page === "P18")
    return <Page file="Settings" name="SettingsPage" onReady={onReady} />;
  return (
    <Empty
      title="页面不存在"
      description="这个页面地址无法识别，请从主导航重新打开。"
      action={
        <Button variant="primary" onClick={onHome}>
          返回商机工作台
        </Button>
      }
    />
  );
}
export function parentRoute(route: AppRoute): string {
  if (route.path === "/tasks/new") {
    if (route.query.has("step") && route.query.get("step") !== "conditions")
      return (
        "/tasks/new" +
        (route.query.get("mode") === "monitor" ? "?mode=monitor" : "")
      );
    return route.query.get("mode") === "monitor" ? "/monitors" : "/collection";
  }
  if (route.path.startsWith("/opportunities/")) {
    const back = safeReturnTo(route.query.get("returnTo"), "/opportunities");
    return back === "/opportunities" || back.startsWith("/opportunities?")
      ? back
      : "/opportunities";
  }
  if (route.path.startsWith("/monitors/")) return "/monitors";
  if (route.path === "/candidates") return "/collection";
  if (route.path === "/profile" && route.query.get("tab") === "materials")
    return "/profile";
  if (route.path === "/outreach" && route.query.has("confirm")) {
    const query = new URLSearchParams(route.query);
    query.delete("confirm");
    return "/outreach" + (query.size ? "?" + query : "");
  }
  if (route.path === "/followups" && route.query.has("add")) {
    const query = new URLSearchParams(route.query);
    query.delete("add");
    return "/followups" + (query.size ? "?" + query : "");
  }
  if (route.path === "/connections" && route.query.has("connect"))
    return safeReturnTo(route.query.get("returnTo"), "/connections");
  if (route.path === "/settings") return "/connections";
  return "/workbench";
}
export function semanticRouteKey(route: AppRoute): string {
  const query = new URLSearchParams(route.query);
  query.sort();
  return route.path + (query.size ? "?" + query : "");
}
function useRouteScroll(route: AppRoute, identity: string, ready: boolean) {
  const positions = useRef(new Map<string, { x: number; y: number }>());
  const restoring = useRef<{ key: string; cancelled: boolean } | null>(null);
  const key = identity + ":" + semanticRouteKey(route);
  useEffect(() => {
    const previous = window.history.scrollRestoration;
    window.history.scrollRestoration = "manual";
    return () => {
      window.history.scrollRestoration = previous;
    };
  }, []);
  const restore = useCallback(() => {
    if (!ready || restoring.current?.key !== key || restoring.current.cancelled)
      return;
    const position = positions.current.get(key) || { x: 0, y: 0 };
    window.scrollTo(position.x, position.y);
  }, [key, ready]);
  useLayoutEffect(() => {
    if (!ready) return;
    restoring.current = { key, cancelled: false };
    restore();
    // Imports and service reads may initially render a short loading state.
    // Retry restoration as the content grows, until the user takes control.
    const observer =
      typeof ResizeObserver === "undefined"
        ? undefined
        : new ResizeObserver(restore);
    observer?.observe(document.body);
    const timeout = window.setTimeout(() => {
      observer?.disconnect();
      if (restoring.current?.key === key) restoring.current.cancelled = true;
    }, 2500);
    const cancel = (event: Event) => {
      if (
        event instanceof KeyboardEvent &&
        ![
          "ArrowUp",
          "ArrowDown",
          "PageUp",
          "PageDown",
          "Home",
          "End",
          " ",
        ].includes(event.key)
      )
        return;
      if (restoring.current?.key === key) restoring.current.cancelled = true;
      observer?.disconnect();
    };
    window.addEventListener("wheel", cancel, { passive: true });
    window.addEventListener("touchstart", cancel, { passive: true });
    window.addEventListener("pointerdown", cancel);
    window.addEventListener("keydown", cancel);
    return () => {
      positions.current.set(key, { x: window.scrollX, y: window.scrollY });
      window.clearTimeout(timeout);
      observer?.disconnect();
      window.removeEventListener("wheel", cancel);
      window.removeEventListener("touchstart", cancel);
      window.removeEventListener("pointerdown", cancel);
      window.removeEventListener("keydown", cancel);
    };
  }, [key, ready, restore]);
  return restore;
}
export function App() {
  const { route, navigate, session, sessionReady } = useApp();
  const [collapsed, setCollapsed] = useState(false);
  const ready = sessionReady !== false;
  const restoreScroll = useRouteScroll(route, session.userId || "local", ready);
  useEffect(() => {
    document.title = `${titleByPage[route.page] || "页面不存在"} · 意客AI`;
    const frame = requestAnimationFrame(() => {
      if (!document.querySelector("[data-yike-dialog]"))
        document
          .querySelector<HTMLElement>("h1")
          ?.focus({ preventScroll: true });
    });
    return () => cancelAnimationFrame(frame);
  }, [route.path, route.page, ready]);
  if (!ready)
    return (
      <main className="loading-state" role="status">
        正在打开工作空间…
      </main>
    );
  if (route.page === "P01")
    return (
      <main className="login-root" key={session.userId || "local"}>
        {routePage(route.page, restoreScroll, () => navigate("/workbench"))}
      </main>
    );
  const active =
    route.path.startsWith("/tasks") || route.path === "/candidates"
      ? "/collection"
      : route.path.startsWith("/monitors/")
        ? "/monitors"
        : route.path.startsWith("/opportunities/")
          ? "/opportunities"
          : route.path;
  return (
    <div className={`app-shell ${collapsed ? "sidebar-collapsed" : ""}`}>
      <a
        className="skip-link"
        href="#main-content"
        onClick={(event) => {
          event.preventDefault();
          document.getElementById("main-content")?.focus();
        }}
      >
        跳到主要内容
      </a>
      <aside className="sidebar">
        <button
          className="brand"
          onClick={() => navigate("/workbench")}
          aria-label="意客AI商机工作台"
        >
          <img src={logo} width="48" height="48" alt="" />
          <span>
            <strong>意客AI</strong>
            <small>商机工作空间</small>
          </span>
        </button>
        <nav aria-label="主导航">
          {NAV.map((item, i) => {
            const Icon = icons[item.icon];
            return (
              <div key={item.path}>
                {item.group && item.group !== NAV[i - 1]?.group && (
                  <div className="nav-group">{item.group}</div>
                )}
                <button
                  className={`nav-item ${active === item.path ? "active" : ""}`}
                  aria-current={active === item.path ? "page" : undefined}
                  onClick={() => navigate(item.path)}
                  title={item.label}
                >
                  <Icon size={22} weight="regular" />
                  <span>{item.label}</span>
                </button>
              </div>
            );
          })}
        </nav>
        <div className="sidebar-bottom">
          <button
            className={`nav-item ${active === "/connections" || active === "/settings" ? "active" : ""}`}
            onClick={() => navigate("/connections")}
            title="账号与授权"
          >
            <Gear size={22} />
            <span>账号与授权</span>
          </button>
          <button
            className="workspace-switch"
            onClick={() =>
              navigate(session.authenticated ? "/settings" : "/login")
            }
            title={session.authenticated ? "客户工作空间" : "本机工作空间"}
          >
            <Buildings size={22} />
            <span>
              {session.authenticated ? "客户工作空间" : "本机工作空间"}
            </span>
          </button>
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <div className="breadcrumb">
            <button
              className="icon-button collapse-button"
              aria-label={collapsed ? "展开导航" : "收起导航"}
              onClick={() => setCollapsed(!collapsed)}
            >
              <SidebarSimple size={20} />
            </button>
            {route.page !== "P02" && (
              <button
                type="button"
                className="icon-button"
                aria-label="返回上级"
                title="返回上级"
                onClick={() => navigate(parentRoute(route))}
              >
                <ArrowLeft size={18} />
              </button>
            )}
            <span>{titleByPage[route.page] || "页面不存在"}</span>
          </div>
          <div className="topbar-actions">
            <span className="version-label">V0.2</span>
            {!session.authenticated && (
              <Button variant="ghost" onClick={() => navigate("/login")}>
                <SignIn />
                登录
              </Button>
            )}
          </div>
        </header>
        <main
          id="main-content"
          tabIndex={-1}
          className="main-content"
          key={session.userId || "local"}
        >
          {routePage(route.page, restoreScroll, () => navigate("/workbench"))}
        </main>
      </div>
    </div>
  );
}
