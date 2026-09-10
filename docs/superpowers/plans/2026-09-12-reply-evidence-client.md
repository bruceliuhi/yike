# 回复证据接入普通客户页

Base `86e5c02`。沿已批准08回复/跟进范围，接已有认证evidence API到现有跟进页，不新建CRM/通知/自动回复。Windows当前没有可调用主机，本片不依赖平台登录、不读取真实私信。定向验证、一次独立整批审核，差量修复。

## Global Constraints

- 只读本人当前客户空间的指定商机；payload只允许opportunity UUID，不接受租户/用户覆盖。服务端仍以现身份和RLS筛选。换用户/空间/商机立即隐藏旧数据，迟到响应不得跨身份显示。
- 来源区分`DEVICE_ATTESTED_PLATFORM_REPLY`（设备提交平台证据，非服务器独立核验）、`OPERATOR_RECORDED`（历史操作员登记）、`MANUAL_RECORD`。不把人工记录、已读修订或重复观察计为新回复；UNKNOWN发送收到回复不自动改SENT。
- DTO保留canonical event_id、revision、原发送/来源/画像/正文/时间与证明；拒绝错域、不完整/重复版本、手工记录携带平台证明。当前选定画像变化不丢历史事实，仅展示原画像版本。
- readonly页面不签名、不改已读、不回复、不新建发送，旧人工跟进和旧followup service保持原行为。空数组=暂无保存证据，不等于平台无回复或已完成平台同步；错误不显示为空。

## Task 1 — backend evidence revision（独立实现）

专属pilot/signed_replies.py及对应定向测试。evidence_row增加顶层`revision`，取数据库revision而非自行推导。record/语义去重/list_evidence所有调用都携带真实revision，原签名/事件payload/hash不变；不改migration。补一个纯投影失败用例和现有HTTP/PG测试断言（按可用环境跑，不把skip当真实PG通过）。report同目录reply-evidence-backend-report.md。不修改desktop。

## Task 2 — strict read DTO / fixed route（根代理）

共享replyEvidence.ts定义严格event与来源证明、revision，校验当前user/tenant/opportunity，按平台公开回复身份+revision折叠重复已读修订，保留完整历史；人工事件不混入平台列表。现servicePolicy/API_OPERATIONS新增唯一GET replies.evidence，普通service提供可选replyEvidence(opportunityId,signal)实际调用原数组API。保持现有request对象型调用兼容，不将数组强制变{}。无写路由。

## Task 3 — existing RelatedReplies（根代理）

已有商机选择/只读来源页组件复用。在已核对非样例目标且普通replyEvidence可用时优先展示证据面板：当前通道回复/来源标签/读状态（UNKNOWN明确未知）/原请求/原时间；完整追加历史另放details，人工证据分别标记。无目标时请选商机，未接服务时旧路径保持。认证/空间/目标改变时清理，刷新只GET。测试错域、重复修订折叠、错误不变空、换身份迟到隔离和实际普通service固定路由。最终类型检查，独立审核后main。
