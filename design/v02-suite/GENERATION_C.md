# 设计套图生成记录 C

最新修订见文末“P12/P13 草稿与样例发送边界精修”；其结果覆盖前文对应交付路径。

日期：2026-09-09。方式：内置 image_gen；每张独立顺序生成，两张实际参考均已查看并传入。未使用 CLI 或代码绘制，不修改产品代码。

参考：[工作台风格](../previews/workbench-blue-v02-full-navigation.png)、[Y Logo](../brand/yike-logo-blue-v1.png)。父任务已完成设计 brief 与 preflight；本组沿用既定蓝白方向，页面套图数量覆盖默认三方案。

## P12 触达中心

- 提示词：[P12.txt](prompts/P12.txt)。
- 生成 ID：`exec-d4ec6dad-f6fa-49b2-b3cb-4b493ab4c272`。
- 原路径：`generated_images/01a08464-f648-7a81-8581-b38ad327f51a/exec-d4ec6dad-f6fa-49b2-b3cb-4b493ab4c272.png`。
- 交付：[P12.png](screens/P12.png)，1487 × 1058 PNG，原样复制。
- 视觉检查：八入口和触达中心选中状态正确；三栏草稿编辑/来源证据布局清晰。收件对象待核对、渠道未选择、准备发送灰显；公开研究样例及未发送标识明确，没有虚构联系人、真实发送或回复。生成图附加的字数计数与提示仅为静态视觉，落地必须由真实字段计算。
- 未验证：实际交互、字数计数、响应式、可访问性及发送能力；全套需用户统一确认后再实现。

## P13 发送确认

- 提示词：[P13.txt](prompts/P13.txt)。
- 生成 ID：`exec-53ca830b-4b56-4024-ae40-d7a138f8aafe`。
- 原路径：`generated_images/01a08464-f648-7a81-8581-b38ad327f51a/exec-53ca830b-4b56-4024-ae40-d7a138f8aafe.png`。
- 交付：[P13.png](screens/P13.png)，1487 × 1058 PNG，原样复制。
- 视觉检查：居中发送确认弹窗、渠道/账号/对象/来源/内容信息齐全；勾选框未选中，确认并发送灰显。背景保留样例、未复核/未入库、尚未发送，历史触达为空，没有虚构联系人、发送成功或回复。
- 未验证：弹窗焦点、Esc/关闭、确认快照失效、真实发送与回执；这是静态状态设计。

### P13 流程背景一致性修订（最终交付）

- 主审要求：初稿背景是不同的触达详情布局，需统一为 P12 的三栏草稿页面。
- 最终生成 ID：`exec-e86b8f58-f9e5-4fcf-a774-260de3e2ddfa`。
- 最终原路径：`generated_images/01a08464-f648-7a81-8581-b38ad327f51a/exec-e86b8f58-f9e5-4fcf-a774-260de3e2ddfa.png`。
- 原样替换 `screens/P13.png`，1487 × 1058；上文初稿不再作为最终交付。
- 复查：背景为 P12 草稿箱、选中样例及原文证据；确认字段、未选复选框、灰显发送按钮保留；不存在虚构收件人或发送记录。

完整修订提示词（依序附 P12、P13 初稿、工作台风格、Y Logo）：

```text
Use case: compositing. Produce ONE corrected full desktop UI screenshot, 1487x1058 natural dimensions. Image 1 is the REQUIRED BACKGROUND: existing P12 触达中心 with three columns (draft list, editable draft, related original evidence), tabs 草稿箱/待确认/待回复/需处理 and active 触达中心 sidebar. Image 2 supplies ONLY the exact central white '确认发送' modal and its soft grey scrim; ignore its different underlying page entirely. Image 3 is previous shell/style reference only; image 4 is the existing Y logo reference. PRIMARY REQUEST: Take image 1 as the complete unchanged base, put a subtle grey modal backdrop over the content area, and overlay the central white modal extracted from image 2 at the same size and position. Keep image 1's sidebar clear and legible. Outside the modal, preserve image 1's exact three-column structure, tabs, selected draft, fields, evidence and buttons. Do NOT invent a different outreach-detail page, new history table, cards, dates, people or buttons. Inside the modal preserve all of image 2's labels and states exactly: 确认发送; 渠道 请选择已连接渠道; 发送账号 待确认; 收件对象 待核对; 关联来源 高交会展区预算询价（公开研究样例）; 发送内容预览 with 您好，想咨询本次展区预算询价的技术资料获取方式。; unchecked 我已核对联系对象、发送账号和内容; 填写并核对对象后可发送; 返回修改; disabled 确认并发送; close X. All content remains unsent and unconfirmed. Preserve original blue-white typography/controls/logo; no fake contact identity, success, reply, or metrics. Do not alter the modal's fields or wording. This is a background replacement to make this confirmation state visibly part of the exact P12 flow.
```

