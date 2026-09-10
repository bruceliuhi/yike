# 08 签名回复接原发送请求

沿既定V0.2任务08内联执行/TDD，基线f9fa484，不改Win客户端，不轮询私人会话或外发。现有117来源不能识别122/123发送请求，本批把真实HTTP入口接上原队列冻结来源，而非伪造旧整数版本。

1. 写`tests/test_signed_reply_http_postgres.py`普通runtime RED，再接`pilot/signed_replies.py`和既有reply API：`/replies/signing-payload`、`/replies/signed`接受原claimId/contextSha256/设备凭据版本及PlatformReplyEvent，使用独立设备+session签名域。
2. 同cursor验证owner、原领取、来源/画像/平台/用途/原目标作者及回复时间；仅原队列SENT/UNKNOWN可关联，UNKNOWN回复不自动变已发送。后来来源关闭/画像修改不阻断原回复事实。使用原设备当前有效密钥，撤销拒写。
3. 抽出`ReplyEventStore.record_in_transaction`复用事件防重/已读/修正，不另造回复库。新来源的平台事件必须走签名入口；原`/replies`保留旧117及人工记录，不接受伪造新来源。124仅给现有不可变事件新增nullable `device_attestation`，不改变旧payload摘要或事件DTO；真实验签后由服务写证明元数据，不存签名/秘密。
4. 新`/opportunities/{id}/replies/evidence`返回事件与其验证来源，区分DEVICE_ATTESTED_PLATFORM_REPLY、OPERATOR_RECORDED、MANUAL_RECORD；既有列表/客户端DTO不破坏。设备证明不冒称服务器独立读取平台。
5. 定向实际PG/HTTP和受改reply_store测试，一次独立审核；必要失败仅差量补验。文档记录来源协议/部署/下一步真实客户端，正常推main，不构包、不宣称客户回复/上线。

本批仍缺真实渠道读取、客户端持久消费与Win接入；完整Goal不缩小。

## 本批验证

`9df9d69`经非作者`draft_batch_review`对`f9fa484..9df9d69`独立规格/代码/架构审核GO，无阻断，未重复测试/构包。真实HTTP、受限PG和Ed25519，平台输入合成，不是客户回复证据。

- 缺新路由404 RED：1 failed。实现后新回复11项及原store32项合跑42 passed/1 failed，15.46s。旧“错误类型纠正”夹具没建来源，新授权检查先返回reply_origin_unavailable；给夹具补合法117来源，使其确实走到类型检查后，仅该项重跑1 passed，0.96s，未放宽拒绝条件。
- 持续轮询仅observedAt改变时，原算法对固定/新event UUID均返回409（2 failed RED）。新签名入口保留首次事件/证明、同原逻辑锁下防UUID混用；仅新增轮询2项及已读/并发影响2项补验4 passed，4.30s。旧store的严格事件语义不放宽，未重跑全部集合。
- 临时数据库均已按本次创建范围删除，无生产操作、未构包。旧payload及摘要兼容由原store定向用例覆盖；新增13项回复HTTP与原32项为分批证据，不冒称最后一次全量45 passed。

本批不会修改队列发送状态，没有读取真实平台私信或发送消息；本机消费/真实通道及Win新接口接收仍是下一步。
