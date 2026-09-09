import { Globe } from "@phosphor-icons/react";
import xiaohongshuLogo from "../assets/platforms/xiaohongshu.png";
import douyinLogo from "../assets/platforms/douyin.ico";
import bilibiliLogo from "../assets/platforms/bilibili.ico";
import zhihuLogo from "../assets/platforms/zhihu.ico";
import "./platform.css";

type PlatformProps = {
  platform: string;
  size?: number;
  className?: string;
};

const platforms = {
  xhs: { name: "小红书", image: xiaohongshuLogo },
  douyin: { name: "抖音", image: douyinLogo },
  bilibili: { name: "B站", image: bilibiliLogo },
  zhihu: { name: "知乎", image: zhihuLogo },
  web: { name: "公开网站", image: undefined },
};
type PlatformKey = keyof typeof platforms;

const aliases: Record<string, PlatformKey> = {
  xhs: "xhs",
  xiaohongshu: "xhs",
  rednote: "xhs",
  red: "xhs",
  小红书: "xhs",
  douyin: "douyin",
  dy: "douyin",
  抖音: "douyin",
  bilibili: "bilibili",
  bili: "bilibili",
  b站: "bilibili",
  哔哩哔哩: "bilibili",
  zhihu: "zhihu",
  知乎: "zhihu",
  web: "web",
  website: "web",
  publicweb: "web",
  publicwebsite: "web",
  公开网站: "web",
  公开网页: "web",
  "公开网站/社区": "web",
};

function resolvePlatform(platform: string) {
  const alias = platform
    .trim()
    .toLowerCase()
    .replace(/[\s_-]+/g, "");
  const key = Object.hasOwn(aliases, alias) ? aliases[alias] : undefined;
  return key ? platforms[key] : { name: platform, image: undefined };
}

/** Decorative only: the surrounding control or PlatformLabel supplies its name. */
export function PlatformIcon({
  platform,
  size = 20,
  className = "",
}: PlatformProps) {
  const { image } = resolvePlatform(platform);
  return (
    <span
      className={`brand-platform-icon ${className}`.trim()}
      aria-hidden="true"
      style={{ width: size, height: size }}
    >
      {image ? (
        <img src={image} alt="" width={size} height={size} draggable={false} />
      ) : (
        <Globe size={size} aria-hidden="true" />
      )}
    </span>
  );
}

export function PlatformLabel({
  platform,
  size = 18,
  className = "",
}: PlatformProps) {
  return (
    <span className={`brand-platform-label ${className}`.trim()}>
      <PlatformIcon platform={platform} size={size} />
      <span>{resolvePlatform(platform).name}</span>
    </span>
  );
}
