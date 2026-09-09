# P12 短句教练与草稿保存交接合同

适用本轮 R4 前端。已实现交互、运行时校验和隔离测试；生产 `shortCoach`、`contactDrafts` adapter 尚未接通，本文件不代表模型、平台发送或后台草稿服务已上线。缺少结构化服务时明确提示未接通，既有 `generateContact(): Promise<string>` 生成路径保留，但其结果不会被包装成已核验证据。

## 实现入口

- 域与唯一运行时 schema：[shortCoach.ts](../desktop/src/renderer/domain/shortCoach.ts)。
- 可选接口：[ShortCoachService / ContactDraftService](../desktop/src/renderer/services/shortCoach.ts)，挂在 `YikeService.shortCoach?` / `contactDrafts?`。
- 页面：[ContactEditor](../desktop/src/renderer/pages/outreach/ContactEditor.tsx)、[ShortCoachPanel](../desktop/src/renderer/pages/outreach/ShortCoachPanel.tsx)。
- 请求生命周期：[useShortCoach](../desktop/src/renderer/pages/outreach/useShortCoach.ts)、[useContactDraftSave](../desktop/src/renderer/pages/outreach/useContactDraftSave.ts)。

## 生成与应用

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

域约束：[r4-short-coach-domain.test.ts](../desktop/tests/ui/r4-short-coach-domain.test.ts)；编辑/迟到/跨空间/保存恢复：[r4-short-coach.test.tsx](../desktop/tests/ui/r4-short-coach.test.tsx)；保留原触达流程的回归：[outreach.test.tsx](../desktop/tests/ui/outreach.test.tsx)、[send-confirmation.test.tsx](../desktop/tests/ui/send-confirmation.test.tsx)。

[TEST adapter](../desktop/tests/visual/r4-short-coach.ts) 与 [adapter 回归](../desktop/tests/ui/r4-short-coach-visual.test.ts) 仅用于隔离内存演练，读取 TEST 身份和 TEST 原文构造精确引用，未调用模型、真实客户空间或外部平台。后端接入须另行提供真实授权、幂等持久化和接口验收；本轮没有新增任意路径 IPC 或假生产 adapter。
