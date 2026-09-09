export interface AppRoute {
  path: string;
  query: URLSearchParams;
  page: string;
}
const pageRoutes: Record<string, string> = {
  P01: "/login",
  P02: "/workbench",
  P03: "/profile",
  P04: "/profile?tab=materials",
  P05: "/collection",
  P06: "/tasks/new",
  P07: "/candidates",
  P08: "/monitors",
  P09: "/monitors/preview",
  P10: "/opportunities",
  P11: "/opportunities/sample",
  P12: "/outreach?opportunity=sample",
  P13: "/outreach?opportunity=sample&confirm=send",
  P14: "/followups",
  P15: "/followups?add=1",
  P16: "/connections",
  P17: "/connections?connect=xhs",
  P18: "/settings",
  P19: "/tasks/new?step=confirm",
  P20: "/tasks/new?mode=monitor",
};
export function parseRoute(hash: string): AppRoute {
  const raw = hash.replace(/^#/, "") || "/workbench";
  const mapped = pageRoutes[raw] || raw;
  let url: URL;
  try {
    url = new URL(
      mapped.startsWith("/") && !mapped.startsWith("//")
        ? mapped
        : "/workbench",
      "https://local.invalid",
    );
  } catch {
    url = new URL("/not-found", "https://local.invalid");
  }
  let page = "UNKNOWN";
  const p = url.pathname;
  const q = url.searchParams;
  if (p === "/workbench") page = "P02";
  if (p === "/login") page = "P01";
  else if (p === "/profile")
    page = q.get("tab") === "materials" ? "P04" : "P03";
  else if (p === "/collection") page = "P05";
  else if (p === "/tasks/new")
    page =
      q.get("step") === "confirm"
        ? "P19"
        : q.get("mode") === "monitor"
          ? "P20"
          : "P06";
  else if (p === "/candidates") page = "P07";
  else if (p === "/monitors") page = "P08";
  else if (p.startsWith("/monitors/")) page = "P09";
  else if (p === "/opportunities") page = "P10";
  else if (p.startsWith("/opportunities/")) page = "P11";
  else if (p === "/outreach")
    page = q.get("confirm") === "send" ? "P13" : "P12";
  else if (p === "/followups") page = q.get("add") === "1" ? "P15" : "P14";
  else if (p === "/connections") page = q.has("connect") ? "P17" : "P16";
  else if (p === "/settings") page = "P18";
  return { path: p, query: q, page };
}
export function safeReturnTo(
  value: string | null,
  fallback = "/connections",
): string {
  return value &&
    /^\/(?:workbench|profile|collection|tasks\/new|candidates|monitors|opportunities|outreach|followups|connections|settings)(?:[/?]|$)/.test(
      value,
    ) &&
    !value.includes("://")
    ? value
    : fallback;
}
export function routeHref(route: AppRoute): string {
  const q = route.query.toString();
  return route.path + (q ? "?" + q : "");
}
export const NAV = [
  { path: "/workbench", label: "商机工作台", icon: "House", group: "" },
  { path: "/profile", label: "业务画像", icon: "User", group: "发现商机" },
  {
    path: "/collection",
    label: "线索采集",
    icon: "MagnifyingGlass",
    group: "发现商机",
  },
  { path: "/monitors", label: "监控任务", icon: "Bell", group: "发现商机" },
  {
    path: "/opportunities",
    label: "商机库",
    icon: "FolderSimple",
    group: "推进商机",
  },
  {
    path: "/outreach",
    label: "触达中心",
    icon: "PaperPlaneTilt",
    group: "推进商机",
  },
  {
    path: "/followups",
    label: "跟进记录",
    icon: "FileText",
    group: "推进商机",
  },
] as const;
