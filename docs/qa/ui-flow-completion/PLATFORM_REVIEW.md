# 平台品牌增量：独立代码审核

审核人：Agent C。日期：2026-09-09。

**结论：本报告独立范围 PASS，未发现新增或未解决的 P0/P1。** 品牌源码绑定 **`1c1567325bca971a723c87983efb0c289c57e03a`**，比较基线为业务源码 `237a5b2a6be4f68682fcae4312f338e2338a3646`。本报告允许所审品牌增量进入候选交付，不替代原生包、浏览器可见、Windows 实机或真实业务接口验收。

## 独立范围

- A 编写的 `desktop/src/renderer/components/Platform.tsx`、`platform.css`、四个本地平台图像、`tests/ui/platform.test.tsx` 及 [资源来源记录](../../PLATFORM_BRAND_ASSETS.md)。
- 主 Agent 编写的 `Connections.tsx` 和 `base.css` 品牌接线。
- B 编写的 `Opportunities.tsx`、`Outreach.tsx`、`pages/followups/RelatedReplies.tsx` 品牌接线。

**排除 C 自作代码：** TaskWizard、Tasks、pages/tasks 的品牌接线及相关模板测试不由本报告作独立代码批准，仍由其他 Agent 交叉审核。本轮完整测试包含这些文件，但测试通过不等于独立自审。此前业务审核范围见 [CODE_REVIEW.md](CODE_REVIEW.md)。本报告没有修改产品源码、测试或资源。

## 核对结果

共享组件通过四个本地静态 import 加载原图，无运行时 HTTP 地址、CSS 外部 URL、fetch 或动态脚本。图标仅装饰，容器 `aria-hidden`、图片 `alt=""`，平台名称由相邻文本保留。平台标签沿用产品已有名称，公开网站使用既有 Globe。别名表用自有属性检查；未识别的平台保留输入原名并回退 Globe，`constructor` 不触发原型属性映射，TikTok 不映射为抖音。没有新增依赖或平台能力声明。

Connections 保留原生 select 的文字选项、平台选择处理和连接/断开前提，只在旁边加相应图标。列表及连接中反馈使用同一品牌组件。base.css 新增选择控件横排样式，并将 `.fact-strip span` 收紧为直接字段选择器，避免品牌组件内部 span 被当成指标标题；没有新增业务状态分支。

Opportunities 的公开来源保留机构或发布者原文：有 sourceLabel 时为图标加原来源名，未将“湖南省商务厅官网”等信息替换成泛化平台名。来源元数据、列表、详情和候选页只变更呈现。Outreach 列表和发送确认展示实际平台/渠道，确认版本、身份、能力、未知发送记录及操作条件未改变。RelatedReplies 只将平台文本接入品牌标签，读取状态和关联行为不变。

四个本地文件的格式、大小和 SHA-256 与资源记录一致：

| 文件 | 格式 / 大小 | 本轮核对的 SHA-256 |
| --- | --- | --- |
| xiaohongshu.png | PNG，180×180，2,482 字节 | `2912c4df1ab479d734ef132e9c45b4f17afa80b2aa3eaf4438acd54afc70b20a` |
| douyin.ico | ICO，32×32，4,286 字节 | `e67348e3ab54fa207e1ce4be78e8399d1b73a794d819a17d8656ea2b17a1109d` |
| bilibili.ico | ICO，32×32，4,286 字节 | `2681561eb24e7435fea1acf26f3af95e4efc9f7d451587b58bef62f030f337e9` |
| zhihu.ico | ICO，32×32，4,286 字节 | `ca501e1d6c35f64b94d78bbabad986fe888d6aab08702a0083ba88076ad60f37` |

官方站点/CDN 下载来源和原始字节保留由 A 的资源记录提供；C 独立检查了记录、代码引用和本地摘要，没有重新联网下载。C 可直接查看 PNG；当前图像查看工具不支持 ICO，三个 ICO 的可见渲染由主任务浏览器/原生验收另行覆盖。来源记录没有把图标使用表述成平台授权、连接成功或商标许可。

## 实际验证

执行目录 `desktop`，使用项目指定 Node 24 runtime。会话输出标识是检索依据，不是仓库内完整日志；不同阶段重叠测试不累加计数。

| 检查 | 结果 | 会话输出 |
| --- | --- | --- |
| `npm test` | **50 个文件，493 passed** | `2060bd` |
| `npm run typecheck` | 通过 | `2060bd` |
| `git diff 1c1567325bca971a723c87983efb0c289c57e03a --exit-code -- src tests package.json package-lock.json` | 通过，测试时源码、测试及依赖声明/锁文件与品牌提交一致 | `2060bd` |
| 四个资源的 `shasum -a 256` 与 `file` | 格式及摘要符合上表 | `defe80` |
| 组件/CSS 的外链及动态请求静态检查 | 无匹配；rg 的退出码 1 表示未发现目标模式 | `defe80` |
| `git diff --check` | 通过 | 本轮检查 |

写入报告时 HEAD 已为正常整合提交 `3228962bf57c047f33ea4333cc21dc5c6ee9d589`；再次检查 `git diff 1c1567325bca971a723c87983efb0c289c57e03a HEAD -- desktop` 为空。因此桌面代码结论可继承到该整合提交，报告没有独立批准其新增后端或文档变化。

测试使用隔离 fixture，不执行真实平台连接、采集或外部触达。原生包重建、平台图标实际显示、小屏布局、Windows 安装及真实接口状态由各自证据报告确认，不从本次静态和组件测试推导成功。
