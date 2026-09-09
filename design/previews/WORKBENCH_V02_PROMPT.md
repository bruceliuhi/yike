# 意客AI V0.2 设计预览生成记录

日期：2026-09-09。方式：内置 image_gen。单张精修，沿用用户已选择的蓝白左侧导航方向。
状态：设计预览，新增导航表示拟开发范围；未实现或发布新功能。
输出：`workbench-blue-v02-full-navigation.png`。
生成记录 ID：`exec-b1e92e19-ea4d-4448-a0aa-b293a76f57df`；仓库内输出见 [设计图](workbench-blue-v02-full-navigation.png)，读取与实现不依赖本机缓存。
输入：现有 workbench-blue-logo-v1.png、yike-logo-blue-v1.png、用户提供的万流汇截图，三张实际路径均传给 image_gen。
视觉检查：已查看生成结果；八个导航、原始证据、样例/待复核/未入库标识、未发送草稿均可见；未加入虚构业绩。真实组件字号、布局尺寸与交互待实现后验证。
规范：沿用用户蓝白技术风、现有 Logo，按 ui-ux-pro-max 的层级/对齐/对比度/可操作性原则；其本地 scripts 为失效路径占位文件，未成功运行检索脚本，不宣称生成过自动规范结果。

## 完整提示词

Use case: ui-mockup. Asset type: a single refined desktop web-app UI design for 意客AI, Chinese B2B business-opportunity software. This is one revision of the already-selected blue-white left-sidebar direction, NOT three alternatives.

Input images: image 1 is the current workbench mock to redesign; image 2 is the exact blue Y brand mark to preserve and place in the sidebar; image 3 is a competitor screenshot provided ONLY to inspire a coherent grouped navigation and workflow breadth. Do not copy its black/lime colors, name, watermark, account names, counts, or form.

Target dimensions: 1440 x 1024. Natural desktop viewport, app content only, no browser/device frame. Ultra crisp product UI, understated refined light tech aesthetic similar to Feishu/Alipay cleanliness, no gradients except the existing logo, no promotional poster. Use white main canvas, subtly cool sidebar #F7F9FC, blue #1677FF and active background #E6F4FF, strong text #172B4D, secondary #66758C, light rules #E8EDF3. Chinese PingFang SC / Noto Sans SC, consistent 14px body; title 24px medium; sections 16px medium; helper 12px. Thin coherent line icons. Sidebar width 208px. Header 60px. Content gutters 28-32px. Controls 34px high, modest 6px corners. Use spacing, alignment and separators first; no nested cards, no shadows, no charts, no KPI cards, no fake activity. This should feel like a carefully composed real work surface, not a spacious slide.

The user is expanding product scope to login/authorization, lead collection, monitoring and outreach. Those NEW NAVIGATION destinations below represent PROPOSED V0.2 scope, not implemented functionality. State exactly "V0.2 设计预览" in a small neat top-right label so this entire frame is clearly a concept. Do not mark invented integrations as connected or any message as sent.

Sidebar: at top exact blue Y logo visibly 32x32, wordmark "意客AI" 20px. Small secondary "商机工作空间". Eight nav destinations total, with purposeful quiet grouping and plenty of spacing between groups but compact 40px item rows:
standalone "商机工作台";
group label "发现商机": "业务画像", "线索采集", "监控任务";
group label "推进商机": "商机库" (active, blue text/light-blue flat selection), "触达中心", "跟进记录";
near sidebar bottom separated by a rule: "账号与授权".
Very bottom small "演示工作空间", with no made-up person or avatar.

Main screen is a FULL OPPORTUNITY DETAIL, not list and detail combined. Header breadcrumb: "商机库 / 机会详情", simple back arrow, top-right V0.2 design-preview label. No search box, no table, no filters, no disabled export, no generic global buttons. One opportunity only, shown only once.
Detail headline: "180㎡高交会展区设计搭建预算询价".
Subtitle: "湖南省商务厅对外贸易发展处".
Compact context line: "公开研究样例 · 待人工复核 · 未入客户库". Clear but not a large warning box.
Single compact metadata strip with 4 aligned columns:
"需求阶段" → "预算编制市场询价";
"项目地点" → "深圳国际会展中心";
"展区面积" → "180㎡";
"资料截止" → "09-15 18:00".
Current date is 2026-09-09. Do not invent dates; source was published 2026-09-08 16:54. No score or estimated revenue.

Below, divide remaining content into evidence main column about 68% and draft support column 32%, separated by a fine vertical line, no boxed outer cards. Left is dominant:
Section "原文证据", with the SINGLE PRIMARY blue action "查看官方原文" aligned to its right, small external-link icon.
A tasteful pale-blue quote band, very restrained thin blue left rule, exact quote "本次报价仅用于预算测算".
Below compact source line "湖南省商务厅官网 · 发布于 2026-09-08 16:54".
Short needs summary exact: "180㎡展区，涵盖设计、搭建、维护、撤展和组展服务。"
Then a well-proportioned evidence assessment list with light horizontal separators and aligned short labels and text:
"匹配依据" : "买方公开征询服务方案与成本；适配需结合地域、施工及组展能力。"
"行动信号" : "9月15日18:00前递交资料，可评估是否参与预算询价。"
"机会价值" : "适合提前了解需求；预算、合同和收入尚未确定。"
"需要核实" : "不确定供应商、不签合同，参与不带来后续招标优先资格。"
Use calm dark neutral text, a very small muted amber symbol beside last label if useful. No pill for every phrase.
A final compact source/contact section after a rule: "联系渠道" followed by "以官方公告的采购咨询电话、资料邮箱及递交要求为准。". Do not invent phone or email, no social private-message link because this source is a government notice.

Right support column: heading "联系准备", small "待校对 · 未发送". One modest editable-looking white text area (height about 210-240px) labeled "询问草稿", exact draft:
"您好，关注到本次高交会展区预算询价。请问展位技术资料及组展服务范围如何获取？我们会先核实自身能力，再按公告要求准备资料。理解此次仅用于预算编制，后续采购以正式公告为准。"
Secondary OUTLINE button "复制草稿", not a large blue CTA.
Under it small secondary "按公告要求联系采购方". Below subtle divider and a short note labeled "样例状态": "仅供研究查看，尚未绑定客户画像。"
No empty followup card, no disabled AddFollowup button, no automatic sending, no fake progress or success status.

Compose content to use screen height naturally with compact balanced typography and alignment; no huge unused half-screen voids or oversized titles. The screenshot should have visual confidence and coherent scope while remaining completely truthful about the one provided real public sample. Preserve exact brand shape. Everything in Chinese must be crisp and correct. Render one image only.
