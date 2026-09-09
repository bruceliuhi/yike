import {
  useEffect,
  useId,
  useRef,
  type ButtonHTMLAttributes,
  type ReactNode,
} from "react";
import {
  ArrowLeft,
  ArrowClockwise,
  CheckCircle,
  Info,
  WarningCircle,
  X,
  FileMagnifyingGlass,
} from "@phosphor-icons/react";
export function Button({
  variant = "secondary",
  loading = false,
  className = "",
  children,
  disabled,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  loading?: boolean;
}) {
  return (
    <button
      {...props}
      type={props.type || "button"}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={`button button-${variant} ${className}`}
    >
      {loading && <ArrowClockwise className="spin" aria-hidden />}
      {children}
    </button>
  );
}
export function PageHeader({
  title,
  description,
  extra,
  back,
}: {
  title: string;
  description?: ReactNode;
  extra?: ReactNode;
  back?: () => void;
}) {
  return (
    <header className="page-heading">
      <div>
        {back && (
          <button className="back-link" onClick={back}>
            <ArrowLeft />
            返回
          </button>
        )}
        <h1 tabIndex={-1}>{title}</h1>
        {description && <div className="page-description">{description}</div>}
      </div>
      {extra && <div className="heading-actions">{extra}</div>}
    </header>
  );
}
export function Field({
  label,
  required,
  error,
  children,
  hint,
  className = "",
}: {
  label: string;
  required?: boolean;
  error?: string;
  children: ReactNode;
  hint?: ReactNode;
  className?: string;
}) {
  const id = useId();
  return (
    <div className={`field ${className}`} role="group" aria-labelledby={id}>
      <div id={id} className="field-label">
        {label}
        {required && <span className="required"> *</span>}
      </div>
      {children}
      {error ? (
        <p className="field-error" role="alert">
          {error}
        </p>
      ) : hint ? (
        <div className="field-hint">{hint}</div>
      ) : null}
    </div>
  );
}
export function Notice({
  children,
  tone = "info",
  action,
}: {
  children: ReactNode;
  tone?: "info" | "warning" | "error" | "success";
  action?: ReactNode;
}) {
  const Icon =
    tone === "error" || tone === "warning"
      ? WarningCircle
      : tone === "success"
        ? CheckCircle
        : Info;
  return (
    <div
      className={`notice notice-${tone}`}
      role={tone === "error" ? "alert" : "status"}
    >
      <Icon aria-hidden size={18} />
      <div>{children}</div>
      {action && <div className="notice-action">{action}</div>}
    </div>
  );
}
export function Badge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "blue" | "green" | "orange" | "red";
}) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}
export function Empty({
  title,
  description,
  action,
}: {
  title: string;
  description?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="empty-state">
      <FileMagnifyingGlass
        size={56}
        weight="duotone"
        className="empty-icon"
        aria-hidden
      />
      <h3>{title}</h3>
      {description && <p>{description}</p>}
      {action}
    </div>
  );
}
export function Tabs({
  items,
  active,
  onChange,
}: {
  items: { key: string; label: ReactNode; count?: number }[];
  active: string;
  onChange: (key: string) => void;
}) {
  return (
    <div className="tabs" role="tablist">
      {items.map((item, i) => (
        <button
          role="tab"
          type="button"
          tabIndex={active === item.key ? 0 : -1}
          aria-selected={active === item.key}
          className={active === item.key ? "active" : ""}
          key={item.key}
          onClick={() => onChange(item.key)}
          onKeyDown={(event) => {
            if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
              event.preventDefault();
              const next =
                (i + (event.key === "ArrowRight" ? 1 : -1) + items.length) %
                items.length;
              onChange(items[next].key);
              (
                event.currentTarget.parentElement?.children[
                  next
                ] as HTMLButtonElement
              )?.focus();
            }
          }}
        >
          {item.label}
          {item.count !== undefined && (
            <span className="tab-count">{item.count}</span>
          )}
        </button>
      ))}
    </div>
  );
}
interface DialogEntry {
  node: HTMLDivElement;
  close: () => void;
}
const dialogs = new Map<HTMLDivElement, DialogEntry>();
let bodyOverflow = "";
let initialFocus: HTMLElement | null = null;
function topDialog(): DialogEntry | undefined {
  const nodes = document.querySelectorAll<HTMLDivElement>("[data-yike-dialog]");
  for (let i = nodes.length - 1; i >= 0; i--) {
    const entry = dialogs.get(nodes[i]);
    if (entry) return entry;
  }
}
function syncDialogModality() {
  // Chromium on macOS can expose the first aria-modal dialog and hide a later
  // sibling confirmation. Only the active layer owns the modal declaration.
  // Do not hide/inert lower dialogs: a top dialog may be their descendant.
  const top = topDialog();
  for (const node of dialogs.keys())
    node.setAttribute("aria-modal", String(node === top?.node));
}
function dialogFocusable(node: HTMLDivElement): HTMLElement[] {
  return [
    ...node.querySelectorAll<HTMLElement>(
      "button,a[href],input,textarea,select,[tabindex]",
    ),
  ].filter((element) => {
    const style = getComputedStyle(element);
    return (
      element.tabIndex >= 0 &&
      !element.matches(':disabled,input[type="hidden"]') &&
      !element.closest("[hidden],[inert]") &&
      style.display !== "none" &&
      style.visibility !== "hidden" &&
      element.getClientRects().length > 0
    );
  });
}
function dialogKeydown(event: KeyboardEvent) {
  const top = topDialog();
  if (!top || event.isComposing || event.keyCode === 229) return;
  if (event.key === "Escape") {
    // One listener selects one dialog for the whole event. Closing it must not
    // expose a parent handler to the same Escape key.
    event.preventDefault();
    event.stopImmediatePropagation();
    top.close();
    return;
  }
  if (event.key !== "Tab") return;
  const focusable = dialogFocusable(top.node);
  const first = focusable[0],
    last = focusable.at(-1);
  const active = document.activeElement;
  if (!first) {
    event.preventDefault();
    top.node.focus();
    return;
  }
  if (
    event.shiftKey &&
    (active === first || active === top.node || !top.node.contains(active))
  ) {
    event.preventDefault();
    last?.focus();
  } else if (
    !event.shiftKey &&
    (active === last || active === top.node || !top.node.contains(active))
  ) {
    event.preventDefault();
    first.focus();
  }
}
function containDialogFocus(event: FocusEvent) {
  const top = topDialog();
  if (top && event.target instanceof Node && !top.node.contains(event.target))
    top.node.focus();
}
export function Modal({
  title,
  onClose,
  children,
  footer,
  size = "medium",
  drawer = false,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  size?: "small" | "medium" | "large";
  drawer?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const heading = useId();
  const close = useRef(onClose);
  close.current = onClose;
  const previous = useRef(document.activeElement as HTMLElement | null);
  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    if (!dialogs.size) {
      initialFocus = previous.current;
      bodyOverflow = document.body.style.overflow;
      document.body.style.overflow = "hidden";
      document.addEventListener("keydown", dialogKeydown, true);
      document.addEventListener("focusin", containDialogFocus, true);
    }
    dialogs.set(node, { node, close: () => close.current() });
    syncDialogModality();
    const activeDialog = topDialog();
    if (activeDialog)
      (dialogFocusable(activeDialog.node)[0] ?? activeDialog.node).focus();
    return () => {
      dialogs.delete(node);
      syncDialogModality();
      if (!dialogs.size) {
        document.body.style.overflow = bodyOverflow;
        document.removeEventListener("keydown", dialogKeydown, true);
        document.removeEventListener("focusin", containDialogFocus, true);
      }
      const top = topDialog();
      const target = previous.current?.isConnected
        ? previous.current
        : initialFocus;
      if (target?.isConnected && (!top || top.node.contains(target)))
        target.focus();
      else if (top && !top.node.contains(document.activeElement))
        top.node.focus();
      if (!dialogs.size) initialFocus = null;
    };
  }, []);
  return (
    <div className={`modal-backdrop ${drawer ? "drawer-backdrop" : ""}`}>
      <div
        ref={ref}
        data-yike-dialog
        className={`${drawer ? "drawer" : "modal"} modal-${size}`}
        role="dialog"
        aria-labelledby={heading}
        tabIndex={-1}
      >
        <header className="modal-header">
          <h2 id={heading}>{title}</h2>
          <button
            className="icon-button"
            aria-label={`关闭${title}`}
            onClick={() => {
              if (topDialog()?.node === ref.current) close.current();
            }}
          >
            <X size={20} />
          </button>
        </header>
        <div className="modal-body">{children}</div>
        {footer && <footer className="modal-footer">{footer}</footer>}
      </div>
    </div>
  );
}
export function Drawer(props: Omit<Parameters<typeof Modal>[0], "drawer">) {
  return <Modal {...props} drawer />;
}
export function Confirm({
  title,
  children,
  onCancel,
  onConfirm,
  loading = false,
  confirmText = "确认",
  confirmDisabled = false,
  danger = false,
}: {
  title: string;
  children: ReactNode;
  onCancel: () => void;
  onConfirm: () => void;
  loading?: boolean;
  confirmText?: string;
  confirmDisabled?: boolean;
  danger?: boolean;
}) {
  return (
    <Modal
      title={title}
      onClose={onCancel}
      size="small"
      footer={
        <>
          <Button onClick={onCancel}>取消</Button>
          <Button
            variant={danger ? "danger" : "primary"}
            disabled={confirmDisabled}
            loading={loading}
            onClick={onConfirm}
          >
            {confirmText}
          </Button>
        </>
      }
    >
      {children}
    </Modal>
  );
}
export function ResourceStatus({
  loading,
  error,
  onRetry,
}: {
  loading: boolean;
  error?: string;
  onRetry?: () => void;
}) {
  if (loading)
    return (
      <div className="loading-state" role="status">
        <ArrowClockwise className="spin" />
        正在加载…
      </div>
    );
  if (error)
    return (
      <Notice
        tone="error"
        action={
          onRetry ? (
            <Button variant="ghost" onClick={onRetry}>
              重试
            </Button>
          ) : undefined
        }
      >
        {error}
      </Notice>
    );
  return null;
}
export function Pagination({
  page,
  total,
  pageSize = 10,
  onChange,
}: {
  page: number;
  total: number;
  pageSize?: number;
  onChange: (page: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  return (
    <div className="pagination">
      <span>共 {total} 条</span>
      <Button disabled={page <= 1} onClick={() => onChange(page - 1)}>
        上一页
      </Button>
      <span>
        {page} / {pages}
      </span>
      <Button disabled={page >= pages} onClick={() => onChange(page + 1)}>
        下一页
      </Button>
    </div>
  );
}
export function formatDate(value: string) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.valueOf())
    ? value
    : date.toLocaleString("zh-CN", { hour12: false });
}
