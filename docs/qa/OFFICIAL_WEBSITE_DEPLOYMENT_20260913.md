# 意客 AI 官方网站部署记录（2026-09-13）

## 线上入口

- 官网：<https://www.tuokexing.net/>
- 服务器：`101.200.137.138`
- DNS：`www.tuokexing.net A 101.200.137.138`
- 裸域 `tuokexing.net` 当前没有 A 记录，因此本次只发布 `www` 子域。

## 发布版本

- Gitee：`yike-ai2026/main`
- 源码提交：`3fda66ee69d65f9a93848d19ecd213ba54f209b3`
- 发布目录：`/www/wwwroot/www.tuokexing.net/releases/3fda66ee69d65f9a93848d19ecd213ba54f209b3`
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

官网首页已包含：目标客户与使用场景、商机工作台与客户情报 CRM、发现/判断/触达/经营四步链路、机会证据样例、平台连接说明及 7 天试点入口。首屏、商机工作台和客户情报 CRM 已加入统一风格的产品插图，多平台信号区增加信号汇聚视觉；首页文案已改为面向所有主动获客企业，突出全网公开信息智能挖掘；首屏收敛为“客户还没开口，意客 AI 先发现”，仅保留两项信任提示与两个动作；右侧使用真实机会详情界面，展示原文证据与联系准备；首屏主按钮直达脱敏机会样例，并明确试用可获得机会记录、原文证据和跟进草稿；新增可切换的“原文证据—匹配判断—建议动作”样例、试用准备表单、平台连接状态说明和移动端固定入口，详细能力下沉到后续区块。示例机会明确标注为示例，不代表客户业绩。
