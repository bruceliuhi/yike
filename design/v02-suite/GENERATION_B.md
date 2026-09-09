# 页面生成记录 B：P05–P09、P20

日期：2026-09-09。内置 image_gen，每页独立顺序生成；未使用 CLI/API 回退。图片保留原始尺寸并原样复制。
P05–P09 的两张参考均已打开查看，每次实际附入：`../previews/workbench-blue-v02-full-navigation.png`、`../brand/yike-logo-blue-v1.png`。P20 使用三张参考，见下节。
逐页完整提示词见 `prompts/Pxx.txt`。这是静态设计，尚无功能实现或真实运行验收。

## P20 持续监控设置

P06 选择持续监控后的同页面状态。完整提示词见 [P20.txt](prompts/P20.txt)。内置 image_gen 独立生成；生成前已逐张查看，并实际附入 [P06](screens/P06.png)、[P11](screens/P11.png)、[Logo](../brand/yike-logo-blue-v1.png) 三张参考。

| 生成 ID | 原始输出 | 工作区文件 | 尺寸 |
|---|---|---|---|
| exec-9b7f5fe9-3d29-4012-b347-fc75de3b90ad | generated_images/01a0845b-4bf9-76e1-b074-e0894a11fd3c/exec-9b7f5fe9-3d29-4012-b347-fc75de3b90ad.png | screens/P20.png | 1487×1058 |

静态观察：保持线索采集导航高亮及步骤 1；画像未选择、五平台及连接状态明确。持续监控选中后展开每日/每隔、两行可编辑时间 09:00 与 15:00、删除与添加时间、Asia/Shanghai（北京时间）和单行离线提示；未将每日两次写成固定能力。页面为配置示例，未显示运行结果、客户业绩或真实账号。全图已查看，控件和页脚完整可读。原样复制 PNG，原始输出与工作区文件 SHA256 均为 `2f42c9f93be678ab27fa1cfb97570edb93ed18dc3010d2494a418e332c9a518d`。

## P05–P09

| 页面 | 生成 ID | 原始输出 | 工作区文件 | 尺寸 | 静态观察 |
|---|---|---|---|---|---|
| P05 线索采集任务 | exec-1008ee65-bc6b-4730-8fb7-5bc8a77e4c69 | generated_images/01a0845b-4bf9-76e1-b074-e0894a11fd3c/exec-1008ee65-bc6b-4730-8fb7-5bc8a77e4c69.png | screens/P05.png | 1486×1059 | 八入口、线索采集高亮、草稿配置示例、最近执行与原始线索为 —；未造运行结果。一次精修去除模板空态插画和重复说明，保留单行空态。 |
| P06 新建获客任务 | exec-c686fbeb-3d03-4d2c-a228-8b92f737cec7 | generated_images/01a0845b-4bf9-76e1-b074-e0894a11fd3c/exec-c686fbeb-3d03-4d2c-a228-8b92f737cec7.png | screens/P06.png | 1484×1060 | 三步流程、关键词/排除词、多平台勾选、单次采集与持续监控；社交平台均未连接，无虚假账号或结果。一次精修删除右侧多余说明，只保留平台表和单行连接提醒。 |
| P07 原始线索复核 | exec-58c98a81-e22a-4065-bf8c-6da9d3d0437b | generated_images/01a0845b-4bf9-76e1-b074-e0894a11fd3c/exec-58c98a81-e22a-4065-bf8c-6da9d3d0437b.png | screens/P07.png | 1485×1059 | 单条公开研究样例，待复核且未入客户库；未绑定画像，确认入库禁用；原文、询价阶段、无合同与无优先资格风险保留。 |
| P08 监控任务 | exec-b6e4d870-6ab5-4872-9414-6358fd03d0ac | generated_images/01a0845b-4bf9-76e1-b074-e0894a11fd3c/exec-b6e4d870-6ab5-4872-9414-6358fd03d0ac.png | screens/P08.png | 1487×1058 | 监控任务高亮；一条配置示例，待配置/平台待完成；执行与新增均 —；每日2次明确本机在线时执行，启动禁用。底部“创建第一个任务”应在落地文案中收紧为“创建新任务”，避免与配置示例混淆。 |
| P09 监控运行详情 | exec-9c743020-99e6-47ae-812c-e95676458feb | generated_images/01a0845b-4bf9-76e1-b074-e0894a11fd3c/exec-9c743020-99e6-47ae-812c-e95676458feb.png | screens/P09.png | 1487×1058 | 明确状态示意/无真实运行数据；小红书登录失效、抖音暂时受限、其余等待执行；所有执行新增均 —；重新连接主操作，无法读取不记为无新增。 |

