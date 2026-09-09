# P04 资料恢复链：a25 实际 TEST 验收

候选：`a25ba7b331e7712c4fba53b173cbbc704ec3e734`。主线程通过 Codex In-app Browser（IAB，browser2）/CUA 操作 `?scenario=P04&state=populated&materials=recovery` 的真实资料页面；本记录独立核对原事件、AX 和截图。服务只使用固定 TEST 画像的内存资料与回执，没有真实 AI 解析、客户库写入或外部资料服务。

本次使用最后点号 ID 修正后的静态 visual build，[最终构建日志](../logs/visual-build-final.log) 和 [source-final-before.json](../source-final-before.json) 保留来源；[build-binding.json](build-binding.json) 是后续重建前保存的 37 文件完整 SHA-256/manifest，供本页和 P12 共用。保存时源码的 296 项与 a25 snapshot 均一致。该清单是运行后采集，不能声称已有运行前完整输出哈希，也不是生产 ASAR 证明。P18 使用的是另一个较早 freeze，见其独立记录。

## 事件与状态

[events.json](events.json) 为 18 条连续事件。`materialRecovery.mutate` 的 `SUCCEEDED` 是底层 TEST 内存动作已经执行、尚未暂扣回执之前的记录；它**不表示产品页已收到终态**。UNKNOWN 场景故意把原操作回执暂扣，直到 TEST release 后用户再次点击产品页查询。

| 路径 | 原始证据 | 可证实结果 |
| --- | --- | --- |
| 保存 → 解析 → 人工确认 | [ready.txt](ready.txt)，events 2–4 | save、parse、confirm 各一次。资料成为版本 3、“已确认”、允许对外引用，并提示业务画像仍需单独保存确认；没有自动确认业务画像。 |
| 取消撤销 | [revoke-cancelled.txt](revoke-cancelled.txt) | 主线程打开影响确认并取消；保存的 AX 仍是版本 3、“已确认”，没有新增撤销执行事件。 |
| 撤销 UNKNOWN，查询并跨路由重入 | [revoke-unknown-route-return.txt](revoke-unknown-route-return.txt)、[1280×720 PNG](revoke-unknown-1280x720.png)，events 5–12 | 撤销一次，首次原请求查询仍未知；转工作台再回资料页后，待确认提示和原请求核对按钮仍存在，添加/编辑/解析/移除禁用。列表重新读取到版本 4、“引用已撤销”，**不能据此推断原请求回执已确认或把 UNKNOWN 当失败**。 |
| 释放原撤销回执并查询 | [revoke-reconciled.txt](revoke-reconciled.txt)，events 13–14 | TEST release 后，再次产品页 query 才移除待确认区、恢复操作入口，显示“资料引用已撤销”；没有第二次撤销。 |
| 取消移除 | [remove-cancelled.txt](remove-cancelled.txt) | 主线程取消影响确认后，版本 4 的已撤销资料仍在；尚未发生移除执行。 |
| 移除 UNKNOWN → release → 原请求查询 | [remove-unknown.txt](remove-unknown.txt)、[remove-reconciled.txt](remove-reconciled.txt)，events 15–18 | 移除一次，首次 query 仍未知并保留保护；release 后第二次 query 显示空列表和“资料已移除”，恢复“添加资料”。 |

原请求次数精确核对：

- 撤销 `c7f80be0-57e4-4e3f-aa3c-6460b006c618`：mutate **1**、query **2**、release **1**。
- 移除 `47d0e28c-622f-4e37-814c-4b04eeb36d19`：mutate **1**、query **2**、release **1**。
- save、parse、confirm 各 **1**；未发现重入导致重复写入。[console.json](console.json) 捕获结果为 `[]`，只代表该次控制台采集没有记录，不扩大为所有运行阶段无错。

## 追加：人工核对后只填入所选画像草稿字段

另开同一 a25 静态 build 的独立 TEST 页，新增内部判断资料，依次保存、解析、人工确认提取内容，再执行“用于画像”。这条链的 [apply-events.json](apply-events.json) 独立从 1 计数：一次 profiles 读取和 save/parse/confirm 各一次，不与前一条 18 事件拼接；没有画像保存或画像确认写事件。

