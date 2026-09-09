import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import type { Session } from "../domain/models";
import { parseRoute, type AppRoute } from "../domain/routes";
import { service as defaultService } from "../services/client";
import type { YikeService } from "../services/contracts";
import { hasUnsavedChanges } from "./hooks";
import { boundedRequest } from "./boundedRequest";
import { Confirm } from "../components/ui";
export interface Toast {
  id: number;
  message: string;
  tone: "info" | "success" | "error";
}
export interface AppContextValue {
  service: YikeService;
  session: Session;
  sessionReady?: boolean;
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
  const [session, setSession] = useState<Session>({ authenticated: false });
  const [sessionReady, setSessionReady] = useState(false);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [pendingPath, setPendingPath] = useState<string | null>(null);
  const lastHash = useRef(window.location.hash);
  const allowed = useRef(false);
  const sessionGeneration = useRef(0);
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
    const id = ++sessionGeneration.current;
    try {
      const next = await service.session();
      if (!signal?.aborted && id === sessionGeneration.current) {
        setSession(next);
        setSessionReady(true);
      }
      return next;
    } catch {
      const next = { authenticated: false };
      if (!signal?.aborted && id === sessionGeneration.current) {
        setSession(next);
        setSessionReady(true);
      }
      return next;
    }
  };
  useEffect(() => {
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
      setSession({ authenticated: false });
      setSessionReady(true);
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
        route,
        navigate,
        notify,
        refreshSession,
      }}
    >
      {children}
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