P07–P09 使用对应完整提示词后追加以下统一约束：

```text
Reference image 1 is ONLY the shell/style reference; do not copy its opportunity title, source or breadcrumb except where this page brief explicitly requests them. Do not invent subtitles or long explanatory paragraphs. Keep the layout compact and product-like. One primary action per page. Show state-demonstration identity once, not repeatedly in each panel.
```

## P07 定向精修

初稿 ID：`exec-c721fb1c-9f53-4395-be6d-5abb69096961`，原始路径 `generated_images/01a0845b-4bf9-76e1-b074-e0894a11fd3c/exec-c721fb1c-9f53-4395-be6d-5abb69096961.png`。未采用初稿：缺少未入客户库标签，风险文案泛化。精修附初稿、既定外壳及 Logo 三图，最终如上。

```text
Use case: precise-object-edit. Edit ONLY two text areas in image 1, the P07 original lead-review desktop screen. Preserve every other element: full 1487x1058 canvas, logo, exact sidebar/nav, spacing, columns, title, public inquiry metadata, colors, filters, selected row and controls. Image 2 is the approved shell/style reference; image 3 is exact logo reference, do not copy their content. First, beside the right review heading keep 公开研究样例 and 待复核 and add a clearly readable compact 未入客户库 status. Second, replace the three bullet lines under 需核实事项 with EXACT text: 预算金额未公开，需进一步核实 / 本次不确定供应商、不签合同 / 参与不带来后续招标优先资格. Keep line lengths sensible, use natural wrap if needed. Do not invent additional sources, accounts, financial values, outcomes, metrics or paragraphs. Do not redesign or move components. Output one complete polished screen.
```

## P06 定向精修

初稿 ID：`exec-a3ccacda-69b5-4ad0-ab28-002fb98b1097`，原始路径 `generated_images/01a0845b-4bf9-76e1-b074-e0894a11fd3c/exec-a3ccacda-69b5-4ad0-ab28-002fb98b1097.png`。按主审要求删除右侧重复说明。精修附初稿、既定外壳及 Logo 三图。

```text
Use case: precise-object-edit. Image 1 is the EDIT TARGET P06 new acquisition task screen. Image 2 is only the approved shell style reference and image 3 is the exact logo. Make ONLY these cleanup changes on the right support column: remove the entire section heading 任务说明, its three numbered instruction lines, the lower divider and the paragraph starting 本次为公开研究样例任务. Replace the blue connection information box with ONE short unboxed helper line: 请在下一步完成平台连接. Keep the platform connection status table showing four unconnected platforms and the public-website row unchanged. Keep the complete left form, labels, values, all five platform selections, all radio controls, three-step progress, sidebar, wordmark, shell, primary 下一步：连接平台 and secondary 保存草稿 buttons exactly as they are. Do not add replacement panels, prose, decorations or new UI. Preserve the original 1487x1058 whole-screen proportions. Leave deliberate clear whitespace in the right column below the single helper line. No new customer data, no performance, no connected identities. Output one complete polished screen.
```

## P05 定向精修

初稿 ID：`exec-4322d7e3-69ef-4ee1-a742-a27d0d16dfde`，原始路径 `generated_images/01a0845b-4bf9-76e1-b074-e0894a11fd3c/exec-4322d7e3-69ef-4ee1-a742-a27d0d16dfde.png`。按主审要求删除模板插画及重复说明。精修附初稿、既定外壳及 Logo 三图。

```text
Use case: precise-object-edit. Image 1 is the EDIT TARGET P05 lead collection task list. Image 2 is the approved shell reference and image 3 is the exact blue logo. Make ONLY a cleanup of the lower 保存的模板 empty-state section. Keep the section heading 保存的模板. Remove both repeated explanatory lines about saving conditions as a template and remove the large empty document illustration. Replace them with ONE short simple left-aligned text line 暂无保存的模板, aligned to the section heading, with natural compact spacing. Do not put this line in a card, do not add new decorations or replacement content. Preserve every other element: sidebar/nav, header, logo, task table, filters, 配置示例 draft, dashes instead of execution counts, connection reminder, primary 新建获客任务 button, exact canvas and layout proportions. Keep no real execution claims. Output one complete polished screen.
```
