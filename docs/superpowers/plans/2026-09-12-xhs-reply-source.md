# 原请求定位与小红书公开回复读取

> 按已批准08回复契约执行，使用subagent-driven-development/定向验证；一次整批审核，修复仅差量。本批base `00dd4d1`，不改变完整V0.2范围。

**Goal:** 为现有原生运行时补上可验证的原评论定位和只读回复能力，不把任意账号留言归为客户回复。
**Architecture:** 服务端从本人原队列/领取/已保存SENT结果提取冻结上下文与根评论ID；现有XHS频道核验同账号、同原帖与原发送内容后，只读取该根评论下原买方的直接回复。无新数据库表，不扫描私信。
**Tech Stack:** PostgreSQL/FastAPI、现有受限MediaCrawler客户端及Playwright。

## Global Constraints

- 仅XIAOHONGSHU POST_COMMENT的原SENT回执；UNKNOWN/FAILED/未领取、错本人设备拒绝原评论定位，绝不重发或改发送状态。用户/租户来自认证，不接受覆盖。
- context源于保存原快照，不依赖最新稿/画像仍有效。调用时仍核验会话与设备密钥有效。原上下文与回执hash/绑定损坏拒绝，不把服务器JSON当自动可信。
- 同一device合法轮换后，以当前有效密钥版本认证查询，保留原confirm/claim的历史凭据版本；不得要求历史版本等于当前版本而抹掉原SENT事实。result沿现有补报语义允许轮换，只要原device/request/claim/context与自身hash正确。
- 阅读仅同一原帖、自己发送的精确根评论、原需求作者直接回复；实际页面账号与原发送账号必须一致。其他作者/其他目标回复不输出。
- API每页10条、最多3页、总等待15秒；超过为PARTIAL，原cursor保留内存不落日志；重复cursor/冲突/错误不得返回空成功。验证、限流或格式变化立即停止，不自动重试/绕过。正文、时间、公开ID直接取原平台数据，已读UNKNOWN，不猜精确时间。
- 不额外导出/持久化/记录Cookie或登录态，不读取私信；仅同隔离浏览器在内存中使用既有登录态完成鉴权。页面临时xsec_token只在同账号客户端请求内使用，不进入结果/错误/日志。测试平台数据全部标合成，未验真实平台或Windows。

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

## 本批证据

- 原生reader `9dee3f3`：新增read_sub_comments依赖/方法前RED（构造参数不存在）；首次reader+原发送+runtime共30 PASS。新增同公开ID跨作者冲突反例RED后修复，最终受影响reader/runtime两文件23 PASS；未改原发送方法，原9项发送证据复用，不相加。惰性同browser客户端专项1 PASS（包含于最终23）。测试仅合成页面和平台响应，不证明真实XHS能读到根评论或接受API。
- 读取结果不携带临时token/cursor，无评论/私信/改已读动作。原 runtime CHECK/EXECUTE 不主动创建读取客户端。新能力尚未接到私有worker/main/客户端同步入口，当前产品不可宣传自动回流已上线。
- 后端`c0c4608`：严格只读`POST /replies/sync-context`从认证owner原SENT队列、领取和平台回执定位根评论；保留原画像/来源历史，核hash与设备绑定。新增route 404 RED→定向PG20 PASS；实施者最终受影响reply_api+signed_reply两文件22 PASS/14.96秒，集合重叠不相加。[后端记录](xhs-reply-origin-report.md)保留命令/边界。仅隔离临时PostgreSQL及合成平台证明，原现有数据库未修改；整批独立审核待收口。
- 原整批审核`c0c4608` NO-GO：P2确认payload顶层requestId未与原queue主键核对。root同时发现同device合法轮换后历史SENT因旧版本强制等于当前版本而拒绝。修复`74f7a16ff90f4cbd9c58521c9c7ce36b5f224a2d`两个反例RED后，仅新增两例+原正向 **3 PASS/2.86秒**；未重跑22项。最终独立静态增量审核 **GO**（报告HEAD`3a068496bbe18b93b1da2a112b0637b266084c7a`），原P2关闭、无新增P1/P2，原整批其余结论复用。
- Cookie文字修正为同隔离browser内存鉴权、不额外导出/持久化/记录，与既有授权runtime实际机制一致。临时PG容器`yike-reply-source-20260912`归本批独占，核对归属后停止移除，仅丢弃可重建合成数据，原库未动。没有构包、真实平台或Windows实机测试；08父卡/完整Goal不关闭。

## 接续位置（不是已实现）

- `app/windows_platform_outreach.py`/`app/platform_outreach_worker.py`现仅识别EXECUTE；下一片需要互斥的只读操作，调用本片read_replies，保留同profile租约/进程物理退出门禁。原执行权限不能因读取而产生；批量回复须有独立有界帧校验，不能直接塞入现128KiB发送结果帧。
- `desktop/src/main/platformOutreachDriver.ts`与main身份scope接原sync-context查询；renderer只表达原请求同步意图，不提交正文/tenant/根ID作为读取权威。结果从私有worker归一化，经现`/replies/signing-payload`及`/replies/signed`设备签名提交；未知提交先查证据，不盲目重复创造事件。
- 最后接现有回复证据页/原发送结果上的显式同步动作及取消/错误/部分结果状态。完成main/worker/UI后再执行受控真实平台与Windows验证；本片不应宣称已完成这一链路。
