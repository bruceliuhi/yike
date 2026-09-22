import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import type { Session } from "../domain/models";
import { parseRoute, routeHref, type AppRoute } from "../domain/routes";
import { service as defaultService } from "../services/client";
import type { YikeService } from "../services/contracts";
import { ServiceError } from "../services/contracts";
import { hasUnsavedChanges } from "./hooks";
import { boundedRequest } from "./boundedRequest";
import { Confirm } from "../components/ui";
import { DeviceConnectionPreparation } from './DeviceConnectionPreparation';
export interface Toast {
  id: number;
  message: string;
  tone: "info" | "success" | "error";
}
export interface AppContextValue {
  service: YikeService;
  session: Session;
  sessionReady?: boolean;
  sessionProblem?: string;
  route: AppRoute;
  navigate: (path: string) => void;
  notify: (message: string, tone?: Toast["tone"]) => void;
  refreshSession: (signal?: AbortSignal) => Promise<Session>;
}
const Context = createContext<AppContextValue | null>(null);
export function useApp(): AppContextValue {
  const context = useContext(Context);
  if (!context) throw new Error("AppProvider is required");
  return context;
}
export function AppProvider({
  children,
  service = defaultService,
}: {
  children: ReactNode;
  service?: YikeService;
}) {
  const [route, setRoute] = useState(() => parseRoute(window.location.hash));
  const [sessionObservation, setSessionObservation] = useState<{service:YikeService; session:Session} | null>(null);
  const guest = useRef<Session>({authenticated:false});
  const sessionReady = sessionObservation?.service === service;
  const session = sessionReady ? sessionObservation.session : guest.current;
  const currentService = useRef(service);
  currentService.current = service;
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [pendingPath, setPendingPath] = useState<string | null>(null);
  const lastHash = useRef(window.location.hash);
  const allowed = useRef(false);
  const sessionGeneration = useRef(0);
  const [sessionCheck, setSessionCheck] = useState<{identity: unknown; problem: string} | null>(null);
  const sessionProblem = sessionCheck?.identity === sessionObservation ? sessionCheck.problem : "";
  useEffect(() => {
    if (!sessionReady || !session.authenticated) return;
    const abort = new AbortController();
    let running = false;
    let checkedAt = Date.now();
    const check = async () => {
      if (running || document.visibilityState === 'hidden' || Date.now() - checkedAt < 60_000) return;
      checkedAt = Date.now();
      running = true;
      let problem = "";
      try {
        const next = await boundedRequest(() => service.session(), {signal:abort.signal, timeoutMessage:"登录状态核验超时"});
        if (!next.authenticated || next.userId !== session.userId)
          problem = "登录状态已变化，请重新登录；当前草稿仍保留。";
      } catch (error) {
        problem = error instanceof ServiceError && error.status === 401
          ? "登录已失效，请重新登录；当前草稿仍保留。"
          : "暂时无法确认登录状态，请检查网络后重试；当前草稿仍保留。";
      } finally { running = false; }
      if (!abort.signal.aborted) setSessionCheck({identity:sessionObservation, problem});
    };
    const interval = window.setInterval(() => void check(), 30 * 60_000);
    const focus = () => void check();
    window.addEventListener('focus', focus);
    document.addEventListener('visibilitychange', focus);
    return () => {
      abort.abort();
      window.clearInterval(interval);
      window.removeEventListener('focus', focus);
      document.removeEventListener('visibilitychange', focus);
    };
  }, [service, sessionObservation, sessionReady, session]);
  useEffect(() => {
    const changed = () => {
      if (!allowed.current && hasUnsavedChanges()) {
        const next = window.location.hash.slice(1);
        history.replaceState(null, "", lastHash.current || "#/workbench");
        setPendingPath(next);
        return;
      }
      allowed.current = false;
      lastHash.current = window.location.hash;
      setRoute(parseRoute(window.location.hash));
    };
    window.addEventListener("hashchange", changed);
    return () => window.removeEventListener("hashchange", changed);
  }, []);
  const refreshSession = async (signal?: AbortSignal) => {
    if (signal?.aborted) throw new DOMException("Session refresh cancelled", "AbortError");
    if (currentService.current !== service) return {authenticated:false};
    const id = ++sessionGeneration.current;
    try {
      const next = await service.session();
      if (!signal?.aborted && id === sessionGeneration.current && currentService.current === service) {
        setSessionObservation({service,session:next});
      }
      return next;
    } catch {
      const next = { authenticated: false };
      if (!signal?.aborted && id === sessionGeneration.current && currentService.current === service) {
        setSessionObservation({service,session:next});
      }
      return next;
    }
  };
  useEffect(() => {
    setSessionObservation(null);
    const abort = new AbortController();
    let requestId = -1;
    void boundedRequest(signal => {
      const pending = refreshSession(signal);
      requestId = sessionGeneration.current;
      return pending;
    }, {
      signal: abort.signal,
      timeoutMessage: "登录状态确认超时，客户工作空间尚未打开。请重新登录后重试。",
    }).catch(error => {
      if (abort.signal.aborted || requestId !== sessionGeneration.current) return;
      sessionGeneration.current++;
      setSessionObservation({service,session:{authenticated:false}});
      notify(error instanceof Error ? error.message : "登录状态尚未确认，请重新登录后重试。", "error");
    });
    return () => {
      abort.abort();
      sessionGeneration.current++;
    };
  }, [service]);
  const notify = (message: string, tone: Toast["tone"] = "info") => {
    const id = Date.now() + Math.random();
    setToasts((old) => [...old.slice(-2), { id, message, tone }]);
    window.setTimeout(
      () => setToasts((old) => old.filter((t) => t.id !== id)),
      6000,
    );
  };
  const go = (path: string) => {
    if (window.location.hash === "#" + path) return;
    allowed.current = true;
    window.location.hash = path;
  };
  const navigate = (path: string) => {
    // Keep the page the user was working on when a protected action asks them
    // to sign in.  This is especially important for a half-filled task: the
    // draft is intentionally session-scoped, so sending the user to the
    // workbench after login makes the sign-in button feel like a dead end.
    if (path === "/login" && route.path !== "/login") {
      const returnTo = routeHref(route);
      path = `/login?returnTo=${encodeURIComponent(returnTo)}`;
    }
    if (window.location.hash === "#" + path) return;
    if (hasUnsavedChanges()) {
      setPendingPath(path);
      return;
    }
    go(path);
  };
  return (
    <Context.Provider
      value={{
        service,
        session,
        sessionReady,
        sessionProblem,
        route,
        navigate,
        notify,
        refreshSession,
      }}
    >
      <DeviceConnectionPreparation api={service.deviceIdentity} session={session} confirmed={sessionReady}>
        {sessionProblem && (
          <div className="session-status-banner" role="alert">
            <span>{sessionProblem}</span>
            <button type="button" onClick={() => navigate('/login')}>重新登录</button>
          </div>
        )}
        {children}
      </DeviceConnectionPreparation>
      {pendingPath && (
        <Confirm
          title="离开当前页面？"
          onCancel={() => setPendingPath(null)}
          onConfirm={() => {
            go(pendingPath);
            setPendingPath(null);
          }}
          confirmText="继续离开"
        >
          <p>当前更改还没有提交。请确认是否继续离开，或返回页面完成保存。</p>
        </Confirm>
      )}
      <div className="toast-stack" aria-live="polite">
        {toasts.map((t) => (
          <div className={`toast toast-${t.tone}`} key={t.id}>
            {t.message}
            <button
              aria-label="关闭提示"
              onClick={() =>
                setToasts((old) => old.filter((x) => x.id !== t.id))
              }
            >
              关闭
            </button>
          </div>
        ))}
      </div>
    </Context.Provider>
  );
}
