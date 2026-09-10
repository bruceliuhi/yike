# V02 回复与跟进事件契约

状态：`SIGNED_ORIGIN_API_IMPLEMENTED / REAL_PLATFORM_REPLY_SYNC_UNVERIFIED`

## 08 原生公开回复来源（2026-09-12）

只读`POST /api/ui/replies/sync-context`接受`{requestId,deviceId,credentialVersion}`，从当前认证owner的原队列/claim/SENT result核对全部hash与绑定，返回`{schemaVersion:'reply-sync-context-v1',context,claimId,claimedAt,rootCommentId,deviceId,credentialVersion}`。仅XHS POST_COMMENT且根回执ID为24位lowerhex；UNKNOWN/FAILED、另一设备/用户、原件损坏拒绝。该接口不签发发送授权、不依赖最新稿/画像仍有效、不接受调用者指定tenant/root/context。

原生XHS频道新增只读`read_replies(context, root_comment_id, claimed_at)`；context/根ID/领取时间必须来自服务端本人原发送结果，不能由页面临时评论ID或最新草稿替代。实际页面须核对原帖作者、当前账号，以及根评论作者为自己且正文等于原savedContent；只取该根下原买方的直接公开回复。最多3页×10条/15秒，分页未结束返回PARTIAL，错误不返回空成功；读状态固定UNKNOWN，不标远端已读。API客户端惰性复用同隔离浏览器，临时xsec_token只在该请求内存使用，不导出或记录。

当前为原请求定位/reader接续批，**私有worker、main设备签名上报及客户页同步按钮尚未装配**；普通客户端仍只能查看已保存证据。该批不启用后台监控、私信扫描或外部发送。实现/审核证据集中于[本批记录](../superpowers/plans/2026-09-12-xhs-reply-source.md)，真实平台输入及Windows仍需单独验收。

## 08B 普通客户端证据读取（2026-09-12）

`GET /api/ui/opportunities/{id}/replies/evidence` 的数组每项为 `{event, verification, revision}`；revision 是保存行的数据库整数版本，不在 renderer 从时间推导。事件签名字节不变。平台记录以来源、原发送请求、平台、公开回复 ID 为身份，最高 revision 表示当前记录（包括更正/撤销），完整历史保留；人工登记单独标识。

普通客户端使用固定只读 `replies.evidence` 操作，只传 opportunityId；服务端按认证用户/RLS取数，界面另核对用户、客户空间和商机。现有跟进页优先显示证据列表，刷新只读取保存证据，非平台私信同步。空列表不表示平台无回复；错误不转为空；UNKNOWN 已读明确未知。设备证据不是服务器独立平台核验，旧操作员登记和人工跟进不可当设备采集。页面不提供新发送或改已读操作；画像变更不丢弃原画像历史。

会话GET、token交换、SMS登录的认证响应补`account_scope:{id,version:1}`，id来自认证SessionIdentity的租户查询，version沿现有单空间v1快照合同；普通客户端映射为accountScope。不得使用证据中的tenant_id反推可信身份，或把请求输入当客户空间。旧无scope会话可保持原基础登录，但证据读取必须拒绝缺失scope。

实现及限定验证见[本批记录](../superpowers/plans/2026-09-12-reply-evidence-client.md)。未完成真实平台回复同步、实际收发联验或08父卡验收。

## 08 新发送来源接入（2026-09-10）

普通runtime已接`POST /api/ui/replies/signing-payload`（`{request}`）和`POST /api/ui/replies/signed`（`{request,signature}`）。request为`{deviceId,credentialVersion,claimId,contextSha256,event}`，event仍是原PlatformReplyEvent。设备Ed25519签服务返回的UTF-8字节，独立域`yike-platform-reply-v1`绑定当前会话；准备签名不轮询平台。

