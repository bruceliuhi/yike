const INVALID_LINK = "INVALID_NATIVE_COLLECTION_LINK";
const INVALID_SCOPE = "INVALID_NATIVE_LINK_SCOPE";
const PLATFORM_SET = new Set(["XIAOHONGSHU", "DOUYIN", "BILIBILI", "ZHIHU"]);
const ROUTE_HOSTS = new Set([
  "www.bilibili.com",
  "space.bilibili.com",
  "www.douyin.com",
  "www.xiaohongshu.com",
  "www.zhihu.com",
  "zhuanlan.zhihu.com",
]);
const FORBIDDEN_DECODED = /[\s\\\p{Cc}\p{Cf}\p{Cs}\p{Zl}\p{Zp}]/u;
const QUERY_KEY = /^[A-Za-z0-9_.-]+$/;
const SENSITIVE_KEY = /(token|cookie|session|authorization|signature|password|secret)/;
const XSEC_TOKEN = /^[A-Za-z0-9_+\/=-]{1,1024}$/;
const XSEC_SOURCE = /^[A-Za-z0-9_-]{1,80}$/;

export type NativeCollectionLink = {
  platform: "XIAOHONGSHU" | "DOUYIN" | "BILIBILI" | "ZHIHU";
  kind: "detail" | "creator";
  external_id: string;
  canonical_url: string;
};

function invalidLink(): never {
  throw new Error(INVALID_LINK);
}

function decodeQueryPart(value: string): string {
  try {
    return decodeURIComponent(value.replace(/\+/g, "%20"));
  } catch {
    return invalidLink();
  }
}

function parseQuery(raw: string): Map<string, string> {
  const result = new Map<string, string>();
  if (raw === "") return result;
  for (const pair of raw.split("&")) {
    const separator = pair.indexOf("=");
    if (separator < 1) invalidLink();
    const key = decodeQueryPart(pair.slice(0, separator));
    const value = decodeQueryPart(pair.slice(separator + 1));
    if (!QUERY_KEY.test(key) || FORBIDDEN_DECODED.test(value)) invalidLink();
    const normalized = key.toLowerCase();
    if ((normalized === "xsec_token" || normalized === "xsec_source") && key !== normalized)
      invalidLink();
    if (result.has(normalized) || normalized === "modal_id") invalidLink();
    result.set(normalized, value);
  }
  return result;
}

function route(host: string, path: string): Omit<NativeCollectionLink, "canonical_url"> & { base: string } {
  let match: RegExpExecArray | null;
  if (host === "www.bilibili.com" && (match = /^\/video\/(BV[A-Za-z0-9]{10})\/?$/.exec(path)))
    return { platform: "BILIBILI", kind: "detail", external_id: match[1], base: `https://www.bilibili.com/video/${match[1]}` };
  if (host === "space.bilibili.com" && (match = /^\/([1-9][0-9]{0,19})\/?$/.exec(path)))
    return { platform: "BILIBILI", kind: "creator", external_id: match[1], base: `https://space.bilibili.com/${match[1]}` };
  if (host === "www.douyin.com" && (match = /^\/video\/([1-9][0-9]{0,19})\/?$/.exec(path)))
    return { platform: "DOUYIN", kind: "detail", external_id: match[1], base: `https://www.douyin.com/video/${match[1]}` };
  if (host === "www.douyin.com" && (match = /^\/user\/([A-Za-z0-9_-]{1,128})\/?$/.exec(path)))
    return { platform: "DOUYIN", kind: "creator", external_id: match[1], base: `https://www.douyin.com/user/${match[1]}` };
  if (host === "www.xiaohongshu.com" && (match = /^\/explore\/([0-9a-f]{24})\/?$/.exec(path)))
    return { platform: "XIAOHONGSHU", kind: "detail", external_id: match[1], base: `https://www.xiaohongshu.com/explore/${match[1]}` };
  if (host === "www.xiaohongshu.com" && (match = /^\/user\/profile\/([0-9a-f]{24})\/?$/.exec(path)))
    return { platform: "XIAOHONGSHU", kind: "creator", external_id: match[1], base: `https://www.xiaohongshu.com/user/profile/${match[1]}` };
  if (host === "www.zhihu.com" && (match = /^\/question\/([1-9][0-9]{0,19})\/answer\/([1-9][0-9]{0,19})\/?$/.exec(path)))
    return { platform: "ZHIHU", kind: "detail", external_id: `answer:${match[2]}`, base: `https://www.zhihu.com/question/${match[1]}/answer/${match[2]}` };
  if ((host === "www.zhihu.com" || host === "zhuanlan.zhihu.com") && (match = /^\/p\/([1-9][0-9]{0,19})\/?$/.exec(path)))
    return { platform: "ZHIHU", kind: "detail", external_id: `article:${match[1]}`, base: `https://zhuanlan.zhihu.com/p/${match[1]}` };
  if (host === "www.zhihu.com" && (match = /^\/zvideo\/([1-9][0-9]{0,19})\/?$/.exec(path)))
    return { platform: "ZHIHU", kind: "detail", external_id: `zvideo:${match[1]}`, base: `https://www.zhihu.com/zvideo/${match[1]}` };
  if (host === "www.zhihu.com" && (match = /^\/people\/([A-Za-z0-9_-]{1,128})\/?$/.exec(path)))
    return { platform: "ZHIHU", kind: "creator", external_id: match[1], base: `https://www.zhihu.com/people/${match[1]}` };
  return invalidLink();
}

