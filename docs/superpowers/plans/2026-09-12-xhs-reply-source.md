# 原请求定位与小红书公开回复读取

> 按已批准08回复契约执行，使用subagent-driven-development/定向验证；一次整批审核，修复仅差量。本批base `00dd4d1`，不改变完整V0.2范围。

**Goal:** 为现有原生运行时补上可验证的原评论定位和只读回复能力，不把任意账号留言归为客户回复。
**Architecture:** 服务端从本人原队列/领取/已保存SENT结果提取冻结上下文与根评论ID；现有XHS频道核验同账号、同原帖与原发送内容后，只读取该根评论下原买方的直接回复。无新数据库表，不扫描私信。
**Tech Stack:** PostgreSQL/FastAPI、现有受限MediaCrawler客户端及Playwright。

## Global Constraints

- 仅XIAOHONGSHU POST_COMMENT的原SENT回执；UNKNOWN/FAILED/未领取、错本人设备拒绝原评论定位，绝不重发或改发送状态。用户/租户来自认证，不接受覆盖。
- context源于保存原快照，不依赖最新稿/画像仍有效。调用时仍核验会话与设备密钥有效。原上下文与回执hash/绑定损坏拒绝，不把服务器JSON当自动可信。
- 阅读仅同一原帖、自己发送的精确根评论、原需求作者直接回复；实际页面账号与原发送账号必须一致。其他作者/其他目标回复不输出。
- API每页10条、最多3页、总等待15秒；超过为PARTIAL，原cursor保留内存不落日志；重复cursor/冲突/错误不得返回空成功。验证、限流或格式变化立即停止，不自动重试/绕过。正文、时间、公开ID直接取原平台数据，已读UNKNOWN，不猜精确时间。
- 不读取或保存Cookie/登录态/私信；页面临时xsec_token只在同账号客户端请求内使用，不进入结果/错误/日志。测试平台数据全部标合成，未验真实平台或Windows。

### Task 1: 后端原发送定位（独立实现）

文件：pilot/signed_replies.py、pilot/reply_api.py、tests/test_signed_reply_http_postgres.py，报告同目录xhs-reply-origin-report.md。

- [ ] RED：已SENT的XHS POST源`POST /api/ui/replies/sync-context`，body=`{requestId,deviceId,credentialVersion}`，当前无路由404。
- [ ] 增加严格ReplySyncContextRequest(Id/Version)；SignedReplyStore.sync_context(claims,raw)，只读锁/认证设备，查询本人原queue/claim和匹配SENT result。不存在/错设备/非XHS POST/UNKNOWN等409。解析DispatchRequest并核hash，context去contextSha256后canonical hash校验、owner/tenant/binding/profile/source/原device等与原确认载荷对齐，根proof.externalId须24位lowerhex。原队列confirmation/claim/result各自request hash及关联一致。不接受从body传context、rootId或tenant。
- [ ] READY响应严格字段：`{schemaVersion:'reply-sync-context-v1',context,claimId,claimedAt,rootCommentId,deviceId,credentialVersion}`。context是原outreach-context-v1；没有授权发送字段/私密URL/token。
- [ ] 实际独立PG定向：本人有效原件；同租户另一用户/他租户/另一device；UNKNOWN/FAILED；原画像撤销/来源关闭仍可定位；输入extra拒绝。仅运行受影响case。不新建迁移，不改desktop/app。
- [ ] 提交独立文件并报告RED/GREEN、SHA、未验边界。

### Task 2: 既有原生XHS频道只读子评论（root）

文件：app/xhs_comment_channel.py、app/platform_outreach_runtime.py、tests/test_xhs_reply_reader.py、受影响原runtime测试。

- [ ] RED测试`await channel.read_replies(context,root_comment_id,claimed_at)`不存在。
- [ ] 构造器可选read_sub_comments回调；read_replies先_snapshot、_identity、_receipt_matches验证，固定note/root、可重开页面中唯一非空xsec_token，调用受限客户端get_note_sub_comments。校验分页comments/list/has_more/bool/cursor、原作者user_info.user_id、target_comment.id==root、id24hex、content长度/非空、create_time毫秒整数不早于claim(5秒容差)且不晚于观察(5秒容差)。返回`{status:'COMPLETE'|'PARTIAL',items:[{externalReplyId,senderPublicId,body,receivedAt,observedAt,readState:'UNKNOWN'}]}`；分页结束前保留去重集合，冲突拒绝。
- [ ] runtime内惰性创建同browser的xhs_client，注入回调，仅read_replies调用时请求；发送/check路径不增加远程调用。保留现有close/取消处理；每次await之后核对取消与实际页面身份，所有失败统一REPLY_SOURCE_UNAVAILABLE，不泄漏原异常。
- [ ] 定向覆盖原买方直接回复/其他作者过滤、错根/账号禁止请求、取消与分页失败、日期/重复冲突、页数上限；复用原发送/生命周期测试。不得执行真实平台动作。
- [ ] 整批独立审核、合同/任务书更新后推main。本批为原生reader与原请求定位，下一主链将它接入私有worker/main签名上报及已有回复页手动同步；未装配前不展示同步可用，不将08父卡标完成。
