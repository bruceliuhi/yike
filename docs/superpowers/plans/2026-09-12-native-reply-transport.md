# 原生回复进程桥与设备签名接续

沿已批准08回复链路执行；base `4f61f26`。使用任务拆分/TDD/一次整批审核，按用户要求只做受影响测试，不构包。Goal不缩为本切片。

## Global Constraints

- 复用现私有host/worker/原profile租约与物理停止；CHECK后只允许一个互斥动作EXECUTE或READ_REPLIES，读取不调用execute、不产生发送许可。正常发送协议与32768字节stdout总上限保持。
- 外部第二帧READ_REPLIES：`{schema_version:'windows-platform-outreach-v1',action:'READ_REPLIES',operation:{rootCommentId,claimedAt}}`；根为24lowerhex，时间awareISO。内部socket统一operation：读取为`{readReplies:{rootCommentId,claimedAt}}`，旧发送仍原3字段dict。严格拒绝混合、extra、重复第二帧、先于READY的动作。
- 结果仍RESULT/outcome。读取outcome为本片reader的`{status:'COMPLETE'|'PARTIAL',items:[...]}`。只有读取模式允许512KiB单个返回帧，合计stdout不超过512KiB+32KiB；上下文/命令输入仍128KiB，发送结果预算不放宽。Node必须验证原买方、ID/时间、30条上限、重复ID，清理并实际close前不发布读取成功。
- 没有cookie/profile/token进入结果日志；既有runtime仅同browser内存鉴权。私信/改已读/发送未授权，不在开发测试执行真实平台动作。
- 主进程reply签名须严格匹配原认证user/tenant/device、规范JSON、完整request及`yike-platform-reply-v1`签名域，renderer不能获得私钥/签名入口或提交自造回复。

### Task 1: Python私有桥（独立实现）

Own app/windows_platform_outreach.py、app/platform_outreach_worker.py、现有对应test或新增tests/test_native_reply_bridge.py；报告docs/superpowers/plans/native-reply-bridge-report.md。

- [ ] RED第二帧READ_REPLIES当前拒绝。保留_operation旧返回语义，加_read_operation/统一内部操作验证；_second/host调度/worker读取按GlobalConstraints打通。_Input只接一次，在READY之后。不要复用EXECUTE外层动作代表读取。
- [ ] worker根据内部唯一readReplies分支调用`await channel.read_replies(context,rootCommentId,claimedAt)`；绝不调用execute。EOF/取消仍终止原owner任务及物理子进程，清理失败不变成功。
- [ ] 只在已接受read操作后放宽返回帧/总输出预算，固定上限如上；普通EXECUTE、READY和输入帧不放宽。host原return字典结构保留，未知/失败不得伪造COMPLETE空数组。
- [ ] 定向协议/真实socket合成worker测试：读取方法收到精确根/claim，execute调用0、一次生命周期、EOF取消、大于32KiB合法read返回、超512KiB拒绝、extra/混合拒绝。现发送测试按影响跑一遍，无Windows时不称实机通过。
- [ ] 提交自己文件，报告RED/GREEN命令、SHA、已知边界；root做整批独立审核，不自行push。

### Task 2: Node驱动、私有请求及签名（root）

Own desktop/src/main/platformOutreachDriver.ts、nativeReplyProtocol.ts、nativeReplySigner.ts、serviceClient.ts、shared/replyEvidence.ts、新定向tests。

- [ ] RED驱动无readReplies与新私有路由/签名函数。新增严格replyBatchSchema和`parseNativeReplyBatch(raw,authorPublicId,claimedAt)`校验当前原作者/时间/重复ID。export现有platformEvent schema用于签名请求，不复制另一份事件定义。
- [ ] driver.readReplies(context,{rootCommentId,claimedAt},signal)与execute互斥；CHECK原context绑定一致才发送READ_REPLIES。读取数据仅物理close成功/cleanupConfirmed后返回，不把发送UNKNOWN当COMPLETE。返回帧预算按读取模式变化，不放宽发送；stop沿原物理语义。
- [ ] 私有requestOutreach新增固定操作：replies.source POST /api/ui/replies/sync-context（payload=requestId/deviceId/credentialVersion）；replies.prepare POST /api/ui/replies/signing-payload（payload={request}）；replies.record POST /api/ui/replies/signed（payload={request,signature}）。不加入公共API_OPERATIONS/preload。
- [ ] `signNativeReply({key,prepared,expected:{serviceOrigin,userId,tenantId,request}})`核256KiB字节上限、完整规范JSON与域/owner/tenant/request一致，再复用Ed25519私有primitive。正文只来自原worker后续装配，当前未向renderer开放。
- [ ] 定向驱动/协议/签名测试与一次tsc；整批审核后main。本片补可调用原生读取和签名传输，下一主链是main身份/profile装配及现有界面同步意图，未装配前不可标回复同步可用。