export function parseNativeCollectionLink(value: unknown): NativeCollectionLink {
  if (typeof value !== "string" || value.length < 1 || value.length > 2048 || !/^[\x21-\x7e]+$/.test(value) || value.includes("\\") || value.includes("#"))
    return invalidLink();
  if (!value.startsWith("https://")) return invalidLink();
  const authorityEnd = value.indexOf("/", "https://".length);
  if (authorityEnd < 0) return invalidLink();
  const rawAuthority = value.slice("https://".length, authorityEnd);
  if (!ROUTE_HOSTS.has(rawAuthority)) return invalidLink();
  const queryStart = value.indexOf("?", authorityEnd);
  const rawPath = value.slice(authorityEnd, queryStart < 0 ? undefined : queryStart);
  if (rawPath.includes("%") || rawPath.split("/").some((part) => part === "." || part === ".."))
    return invalidLink();
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    return invalidLink();
  }
  if (url.protocol !== "https:" || url.username || url.password || url.port || url.hash || url.hostname !== url.hostname.toLowerCase())
    return invalidLink();
  const target = route(url.hostname, rawPath);
  const query = parseQuery(queryStart < 0 ? "" : value.slice(queryStart + 1));
  const token = query.get("xsec_token");
  const source = query.get("xsec_source");
  for (const key of query.keys()) {
    if (SENSITIVE_KEY.test(key) && !(target.platform === "XIAOHONGSHU" && key === "xsec_token"))
      return invalidLink();
  }
  if ((token === undefined) !== (source === undefined)) return invalidLink();
  if (token !== undefined && (target.platform !== "XIAOHONGSHU" || !XSEC_TOKEN.test(token) || !XSEC_SOURCE.test(source!)))
    return invalidLink();
  const canonical_url = token === undefined
    ? target.base
    : `${target.base}?xsec_token=${encodeURIComponent(token)}&xsec_source=${encodeURIComponent(source!)}`;
  return { platform: target.platform, kind: target.kind, external_id: target.external_id, canonical_url };
}

export function planNativeCollectionLinks(
  platforms: readonly string[],
  links: readonly string[],
): NativeCollectionLink[] {
  try {
    if (!Array.isArray(platforms) || platforms.length < 1 || platforms.length > 4 ||
        platforms.some((platform) => typeof platform !== "string" || !PLATFORM_SET.has(platform)) ||
        new Set(platforms).size !== platforms.length || !Array.isArray(links) || links.length < 1 || links.length > 100 ||
        links.some((link) => typeof link !== "string"))
      throw new Error();
    const planned = links.map(parseNativeCollectionLink);
    const selected = new Set(platforms);
    if (planned.some((item) => !selected.has(item.platform)) ||
        platforms.some((platform) => !planned.some((item) => item.platform === platform)) ||
        new Set(planned.map((item) => `${item.platform}:${item.kind}:${item.external_id}`)).size !== planned.length)
      throw new Error();
    return planned;
  } catch {
    throw new Error(INVALID_SCOPE);
  }
}