## P14 回复与跟进

- 提示词：[P14.txt](prompts/P14.txt)，末尾追加约束见下。
- 生成 ID：`exec-84524a8a-3d9d-4d60-8d1d-141ba359d68d`。
- 原路径：`generated_images/01a08464-f648-7a81-8581-b38ad327f51a/exec-84524a8a-3d9d-4d60-8d1d-141ba359d68d.png`。
- 交付：[P14.png](screens/P14.png)，1487 × 1058 PNG，原样复制。
- 视觉检查：跟进记录选中，待跟进/回复记录/全部标签及负责人/日期筛选完整。主表与关联回复均为空，通道回复/人工登记分开，唯一主按钮为添加跟进；无虚构客户、回复、会议或询价数据串入。
- 未验证：筛选、新增、事件关联、键盘与空态交互；这是静态空状态设计。

追加完整提示词：

```text
Reference image 1 is ONLY visual style and shell; never copy its opportunity title, source, dates, or breadcrumb except if this current screen brief explicitly asks. For this followup empty-state screen do not include any inquiry title or source. Use only requested concise labels; avoid extra subtitles, long explanations, extra primary buttons, or a dense right column. Preserve empty followup and reply states.
```

## P15 添加跟进

- 提示词：[P15.txt](prompts/P15.txt)，末尾追加约束见下。
- 生成 ID：`exec-e53bedb5-6d4e-4feb-87aa-7e7499faac1b`。
- 原路径：`generated_images/01a08464-f648-7a81-8581-b38ad327f51a/exec-e53bedb5-6d4e-4feb-87aa-7e7499faac1b.png`。
- 交付：[P15.png](screens/P15.png)，1487 × 1058 PNG，原样复制。
- 视觉检查：右抽屉覆盖空态跟进页面，导航仍清楚；商机未选择，事实类型均未选，时间/备注/下一步/负责人字段齐备，明确人工登记与渠道回执分开展示。没有预填客户或假回复/记录。
- 未验证：必填校验、保存、负责人解析、日期选择与抽屉焦点。初稿背景差异已由下面的流程一致性修订处理。

追加完整提示词：

```text
Reference image 1 is ONLY visual style and shell; never copy its opportunity title, source, dates, or breadcrumb except if this current screen brief explicitly asks. For this add-followup drawer show no inquiry title or source, no already selected business opportunity. Use only requested concise labels; avoid extra subtitles, long explanations, extra primary buttons, or dense notes. Preserve the empty form and all specified unselected controls.
```

### P15 流程背景一致性修订（最终交付）

- 主审要求：初稿底层筛选和表格与 P14 不同，需统一同一跟进流程。
- 最终生成 ID：`exec-6e835e65-b4a1-4d5e-9ec7-cfe17f0e1f40`。
- 最终原路径：`generated_images/01a08464-f648-7a81-8581-b38ad327f51a/exec-6e835e65-b4a1-4d5e-9ec7-cfe17f0e1f40.png`。
- 原样替换 `screens/P15.png`，1487 × 1058；上文初稿不再作为最终交付。
- 复查：背景恢复 P14 的三标签、负责人/日期筛选及原表格列，右侧关联回复由抽屉覆盖；空态及抽屉所有未填写/未选事实状态保留。无新联系人、已保存记录或回复。

完整修订提示词（依序附 P14、P15 初稿、工作台风格、Y Logo）：

