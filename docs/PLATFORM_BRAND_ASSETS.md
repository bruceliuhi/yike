# 平台品牌资源

更新：2026-09-09。用于意客AI界面标识内容来源和平台连接，不表示平台已授权、连接成功或平台背书。品牌图标不代替平台名称、执行账号和能力状态。

## 来源与离线交付

以下资源在开发时从对应平台官网或官网引用的 CDN 下载，保持原始字节；客户端通过 Vite 本地静态 import 打包，运行时不访问这些地址。未使用手绘标志、字体代替品牌、TikTok 文字标或新增图标依赖。

| 平台 / 本地文件 | 官方来源与核对 | 尺寸 / 字节 | SHA-256 |
|---|---|---|---|
| 小红书 / [xiaohongshu.png](../desktop/src/renderer/assets/platforms/xiaohongshu.png) | [官网](https://www.xiaohongshu.com/explore) HTML 的 `apple-touch-icon` 指向[此 PNG](https://picasso-static.xiaohongshu.com/fe-platform/f43dc4a8baf03678996c62d8db6ebc01a82256ff.png) | 180×180 / 2,482 | `2912c4df1ab479d734ef132e9c45b4f17afa80b2aa3eaf4438acd54afc70b20a` |
| 抖音 / [douyin.ico](../desktop/src/renderer/assets/platforms/douyin.ico) | [官网 favicon](https://www.douyin.com/favicon.ico) 重定向到[官方 CDN](https://lf1-cdn-tos.bytegoofy.com/goofy/ies/douyin_web/public/favicon.ico)；实际标志为彩色音符 | 32×32 / 4,286 | `e67348e3ab54fa207e1ce4be78e8399d1b73a794d819a17d8656ea2b17a1109d` |
| B站 / [bilibili.ico](../desktop/src/renderer/assets/platforms/bilibili.ico) | [官网 favicon](https://www.bilibili.com/favicon.ico)；[官方 CDN 副本](https://i0.hdslb.com/bfs/static/jinkela/long/images/favicon.ico) 返回相同字节；实际标志为蓝色小电视 | 32×32 / 4,286 | `2681561eb24e7435fea1acf26f3af95e4efc9f7d451587b58bef62f030f337e9` |
| 知乎 / [zhihu.ico](../desktop/src/renderer/assets/platforms/zhihu.ico) | [官网 favicon](https://www.zhihu.com/favicon.ico) 重定向到[官方静态站点](https://static.zhihu.com/heifetz/favicon.ico) | 32×32 / 4,286 | `ca501e1d6c35f64b94d78bbabad986fe888d6aab08702a0083ba88076ad60f37` |

已检查 PNG 原图与 ICO 的本地解码预览；预览仅作核对，不替换上述原始文件。品牌资产的权利仍归各平台，下载来源记录不等于额外商标许可。

## 共享组件约定

- [Platform.tsx](../desktop/src/renderer/components/Platform.tsx) 导出 `PlatformIcon({platform, size = 20, className})` 和 `PlatformLabel({platform, size = 18, className})`。
- 标签延续现有 `PLATFORMS` 命名：小红书、抖音、B站、知乎、公开网站。常见中文/英文及大小写别名统一到同一品牌；TikTok 不视为抖音别名。未知来源保持输入名称，使用现有 Phosphor `Globe`。
- 图标仅装饰，容器 `aria-hidden`、图像 `alt=""`；可访问名称由相邻平台文字或控件负责。图标本身不承担“已连接”的状态含义。
- 共享类使用 `brand-platform-icon` / `brand-platform-label`；不复用旧 `.platform-label` 的布局规则，不改变页面业务状态。公开来源的机构或发布者名称应保留原文，必要时使用图标加原来源名。
- [必要契约测试](../desktop/tests/ui/platform.test.tsx) 覆盖别名、未知回退、装饰性语义、尺寸和无远程图像 URL。图标在各页面的可见集成由主任务另验收。
