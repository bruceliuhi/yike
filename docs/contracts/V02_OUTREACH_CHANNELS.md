# V02 触达对象与确认协议

状态：`CONTEXT_QUEUE_AND_DISPATCH_LEDGER_IMPLEMENTED / REAL_PLATFORM_SEND_UNVERIFIED`

## 07B 本机许可消费组件（2026-09-10）

`74b4d52`新增私有主进程组件`outreachConsumer.ts`和`outreachConsumptionJournal.ts`；验证与审核记录集中于[本批计划](../superpowers/plans/2026-09-10-native-outreach-consumption.md#本批验证)。尚未注册main/IPC或安装真实发送器，不代表Win已消费。

固定主进程适配器负责构造`OutreachExpected`（serviceOrigin/userId/tenantId/deviceId/sessionId/requestId/claimId/contextSha256），仅传入认证私有transport的首次123 grant，不能接受renderer自报身份或注入driver。控制器重算完整context摘要、核对账号/收件人/来源/动作及有效期；`NativeOutreachChannel.check`必须只读核验实际原账号与目标，返回绑定context摘要、device/connection/version/account/recipient和5秒内checkedAt。`execute`仍须在固定隔离profile的动作点检查取消及账号。

日志目录由主进程固定在可信应用数据根内（不接受renderer路径、祖先目录须可信），保护器使用OS保护存储。消费以serviceOrigin/userId/tenantId/requestId为唯一键，加密记录claim/device/context摘要，排他创建并同步文件；POSIX同步目录和父目录，Windows文件同步仍需实机验收。正文/登录态不入日志。损坏、保护失败或部分写入均停止，永不自动删除消费记录。跨会话/重建控制器不能重发；用户删日志与通用断电保证不在此证明内。

`RESULT_READY`仅为待签名提交的设备结果，始终`serverAccepted:false`；异常或不明确结果保留UNKNOWN，不猜测未投递。有效的晚到回执仍保留原request/claim；需由后续私有transport提交123 RESULT并按原请求恢复，当前没有自动重试或外部发送入口。

## 07B 单次领取与结果（2026-09-10）

123增量新增普通runtime接口`POST /api/ui/outreach/dispatch/signing-payload`（`{request}`）及`POST /api/ui/outreach/dispatch`（`{request,signature}`）。沿用设备Ed25519，独立域`yike-outreach-dispatch-v1`绑定当前会话；直接签服务返回的规范UTF-8字节。

request公共字段：`action`（CLAIM/RESULT）、`requestId`（原确认）、`claimId`、`deviceId`、`credentialVersion`、`contextSha256`；RESULT另需`resultId`及`outcome`，CLAIM不带结果。未知字段/宽松布尔不接受。

CLAIM同事务重验完整context、原设备/密钥及原稿/来源/画像/连接，确认和渠道报告最多120秒。默认平台允许集合为空；配置只开服务许可，不证明真实平台已验收。首次领取才返回`dispatchAllowed:true`、冻结context、claimId、dispatchBefore（最多30秒且不超过原120秒期限），状态立即为UNKNOWN。重放CLAIM、结果响应及GET原queue始终false，重放不附可执行context。

**本机worker必须在平台动作前原子持久消费(requestId,claimId)**；重复响应/IPC/崩溃恢复不得再动作，动作前实际核验原账号/对象/内容/渠道，过期许可不能用。此本机能力尚未接入，不能仅凭服务端一次grant宣称端到端最多发送一次，Win不得直接开启发送按钮。领取后取消/换claimId均拒绝，超时不得回QUEUED；QUEUED/UNKNOWN/SENT防新UUID，FAILED或CANCELLED后仍需新人工确认。已SENT后的明确跟进应另接后续动作，不能自动新建首联请求规避。

RESULT只核对原领取/设备/context，不重验后来变更的草稿/来源/连接。可用该设备当前有效密钥和当前会话报告原结果；设备撤销仍拒写，原请求可读。严格outcome：

| status | 必填 | 不允许 |
|---|---|---|
| UNKNOWN | status | confirmed、confirmedNotDelivered、proof非null |
| SENT | confirmed:true；proof.kind=ACCEPTED | confirmedNotDelivered非null |
| FAILED | confirmed:true、confirmedNotDelivered:true；proof.kind=REJECTED_NOT_DELIVERED | 把超时、空查询、点击无响应当未投递 |

proof含externalId（不透明平台结果ID）、sha256（核验回执摘要）、observedAt（带时区，不早于领取、不晚于现在，允许5秒误差）。不回传Cookie、私钥、敏感URL或原始平台响应。SENT/FAILED回执注明`evidenceAuthority:DEVICE_ATTESTED_PLATFORM_RECEIPT`，是签名设备的明确平台回执声明，**不是服务器独立实测**；实际适配器仍需验收。

同resultId同内容返回原历史，异内容409；UNKNOWN可到SENT/FAILED，终态不反转。历史UNKNOWN重放不等于当前态，当前态查原queue；GET带claimId/dispatchBefore，永远不重新授权。仅SENT的deliveryConfirmed为true，FAILED另有confirmedNotDelivered:true。

旧renderer `send(draft,confirmationToken)`尚未接此协议，不能把dispatchAllowed映成SENT。原队列回复关联现已通过[124签名回复增量](V02_REPLY_FOLLOWUP.md#08-新发送来源接入2026-09-10)显式接入，不伪造117整数来源版本；本机消费/真实渠道仍未验。[123本批记录](../superpowers/plans/2026-09-10-outreach-dispatch-ledger.md#本批验证)保留历史证据。以下122段描述其首次交付，当前状态和接口增量以上文为准。

## 07B 人工确认队列（2026-09-10）

普通runtime新增以下认证接口；部署先执行迁移122及`deploy/grant_outreach_queue.sql`，不改旧117整数版本契约。

| 入口 | 用途 |
|---|---|
| `POST /api/ui/outreach/signing-payload` | 输入`{request}`，取得当前会话绑定的`signing_payload`和requestSha256；准备字节不授权发送 |
| `POST /api/ui/outreach/queue` | 输入`{request,signature}`，验证已登记设备Ed25519签名并重新核验完整context后入队 |
| `GET /api/ui/outreach/queue/{request_id}` | 本人原请求恢复；不创建操作，404不能推定未送达 |
| `POST /api/ui/outreach/queue/{request_id}/cancel` | 仅取消尚未派发的QUEUED；重复取消返回原CANCELLED |

`request`字段：`requestId`（新确认UUID）、`context`（上一节原请求）、`contextSha256`（上一节响应摘要）、`credentialVersion`、严格布尔`humanConfirmed:true`、`channelCheck:{status:"AVAILABLE",observedAt:"带时区ISO时间"}`。签名必须由**该设备**私钥对服务返回的UTF-8原文字节生成，采用现有无padding的base64url；协议域`yike-outreach-confirmation-v1`绑定tenant、owner和当前session。切换会话需重新取字节签名，不能复用旧签名；私钥和签名均不入数据库。

只有客户端已完成原账号/目标/渠道核验后才可以报告AVAILABLE；签名只证明设备声明，不证明服务器实测平台。入队要求报告最多120秒前（允许5秒时钟超前）、最新保存稿/来源/画像/连接版本及整个context不变。CONNECTED不能自行转换为AVAILABLE。**当前客户端尚未消费本接口，不能在UI伪造核验报告来开启按钮。**

响应为`{requestId,state:"QUEUED"|"CANCELLED",deliveryConfirmed:false}`。同owner/商机/channel只允许一条未决；换UUID或账号不能绕过。原UUID同绑定返回当前原状态，即使后来来源失效也可恢复；变更绑定409。设备撤销/换钥后通过只读GET恢复，不能复用旧签名重新确认。取消后如确需重新联系，必须走新上下文、新核验、新人工确认和新UUID，旧请求永不重启。

本批仅持久化人工确认及当时完整context，不发消息、不创建SENT、不启用全局outreach能力。队列等待并不延长渠道核验/确认的有效期；后续领取必须再次验证有效期与最新事实。06B原生检查/单次派发、07B领取/UNKNOWN对账、08与实际发送原请求关联仍未完成，旧117回复origin不能直接冒认122队列为已发送。实现与定向证据集中见[本批计划](../superpowers/plans/2026-09-10-outreach-confirmation-queue.md)。

## 已接普通服务的联系上下文（2026-09-10）

`POST /api/ui/outreach/context` 已在普通runtime接入。输入为 `{binding: DraftSaveBinding, deviceId, connectionId, connectionVersion}`；binding必须来自本人**最新**已保存草稿。数据库当前来源/画像状态、固定证据版本、设备归属和连接版本重新核验；历史保存回执仍可查，但不能拿旧稿形成新联系上下文。

草稿`accountId`沿用客户端的 **account_public_id**；请求`connectionId`则来自连接注册记录的UUID。两者不可互换：服务端锁定指定设备/连接/版本后，比对其公开账号ID与原保存稿，再核对来源平台；不改现有草稿摘要或把同昵称当同一账号。

响应 `outreach-context-v1` 包含原binding、owner/空间、画像、全文草稿、来源ID/URL/固定证据版本与摘要、target、连接公开身份，以及整个响应（不含contextSha256自身）的UTF-8规范JSON SHA-256。规范JSON递归排序键、不加空格、不转义中文；该摘要**不是授权token**。

- `COMMENT_REPLY`：postId为原帖子、commentId为原需求评论、authorPublicId为该评论作者；不采用父评论或博主身份。
- `POST_COMMENT`：指向原帖子，commentId为null；`DIRECT_MESSAGE`指向原需求作者，同时保留原帖子/评论以供追溯。
- 无可靠公开ID或PAGE未定义渠道则拒绝；没有从昵称推断账号，也没有改写调用者的草稿对象/账号。
- 固定证据沿用UUID版本 `source.evidenceVersion`，不将其伪造为旧契约的整数source_version。完整context摘要交给后续渠道核验/确认绑定，不直接塞进旧进程内模型。

响应始终明确 `authorization: NOT_GRANTED`、`channelCapability.status: UNVERIFIED`。CONNECTED仅表示数据库中由客户登记的连接状态，既不是本次平台重开，也不是评论/私信权限。没有确认token、发送回执或队列写入；下一步仍须原账号/原目标的实际渠道检查、人工确认和持久发送队列。Win07C可据此接联系准备，不能把200当作verifyContact.allowed。原`SourceObject`等纯契约仍保留为历史对照，不代表已开通发送。

本批代码、测试边界及独立审核见[联系上下文计划](../superpowers/plans/2026-09-10-outreach-context.md)。没有新增迁移/授权：复用草稿121、候选/证据及连接已有最小授权；不输出vault/session_ref。

本文件冻结 V02-06A/07A 的后端对象边界，供真实平台适配器、发送队列和 Windows 客户端后续联调。它不代表任何平台已经接通，也不授权自动发送或绕过验证码、限流和风控。

## 对象与绑定

- `SourceObject`：公开来源对象，必须保留 `source_id`、`opportunity_id`、平台、可重开的公开 URL、作者公开 ID 和来源版本。公开 URL 不得包含 token、cookie、session、password 或 secret 参数。
- `ChannelCapability`：某个已授权连接在某时刻对 `comment` 或 `dm` 的能力状态。只有 `AVAILABLE` 且带 `connection_id` 与 `connection_version` 时，才允许建立收件人映射。
- `RecipientMapping`：服务端从来源和已验证能力解析出的收件人。平台公开 ID 是不透明字符串，不得假设为 UUID；映射必须与来源、商机、渠道、连接和连接版本完全一致。
- `DraftBinding`：待人工确认的草稿，绑定来源 ID/版本、商机、渠道、收件人、连接版本、内容版本。内容只以 SHA-256 摘要进入确认快照。

连接器已有的 `VERIFIED` 等内部状态不得直接当作本协议状态传入；适配层必须依据当次真实能力检查转换为 `AVAILABLE` 或 `UNVERIFIED`，并保留原因和检查时间。

## 确认与幂等

`bind_confirmation` 只接受完全匹配的来源 ID/版本、来源作者、收件人、渠道、连接版本和草稿内容，生成有过期时间的不可变快照。确认时间之前以及过期之后均无效；连接版本、收件人、渠道、内容或版本任一变化，旧快照必须失效。后续持久层必须对 `request_id` 建立唯一约束：同一请求相同绑定可重放，绑定冲突必须拒绝，不能盲目重发。

当前 `IdempotencyRegistry` 仅是进程内契约模型，用于测试和联调，不是生产存储；生产实现必须在 PostgreSQL 事务中持久化完整快照、原始请求 ID 和状态。

## 发送结果

`SendReceipt` 采用失败关闭语义：

- `SENT` 必须明确 `confirmed=true`；
- `FAILED` 必须明确 `confirmed=true` 且 `confirmed_not_delivered=true`；
- `UNKNOWN` / `PENDING` 不得声称已确认或未送达，必须保留原请求 ID，等待原请求对账；
- 未取得平台回执时不得把页面变化、超时或本地点击当作成功。

模块只做严格校验，不执行外部网络操作，不保存账号凭据、Cookie、验证码或私信正文以外的敏感信息。