```text
Use case: compositing. Produce ONE corrected full desktop UI screenshot at 1487x1058, no crop or collage. Image 1 is the REQUIRED COMPLETE BACKGROUND: P14 跟进记录 with tabs 待跟进/回复记录/全部, 负责人 and 日期 filters, 添加跟进 button, empty followup table and right 关联回复 empty panel. Image 2 supplies ONLY its exact right-hand white 添加跟进 drawer and grey scrim. Ignore image 2's different underlying table/filter page entirely. Image 3 is old shell/style reference only; image 4 is the exact blue Y logo. PRIMARY REQUEST: use the whole of image 1 unchanged as base, darken content with a subtle grey drawer scrim, then overlay the exact white drawer from image 2 along the right edge at its original width and same full-height position. Preserve image 1's sidebar and active 跟进记录; behind the drawer preserve all its visible tabs, two filters, main table column order, empty state typography and row lines. The drawer covers the right 关联回复 panel rather than moving or redesigning the underlying page. Do not introduce new filters, table columns, subtitles, customers or followup facts. DRAWER INVARIANTS: title 添加跟进 and close X; 关联商机 请选择已入库商机; 跟进类型 人工登记; 事实类型 radio 已联系 / 已回复 / 已约谈 / 已报价 with NONE selected; 联系时间 选择实际发生时间; 备注 empty 写下实际沟通内容; 下一步 empty; 下次跟进 选择日期; 负责人 当前成员; small 手工记录会标记为人工登记，与渠道回执分开展示。; primary 保存记录 and secondary 取消. Preserve its exact labels, layout, control sizes and unfilled states. Do not invent identity, name, dates, saved record, successful contact, reply, meeting or quote. This is strictly background replacement so this drawer visibly belongs to the exact P14 followup screen.
```

## P18 设备与使用授权

- 提示词：[P18.txt](prompts/P18.txt)，首次追加约束和修订提示词见下。
- 初稿 ID：`exec-fc179e31-f18d-4398-b4af-f0c280934b9c`，原路径：`generated_images/01a08464-f648-7a81-8581-b38ad327f51a/exec-fc179e31-f18d-4398-b4af-f0c280934b9c.png`；初稿自行添加本地数据措辞，与服务端客户数据架构不符，未作为最终交付。
- 最终生成 ID：`exec-28298dce-d7fc-4d56-9fb8-e35106841391`。
- 最终原路径：`generated_images/01a08464-f648-7a81-8581-b38ad327f51a/exec-28298dce-d7fc-4d56-9fb8-e35106841391.png`。
- 交付：[P18.png](screens/P18.png)，1487 × 1058 PNG，原样复制修订结果。
- 视觉检查：账号与授权选中，设备与使用授权标签选中；未激活、尚未绑定、版本/有效期未知，无假收费套餐或授权身份。激活为唯一主按钮，数据与诊断保持业务标签；已移除自行生成的本地数据及冗余解释。
- 未验证：真实激活、设备管理、版本检查、导出/恢复与诊断功能；这是静态设计。

首次追加完整提示词：

```text
Reference image 1 is ONLY visual style and shell; never copy its opportunity title, source, dates, or breadcrumb except if this current screen brief explicitly asks. For this settings screen do not include any inquiry title, source, sample business opportunity, or unrelated data. Use only requested concise labels; avoid extra subtitles, long explanations, extra primary buttons, or dense notes. Activation is the only primary action. Show unactivated and unbound states, no invented installed version or license expiry.
```

修订完整提示词（附初稿、工作台风格及 Y Logo）：

```text
Use case: precise-object-edit. Image 1 is the edit target: the entire 意客AI 账号与授权 / 设备与使用授权 desktop design. Image 2 is shell/style reference only. Image 3 is the exact Y brand logo. Output ONE complete screen at the target's exact natural 1487x1058 dimensions, no cropping, no multiple images. Make ONLY this targeted copy cleanup in image 1: in the 版本与数据 section DELETE the explanatory sentence '导出本地数据，用于数据备份或迁移。' beside 导出数据, and DELETE '将本地数据备份或从备份恢复。' beside 备份与恢复. Leave those middle cells simply empty. In 支持与诊断 likewise DELETE the middle explanatory sentences beside 导出脱敏诊断 and 联系支持. Keep the left labels and all right action buttons unchanged. Do not replace these sentences with other explanations. The product stores customer data on a server; do NOT introduce local database wording, server details, implementation terms, extra data, dates, identities, or statuses. Preserve absolutely all other pixels, sidebar, Y logo, eight navigation items and active state, typography, section positions, spacing, row rules, label columns, button locations, white background, 未激活, 尚未绑定, em dashes for version/expiry, and the preview labels. No other revisions.
```

## P12/P13 草稿与样例发送边界精修

本次主审要求：补充低强调的重新生成动作；公开样例不能发送；发送确认必须显示与编辑页完全一致的完整草稿。图中生成动作只是样例演示，真实客户分支按单独条件限制。

### P12 最终精修

- 生成 ID：`exec-db6777dc-529b-4fb3-bab8-d16a685c7018`。
- 原路径：`generated_images/01a08464-f648-7a81-8581-b38ad327f51a/exec-db6777dc-529b-4fb3-bab8-d16a685c7018.png`。
- 已原样替换 `screens/P12.png`，1487 × 1058。
- 复查：沟通内容标题右侧出现低强调“重新生成”；全文草稿保留；脚注为“公开样例仅供预览，不能发送。”，准备发送仍禁用。

