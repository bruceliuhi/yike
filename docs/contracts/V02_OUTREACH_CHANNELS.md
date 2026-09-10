# V02 触达对象与确认协议

状态：`CONTRACT_ONLY / NOT_PRODUCTION_SEND`

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
