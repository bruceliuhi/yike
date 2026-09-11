# P12 短句教练与草稿保存交接合同

适用 R4 前端。普通客户端 `contactDrafts` 已接真实认证HTTP保存/查询，见[客户端接入记录](superpowers/plans/2026-09-11-contact-draft-client.md)。`shortCoach` 已接配置模型适配器、预览确认及结构化建议，限定验证见[接入记录](superpowers/plans/2026-09-11-short-coach-service.md#实施与验证)；未配置模型仍明确不可用，不代表已调用真实模型、平台发送或生产上线。既有 `generateContact(): Promise<string>` 路径保留，但其结果不会被包装成已核验证据。

## 实现入口

- 域与唯一运行时 schema：[shortCoach.ts](../desktop/src/renderer/domain/shortCoach.ts)。
- 可选接口：[ShortCoachService / ContactDraftService](../desktop/src/renderer/services/shortCoach.ts)，挂在 `YikeService.shortCoach?` / `contactDrafts?`。
- 页面：[ContactEditor](../desktop/src/renderer/pages/outreach/ContactEditor.tsx)、[ShortCoachPanel](../desktop/src/renderer/pages/outreach/ShortCoachPanel.tsx)。
- 请求生命周期：[useShortCoach](../desktop/src/renderer/pages/outreach/useShortCoach.ts)、[useContactDraftSave](../desktop/src/renderer/pages/outreach/useContactDraftSave.ts)。

## 生成与应用

普通服务先 `preview(input)` 返回原输入摘要及实际模型标识，界面展示完整公开原文、当前人工草稿与模型名称；明确确认后以同一请求加 `disclosure` 调用生成。服务端核对已保存原文、画像及来源当前状态，只把原文/草稿/channel/purpose交给模型，不带账号、收件对象或资料库。取消停止客户端等待，不自动重试；同原请求最多调用一次，重放只返回旧结果或明确状态。安全上限为每租户UTC自然日50次新调用，失败计入，不是价格或搜贝。建议有效期5分钟，承诺仍需人工复核。

`generate({binding, content, sourceText}, signal?)` 返回结构化 `CoachSuggestion`。`binding` 必须原样对应当前客户空间 ID/版本、请求 ID、商机、已确认画像版本、来源证据版本/URL/观察时间、评论或私信用途、草稿版本与 SHA-256、教练目的。

目的为 `requirement`（具体需求）、`materials`（资料获取）、`scope`（服务范围）。当前只提交该商机公开摘录；内部材料不会发送给教练。扩展资料引用前须另行定义和核验材料授权、版本与可见范围。

响应包括完整候选文字、一个问题、上下文摘要、原文引用、检查提示与有效期。原文引用采用 JavaScript **UTF-16** 的 `[start,end)` 索引，必须逐字等于本次 `sourceText` 切片，并绑定同一 URL/证据版本。引用 ID 必须存在且唯一；`CONTEXT` / `PROMISE` 标为 `SUPPORTED` 时须有引用锚点。`SUPPORTED` 表示有对应引用，不能据此声称服务能力、承诺或业务事实已被算法证明。缺少计量字段不会显示为零消耗。

生成与应用核对均有 30 秒等待上限。取消只停止客户端等待，不宣称撤销服务端工作。离页、客户空间、来源、画像或用途变化会丢弃旧代响应。人工编辑始终保留；候选只进入全文比较弹窗。用户明确选择替换后，还会重新读取商机并核对证据版本、有效期和核对期间的人工修改。失败、过期或失配不会覆盖当前文字。

成功应用后，[已采用建议摘要](../desktop/src/renderer/pages/outreach/AdoptedCoachSummary.tsx) 仅在本次采用的草稿版本、全文、目的、空间、来源及建议有效期仍匹配时保留；保存不会冒充再次审核。人工变更或切换后摘要撤销，恢复旧文字也不会自动恢复旧检查。收件对象和发送账号移至默认折叠的“发送配置”，保留原字段、值及发送核验。

公开样例仅只读预览、复制，不生成客户建议、保存到客户库或进入真实发送。评论和私信草稿独立保存；更改文字或保存状态会使旧发送确认失效，外发仍遵守 [触达合同](UI_OUTREACH_CONTRACT.md)。

## 保存与 UNKNOWN 恢复

`contactDrafts.save({binding,snapshot})` 与 `operation(binding)` 共用原请求。保存绑定为 `{opportunityId, channel, requestId, contentHash}`；快照包含完整草稿、客户空间、画像版本和来源证据版本。摘要覆盖内容、草稿版本、账号/对象及这些版本范围，不能只对正文计算。服务器必须按已认证空间授权、复核所有版本/摘要，并原子保存原请求及草稿；客户端字段不是授权依据。

| 回执 | 前端行为 |
| --- | --- |
| `SUCCEEDED` + `confirmed:true` + 精确快照 | 摘要一致且 `savedContent === content` 才核销原锁；只在当前客户空间 ID/版本也一致时应用快照和提示成功。保存期间的新人工文字仍保留。 |
| `FAILED` + `confirmed:true` | 表示服务已确认未保存；核销原锁，保留人工文字供复核重试。 |
| `PENDING` / `UNKNOWN`、超时、网络错误、无效/失配回执 | 保留原请求并禁止重复保存、准备发送；只能核对原保存请求。 |

派发前同步写入 `contact-draft-saves` 操作账本，键为 `[opportunityId, channel, requestId, contentHash]`、值为 `PENDING`，按用户隔离。写入失败不派发；关闭页面、清草稿和登出不会清掉未决操作。账本不保存正文、对象、凭据或授权 token。

兼容旧 `saveContact` 时仍有等待上限，旧请求用 `legacy:` 前缀。旧接口无法查询原请求，未知结果会继续锁定并明确提示核对后台；不能伪造可恢复查询。仅明确的 `DRAFT_SAVE_REJECTED` 非 408 的 4xx，或 `CAPABILITY_UNAVAILABLE` / `UNAVAILABLE` 的 501 被当作确定未派发；普通 HTTP 错误不证明未保存。

## 验证与后端接入边界

### 07C 普通客户端接续（2026-09-11）

普通 service 现提供 save/operation/latest，桌面IPC仅允许三个固定路由；请求与回执验证摘要、商机、用途及当前客户空间。latest 仅将明确 `404/draft_not_found` 当作“本人未保存”，其他错误不得解释为空。

编辑器恢复本人已保存正文、版本、账号和对象，评论/私信独立。初始未编辑稿可自动恢复；已有本机修改或来源变化须明确采用。前驱随本机编辑状态保存，不在提交时读取最新值代签；原成功回执仅推进对应用途。恢复高版本时保留新人工修改，下一保存版本须严格更高。保存不生成发送许可，历史稿也不证明来源仍开放。

既有UNKNOWN保护保留：普通HTTP冲突/404不证明原请求未写入。原操作长期查无结果时仍需后台核查；本批未新增终态失败回执账本，不宣称所有失败都可自动恢复。短句模型、真实平台/Windows/生产与客户试用另行验收。

### 07B 后端接入（2026-09-10）

普通 Web runtime 已提供：`POST /api/ui/contact-drafts`（`DraftSaveInput`加顶层 `previousRequestId`）、`POST /api/ui/contact-drafts/operation`（原 `DraftSaveBinding`）、`GET /api/ui/opportunities/{id}/contact-drafts/{comment|dm}`（本人最新成功保存回执）。三者沿用正式会话、HTTPS及Origin边界。迁移121和显式草稿授权须先部署；客户端07C尚未接入，不据此打开outreach或短句模型能力。

`previousRequestId` 首次保存为null/省略；已有人工稿时必须等于**开始编辑时**采用的保存回执 `binding.requestId`。客户端收到自己的成功保存或明确读取/采用最新稿后才更新这个前驱；不得在提交时静默读取新前驱替旧窗口补签。服务端按owner锁校验前驱，即使正文A→B→A或只变账号/对象也拒绝旧窗口。该字段是保存CAS条件，不进入既有内容摘要，不改变原查询绑定或回执形状；Win的adapter与编辑状态需同时接入，不能只打开save方法。

服务只返回确切的 `SUCCEEDED/confirmed:true` 或安全错误，不把404/超时当作FAILED。原请求重放/查询返回原版本，即使来源后来失效；最新草稿也只是保存事实，不是实时可发送证明。客户端恢复后须采用已存版本和savedContent，再以更高版本提交人工编辑；不能每次从版本1覆盖。comment和dm分别保存，租户内不同用户的人工稿互不可见。

`accountScope:null` 为现有无scope会话的兼容值，仍由服务器会话确定租户/owner；非空必须精确等于 `{id: authenticatedTenantId, version:1}`，不是客户端自报授权。来源/画像ID须有效且匹配服务器固定证据；不接受公开sample。账号和收件文字仅是人工草稿内容，保存不核发发送许可，不代替后续连接版本与收件人实际核验。

Win接入时保留原pending账本；普通HTTP错误不转成 `DRAFT_SAVE_REJECTED`，请求冲突尤其不能推断原操作未保存。原始研究建议仍保留在商机详情，不能用它替代本人的最新人工稿。[本批计划与证据](superpowers/plans/2026-09-10-contact-draft-persistence.md)供接续，不记客户端ACK。

域约束：[r4-short-coach-domain.test.ts](../desktop/tests/ui/r4-short-coach-domain.test.ts)；编辑/迟到/跨空间/保存恢复：[r4-short-coach.test.tsx](../desktop/tests/ui/r4-short-coach.test.tsx)；保留原触达流程的回归：[outreach.test.tsx](../desktop/tests/ui/outreach.test.tsx)、[send-confirmation.test.tsx](../desktop/tests/ui/send-confirmation.test.tsx)。

[TEST adapter](../desktop/tests/visual/r4-short-coach.ts) 与 [adapter 回归](../desktop/tests/ui/r4-short-coach-visual.test.ts) 仅用于隔离内存演练，读取 TEST 身份和 TEST 原文构造精确引用，未调用模型、真实客户空间或外部平台。后端接入须另行提供真实授权、幂等持久化和接口验收；本轮没有新增任意路径 IPC 或假生产 adapter。