服务同事务核对原owner、122/123领取、原设备当前有效密钥、冻结来源/商机/画像/平台/渠道/需求作者和context摘要。原队列仅SENT/UNKNOWN可关联，未领取、FAILED、错作者或渠道拒绝；收到/观察时间不得早于领取或来自未来（允许5秒误差）。来源后来关闭、画像撤销或稿件改变不丢失原请求事实。**UNKNOWN下收到回复不会自动变SENT，也不解除防重。**实际适配器还须证明回复属于原会话/平台对象；设备签名不是服务器独立实测平台。

返回`{event,verification}`，verification含DEVICE_ATTESTED_PLATFORM_REPLY、设备/凭据版本、claimId、context及请求/事件摘要、服务验签时间。124只增加现有不可变事件行的nullable device_attestation，不改旧事件payload、摘要或DTO；不保存签名、私钥或平台登录态。

新`GET /api/ui/opportunities/{id}/replies/evidence`返回本人该商机的追加历史，分别标记`DEVICE_ATTESTED_PLATFORM_REPLY`、`OPERATOR_RECORDED`（旧无设备证明平台记录）、`MANUAL_RECORD`。客户端应据此区分来源并按已有revision/state折叠当前状态，不能将历史已读修订重复计作客户回复。旧`/replies`及原列表保留人工/117路径及DTO；新来源平台写入必须走签名入口，旧接口的重放/已读/纠正也不能绕过来源校验。

持续轮询时，只改变观察时间且事实相同的回复返回首次已验证事件；不覆盖原时间/证明，不新增回复。事件ID换新也按公开回复ID去重，但已有其他事件UUID不能借此复用。正文/作者/收到时间等改变仍走冲突/明确修正；已读变化按原规则追加，不修改远端已读。

Win必须采用响应返回的canonical event_id，后续UNREAD→READ修订沿用该ID；不能继续使用被语义去重的临时UUID，否则旧store会按冲突拒绝。独立审核只确认本批后端，不代签客户端ACK。

本片为实际HTTP/PG及设备签名接线，原平台输入仍为合成验证，未实现真实私信读取、提醒或Win消费ACK。[单一实施证据](../superpowers/plans/2026-09-10-signed-reply-origin.md#本批验证)记录范围和未完成项，不能当作已收到真实客户回复。

`pilot/reply_contract.py` 只校验和建模事件，不读取平台、不标记远端已读，也不把人工备注伪装成平台回复。

## 事件边界

- `PlatformReplyEvent` 必须绑定租户、用户、商机、来源、画像版本和原发送请求，并保留平台、渠道、公开回复 ID、发送者公开 ID、原文、收到/观察时间和 `UNREAD / READ / UNKNOWN` 状态。
- `ManualFollowupEvent` 只记录人工事实（联系、会议、报价、输单、赢单或备注），不携带平台字段。平台回复与人工记录必须分开统计。
- 所有 ID、时间、文本和额外字段严格校验；回复观察时间不能早于收到时间，人工发生时间不能晚于观察时间。
- 生产持久层必须先核对同一所有者的确认发送快照，再接受平台回复，不能只凭客户端提交的商机或请求 ID 建立关联。

## 已读与纠正

只有明确 `UNREAD` 的平台事实才能生成新的 `READ` 事实；`UNKNOWN`、人工事件或已读事件均不能被标记为已读。纠正/撤销采用追加式事件，必须与原事件完全同域，不能覆盖历史事实或跨商机引用。

## 去重

同一租户、来源、原发送请求、平台和公开回复 ID 只接受一次；重复事件必须保持商机、来源、发送请求、发送者、正文和收到时间一致，否则拒绝冲突。纠正/撤销事件按自身事件 ID 追加历史，不与原平台回复竞争 active 身份。当前 `ReplyEventRegistry` 是进程内模型，生产实现必须在 PostgreSQL 中建立相同唯一范围、revision、原始请求关联和 RLS，并在服务端重新核验权限。

本契约不证明任何平台回复已成功回流、已读同步、提醒调度或客户商业结果。
