# 意客 AI 官方网站部署记录（2026-09-13）

## 线上入口

- 官网：<https://www.tuokexing.net/>
- 服务器：`101.200.137.138`
- DNS：`www.tuokexing.net A 101.200.137.138`
- 裸域 `tuokexing.net` 当前没有 A 记录，因此本次只发布 `www` 子域。

## 发布版本

- Gitee：`yike-ai2026/main`
- 源码提交：`3413e9a`
- 发布目录：`/www/wwwroot/www.tuokexing.net/releases/6959d50766aa92d96f65ba704acd35bf46fd33f0`
- 当前软链：`/www/wwwroot/www.tuokexing.net/current`
- 站点类型：独立静态站点，不占用 `yike.tuokexing.net` 的应用和运营后台配置。

## HTTPS 与 Nginx

- 独立 vhost：`/www/server/panel/vhost/nginx/www.tuokexing.net.conf`
- 80 端口：ACME 挑战，其余请求 308 跳转 HTTPS。
- 443 端口：静态文件服务，使用独立 Let's Encrypt 证书。
- 证书：`/etc/letsencrypt/live/www.tuokexing.net/fullchain.pem`
- 当前证书有效期至 `2026-12-12`，Certbot 已配置自动续期。
- 服务器执行 `nginx -t` 通过并已 graceful reload。

## 线上验收

以下路径均通过公网 HTTPS 返回 200：

- `/`
- `/products/workbench/`
- `/products/crm/`
- `/features/`
- `/download/`
- `/roadmap/`
- `/contact/`
- `/faq/`
- `/security/`
- `/scenarios/`
- `/privacy/`
- `/terms/`
- `/filing/`
- `/insights/multi-platform-monitoring/`

官网已加入搜索与 AI 抓取基础：每个路由有独立 title、description、canonical、Open Graph/Twitter 元信息和 JSON-LD；各页面在 JavaScript 执行前保留可抓取的语义正文；`robots.txt`、`sitemap.xml`、`llms.txt` 和 FAQ 已上线。产品范围统一按已授权平台与当前可访问公开来源表述，不把规划能力写成已交付能力。

官网首页已包含：目标客户与使用场景、商机工作台与客户情报 CRM、发现/判断/触达/经营四步链路、机会证据样例、平台连接说明及 7 天试点入口。首屏、商机工作台和客户情报 CRM 已加入统一风格的产品插图，多平台信号区增加信号汇聚视觉；首页文案已改为面向所有主动获客企业，突出全网公开信息智能挖掘；首屏收敛为“客户还没开口，意客 AI 先发现”，仅保留两项信任提示与两个动作；右侧使用真实机会详情界面，展示原文证据与联系准备；首屏主按钮直达脱敏机会样例，并明确试用可获得机会记录、原文证据和跟进草稿；新增可切换的“原文证据—匹配判断—建议动作”样例、试用准备表单、平台连接状态说明和移动端固定入口，详细能力下沉到后续区块。示例机会明确标注为示例，不代表客户业绩。

本次发布新增内容中心视觉资产：内容洞察页主视觉、文章卡片配图和文章详情封面，统一表达“公开内容信号 → 证据判断 → 销售下一步”。资产位于 `website/public/illustrations/insights/`，采用 WebP 压缩，文章配图均有描述性替代文本。

本次交互精修补充：桌面与移动端首屏内容使用克制的渐入、产品视觉轻浮动和卡片悬停反馈；窄屏菜单固定在右上角，小屏隐藏重复的顶部预约入口，并保留 `prefers-reduced-motion` 降级。

本次官网运营精修补充：下载页增加 macOS、Windows、Web 和部署状态徽章及产品缩略图；能力全景在移动端改为信息卡；联系页增加“业务输入 → 证据整理 → 下一步”流程图；文章详情增加目录锚点和阅读进度；Footer 增加隐私政策、服务协议、备案信息入口，其中备案号在正式核验前不展示；7 张大尺寸产品 PNG 转为 WebP，源文件保留用于回滚，页面引用和 OG 图片已同步。

本次精修补充：能力全景、适用场景、下载与试用三页首屏配图；小红书、抖音、B站、知乎和公开网页使用统一尺寸的平台图标；首页在 1240px 以下切换单列避免产品图裁切；移动菜单支持 `aria-expanded`、Escape 关闭和点击链接收起；全局加入键盘焦点样式、减少动画设置和移动端底部安全间距；文章分享图与 Article JSON-LD 按页面使用对应视觉资产。

试用表单现在会根据剪贴板权限显示真实结果：自动复制成功时提示已复制，失败时直接展示可手动复制的内容；文章移动端保留底部试用入口。
