# R4 P02 机会简报服务契约

2026-09-11 接续：普通客户端已接认证的已有事实简报，版本与限定验证见[本批记录](superpowers/plans/2026-09-11-opportunity-brief-service.md#实施与验证)。`profileId` 沿用 `Profile.id`，即 `profile_version_id`；只读取所选时区的当前业务日，历史日期请求明确拒绝。已核验机会及结构化到期跟进已接；后续新增[本人同来源留存正文变化](superpowers/plans/2026-09-11-source-content-changes.md#实施与验证)，仍不把空变化组解释为全网无变化。未代表生产或客户验收。

2026-09-09。范围为已获实现授权的 R4 工作台机会简报前端，依据 [R4 交互合同](../design/v02-suite-r4/INTERACTION_CONTRACT.md)。本次实现只读快照与既有详情/跟进导航，不新增自动联系、执行研究或虚构业务业绩。

## 可选服务与快照身份

`YikeService.opportunityBrief?: OpportunityBriefService` 提供 `query(request, signal?)`。完整类型见 [服务接口](../desktop/src/renderer/services/opportunityBrief.ts)，验证规则见 [数据合同](../desktop/src/renderer/domain/opportunityBrief.ts)。缺真实适配时显示尚未接通；原工作台待办、准备步骤和公开样例保留，不从任务、事件或连接数量拼凑简报。

请求包含 `contractVersion=1/requestId`、可信会话的 `userId/accountScopeId/scopeVersion`、已确认 `profileId/profileVersion`、`businessDate` 和 IANA `timezone`。缺可信账户范围不得调用新服务。服务端从认证会话派生授权；请求内的身份仅用于核对，不能代替认证或选择任意账户。

响应必须精确回显以上全部字段，另含 `snapshotId`、`audience=CUSTOMER`、生成/到期时间、完整度、最近完成检查时间、已查/未查范围和原 `taskId/runId/windowId` 列表。它是指定账户、画像版本和业务日的已有快照，读取不得隐含生成、收费、标记已联系或触发新采集。

## 三组内容

| 分组 | 依据 | 既有目标页面 |
|---|---|---|
| 今日值得联系 `contact` | `REVIEWED_DEMAND`，已核验需求及人工判断；不承诺联系后成交。 | 当前商机详情 |
| 重要变化 `changes` | `VERIFIED_CHANGE`，留存原文对比，不代表采购事实已复核。 | 当前商机详情的变化标签 |
| 待跟进 `followup` | `MANUAL_FOLLOWUP / CHANNEL_FOLLOWUP`，人工登记与渠道记录分别保留。 | 该商机的跟进记录 |

每项包含稳定简报条目 ID、商机 ID/版本、标题、入选理由、画像 ID/版本、`sample=false`、对象有效性，以及依据记录 ID/版本/类型/摘录/核验时间。依据必须符合所在分组，同组不能重复商机或条目，所有条目必须属于请求画像。禁止保留 ID 为 `sample` 或 `sample:*` 的客户条目。

每组 `total` 为该快照完整数组长度（最多 1,000），前端每页展示 6 条，不允许服务默默截断后报总数。同一商机可以进入不同分组，因此三组不能求和当成新增客户或成交数量。

变化组复用时间线 V2 同源投影，每机会最多保留一条在本业务日收到证据的最新变化；日界使用 detectedAt，不改写原帖发布时间。basis.recordId 绑定变化端点，basis.version 为后次 observation ID，摘录来自变化后正文；理由说明观察时间、编辑时间未知及需求待复核。未覆盖范围继续披露，coverage 不因此升为 COMPLETE。

`coverage=COMPLETE` 需要最近完成时间、已查范围且无未查范围；`PARTIAL` 必须说明未查范围；`NOT_CHECKED` 不能同时携带已核验条目、运行或已查范围。最近完成检查和依据核验不能晚于生成时间，生成时间不能在未来且必须早于到期时间。格式、身份、计数或依据错误显示读取错误，不能解释为今日无机会。

## 页面与时间生命周期

页面在已确认画像中选择版本，默认取返回集合中版本号最新者；多个已确认画像可切换。画像变更会请求新快照，旧结果不会暂留为新画像结果。没有已确认画像时提供原画像入口。

当前业务日按页面明确显示的本机 IANA 时区计算。到当地下一日边界自动刷新，计算包含夏令时变化，不能固定等待 24 小时代替日历切换。时区和业务日随请求绑定，不能将另一日期的数据展示成今天。

每次读取限时 30 秒；刷新、离页、身份、账户或画像变更后，迟到响应不能覆盖当前页面。失败提供重试，等待不等于空结果。快照到期后仍可标识为历史查看，进入对象的操作禁用，须先刷新。对象 `EXPIRED / TARGET_MISSING` 同样不能进入其他记录。

导航只使用返回的确切既有商机 ID：详情为 `/opportunities/:id`，变化为 `/opportunities/:id?tab=changes`；跟进为 `/followups?tab=todo&opportunity=:id`。后者明确表示“查看该商机跟进”，不伪造针对单条待办的精确路由。实际目标页仍需重新校验当前权限和对象状态。

账户准备区域来自真实连接状态，不把已连接解释为已搜索或已完成检查。原待办与准备入口收在“全部待办与准备步骤”中，公开研究样例保留独立标识，不能作为客户简报条目入库或发送。

## 验证与待接能力

域/组件回归覆盖身份及业务日绑定、分组依据、同商机跨组不求和、来源未知、错误/超时、过期/午夜刷新、确认画像切换、对象失效和既有导航。测试依据位于 `desktop/tests/ui/r4-opportunity-brief-*`；最终数量和候选 SHA 以当轮 QA 报告为准。

[隔离视觉适配](../desktop/tests/visual/r4-opportunity-brief.ts) 只接受 `TEST` 会话范围，返回既有隔离样例对象的内存快照；动态有效期用于真实页面交互验收。它不访问外部平台、不写客户库、不生成发送或启动回执。正式源码接入与本地合成联验见上述本批记录；真实平台变化、生产与客户验收仍未完成，本合同不等于这些能力已经上线。