完整提示词（附旧 P12、工作台风格、Y Logo）：

```text
Use case: precise-object-edit. Output ONE complete 意客AI P12 触达中心 desktop design at the exact 1487x1058 dimensions. Image 1 is the only edit target; image 2 supplies existing shell/style, image 3 supplies the exact Y logo. Make ONLY these two small changes in the center editing column: (1) On the same horizontal row as the label '沟通内容', add a discreet right-aligned plain text action '重新生成' in small dark blue #0958D9. No filled button, icon, sparkle, new card, or extra explanation; this regeneration action is only a design demonstration for the public sample. (2) Replace the helper footnote immediately BELOW the draft textarea (currently 请基于官方信息，确保内容准确、合规、得体。) with exactly '公开样例仅供预览，不能发送。'. Preserve the entire draft textarea text VERBATIM: '您好，关注到本次高交会展区预算询价。请问展位技术资料及组展服务范围如何获取？我们会先核实自身能力，再按公告要求准备资料。理解此次仅用于预算编制，后续采购以正式公告为准。'. Preserve all other layout, typography, sidebar/logo, three-column widths, header, selected draft, evidence/source, fields, blank recipient, unselected channel, pending-review/not-in-customer-library state, counts, and preview labels. Preserve primary 保存草稿 and grey disabled 准备发送 exactly. Do not make the sample sendable, do not invent a channel, recipient, successful send or reply. No other edits and no crop. Current anchor date is 2026-09-09; preserve all existing source dates.
```

### P13 最终精修

- 生成 ID：`exec-82c09c89-7b68-4274-9c1b-5aadbc7b72f5`。
- 原路径：`generated_images/01a08464-f648-7a81-8581-b38ad327f51a/exec-82c09c89-7b68-4274-9c1b-5aadbc7b72f5.png`。
- 已原样替换 `screens/P13.png`，1487 × 1058。
- 复查：背景使用更新的 P12，底部可见样例不可发送脚注；前景展示同一完整草稿，未缩写。确认框未选、发送按钮灰显，提示为“公开样例未入客户库，当前不可发送”。无真实发送或身份伪造。

完整提示词（依序附更新 P12、旧 P13、工作台风格、Y Logo）：

```text
Use case: compositing and precise text edit. Create ONE complete Chinese 意客AI P13 confirmation-state desktop design at 1487x1058. Image 1 is the REQUIRED updated P12 background, including the discreet 重新生成 action beside 沟通内容 and footnote 公开样例仅供预览，不能发送。 Image 2 is the current P13 with its central white 确认发送 modal; preserve its fields and style. Image 3 is shell/style reference only; image 4 is the exact blue Y logo. Start from image 1 unchanged as the underlying three-column outreach workspace, apply a subtle grey scrim and overlay the white confirmation modal from image 2. Make only these content fixes inside the modal: (A) Replace the shortened 发送内容预览 with this COMPLETE draft, verbatim, all four sentences, no shortening or rewriting: '您好，关注到本次高交会展区预算询价。请问展位技术资料及组展服务范围如何获取？我们会先核实自身能力，再按公告要求准备资料。理解此次仅用于预算编制，后续采购以正式公告为准。' The text must be fully visible. Increase the preview textbox height to roughly 180px if necessary, keep readable 14-16px Chinese text, and enlarge the modal only as needed so all controls fit on screen. (B) Replace the helper above the footer buttons that currently says 填写并核对对象后可发送 with exactly '公开样例未入客户库，当前不可发送'. The public sample must NEVER become sendable merely by filling recipient or checking a checkbox. Keep 确认并发送 visibly disabled and the checkbox unchecked. Preserve fields: 渠道 请选择已连接渠道, 发送账号 待确认, 收件对象 待核对, 关联来源 高交会展区预算询价（公开研究样例）. Preserve title 确认发送, close X, checkbox label 我已核对联系对象、发送账号和内容, 返回修改, footer disabled 确认并发送. Keep the updated P12 actual background structure, sidebar/logo, selected draft/evidence, blank account/recipient/channel, unsent states and V0.2 设计预览. No new customer, actual sent record, reply, metric or dates. This is only a sample confirmation-state preview. Do not add new cards, controls, explanatory paragraphs or product features. Current date 2026-09-09.
```