- [apply-preview.txt](apply-preview.txt) 显示资料版本 3、“仅供内部判断”和填入画像草稿弹框；对照当前服务内容 `TEST 展台设计搭建`，提取内容已由人工改成 `TEST 人工核对：展区设计、搭建及现场维护。`。仅“采用服务内容”被勾选，替换确认 checkbox 未勾选时“填入画像草稿” disabled。
- 主线程核对并勾选后填入，再点击“业务描述”。[applied-profile-draft.txt](applied-profile-draft.txt) **实际是离页确认弹框**，不是最终业务描述截图；它同时显示“所选提取内容已填入画像草稿，尚未保存或确认”。保留原文件名，不把文件名当状态证据。
- 明确选择继续离开后，[applied-profile-visible.txt](applied-profile-visible.txt) 的实际路由为 `#/profile`。服务内容与人工文本一致；目标客户、地区、偏好、排除项仍分别是 `TEST 参展企业与展会主办方`、`TEST 湖南、深圳`、`TEST 公开预算询价与布展需求`、`招聘、求职、培训、招生`，与原 TEST 画像字段一致。
- 页面明确显示“未保存修改”及“修改后需保存并重新确认”；画像选择器的“版本 1 · 已确认”是原已存在版本状态，**不代表刚填入的内容已保存、新画像已确认或任务已更新**。

体验观察：资料填入后，切到同一画像的业务描述还要多确认一次“离开当前页面”，会增加操作步骤。实际继续后所选字段已保留，没有资料丢失证据；本次仅记录该提示体验，不将其推断成数据损坏。

## 与已批准 R3 的可见对照

已在同一次图像工具调用中打开 [R3 P04](../../../../design/v02-suite-r3/screens/P04.png) 和 [实际 1484×1060 抽屉](drawer-1484x1060.png)，并查看 UNKNOWN 的 1280×720 图。结论为语义结构与设计规范相符，**不作逐像素一致判定**。

- 保留蓝白壳、Y Logo、八入口分组导航、资料表和右侧“添加资料”抽屉；名称、上传/粘贴、用途、引用范围、取消/保存草稿顺序一致，底部主要操作可见。
- 尺寸和字号以 [DESIGN_SYSTEM](../../../../design/v02-suite-r3/DESIGN_SYSTEM.md) 优先：208px 侧栏、60px 页头、28px 主区边距，页面/区块/正文字级 24/16/14。参考生成图的侧栏约 234px、文字整体较大；实际图更紧凑，不按 raster 比例放大文字。
- 内容输入的上传/粘贴切换采用下划线 tabs，参考为分段按钮；空态采用线性文件图标，参考为灰色实体文件插画。这是仍可辨的视觉差异，不遮挡控件，也不虚构能力。
- 实际表新增“画像版本 · 客户空间资料”和操作列，承载真实版本/编辑/撤销流程；引用范围文案明确人工确认后才能用于联系准备。它们是现有功能约束，不将测试资料冒称客户成绩。
- 1484 图抽屉输入与固定底栏完整；1280 图的 UNKNOWN 警示、原请求查询、资料版本和禁用操作均清晰可见。主线程报告该 1280 场景无横向溢出，截图未见水平裁断；不外推其它分辨率或系统缩放。

## 剩余观察与边界

`remove-reconciled.txt` 同时保留之前的“资料操作结果待确认，请核对原操作。”通知和新“资料已移除。”通知。此时列表已空、持久的待确认区已消失，因此不是锁未解除的证据。后续已核对 `desktop/src/renderer/app/context.tsx:107–114`：每条通知在 6000ms 后按 ID 自动移除，因此这是短暂并存，**不是永久残留或已确诊阻断**。保留为非阻断的体验观察；按原请求替换旧提示可作为后续按需优化，不要求本轮额外修复。

本次没有可见验证多客户空间/不同用户切换、真实后台持久恢复或 Windows；跨空间代码依赖独立代码审查与定向测试。另行发现的 P14/P15 跨空间 P1 不属于本页通过范围，不能用此记录宣布整个前端 Goal 完成。截图校准目录保留历史过程，不把其中诊断图当最终抽屉证据。
