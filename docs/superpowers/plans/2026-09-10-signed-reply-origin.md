# 08 签名回复接原发送请求

沿既定V0.2任务08内联执行/TDD，基线f9fa484，不改Win客户端，不轮询私人会话或外发。现有117来源不能识别122/123发送请求，本批把真实HTTP入口接上原队列冻结来源，而非伪造旧整数版本。

1. 写`tests/test_signed_reply_http_postgres.py`普通runtime RED，再接`pilot/signed_replies.py`和既有reply API：`/replies/signing-payload`、`/replies/signed`接受原claimId/contextSha256/设备凭据版本及PlatformReplyEvent，使用独立设备+session签名域。
2. 同cursor验证owner、原领取、来源/画像/平台/用途/原目标作者及回复时间；仅原队列SENT/UNKNOWN可关联，UNKNOWN回复不自动变已发送。后来来源关闭/画像修改不阻断原回复事实。使用原设备当前有效密钥，撤销拒写。
3. 抽出`ReplyEventStore.record_in_transaction`复用事件防重/已读/修正，不另造回复库。新来源的平台事件必须走签名入口；原`/replies`保留旧117及人工记录，不接受伪造新来源。124仅给现有不可变事件新增nullable `device_attestation`，不改变旧payload摘要或事件DTO；真实验签后由服务写证明元数据，不存签名/秘密。
4. 新`/opportunities/{id}/replies/evidence`返回事件与其验证来源，区分DEVICE_ATTESTED_PLATFORM_REPLY、OPERATOR_RECORDED、MANUAL_RECORD；既有列表/客户端DTO不破坏。设备证明不冒称服务器独立读取平台。
5. 定向实际PG/HTTP和受改reply_store测试，一次独立审核；必要失败仅差量补验。文档记录来源协议/部署/下一步真实客户端，正常推main，不构包、不宣称客户回复/上线。

本批仍缺真实渠道读取、客户端持久消费与Win接入；完整Goal不缩小。
