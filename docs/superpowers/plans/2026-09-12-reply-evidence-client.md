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

## 本批交付与证据

- 后端 `bbe6add`：投影与三个查询统一返回数据库 revision，未改签名字节或迁移。[后端证据](reply-evidence-backend-report.md)：纯投影先 KeyError RED 后 1 PASS；HTTP/PG 4 SKIP，缺少 fixture URL，不算实际数据库通过。
- 客户端 `c9118d9`：严格证据 DTO、固定 GET/数组原样传输，接已有跟进页真实目标分支，原身份门控与迟到响应隔离、最高版本显示及可展开原历史。来源与空/错状态独立，不新增外部动作。
- 新 DTO/UI 用例先因模块不存在 RED。四个定向文件（replyEvidence、reply-evidence-panel、client、followup-reply-entry）首次 67 PASS / 1 FAIL；唯一失败是测试在异步首次调用前切换身份，原一次性 pending mock 留给新身份。核对 boundedRequest 微任务调用后，用 waitFor 等首次调用再切换；只重跑受影响 UI 文件 4 PASS，其余文件 63 PASS 复用，集合不相加。
- `tsc --noEmit` PASS，`git diff --check` PASS。未跑全仓测试、重复构包、真实私信或实际生产访问。独立审核结果待下文更新，未将代码候选当完整08或产品完成。
- 独立审核`c9118d9` NO-GO，发现P1：普通session/token/SMS只投影user而没有accountScope，手造session的UI用例漏掉实际入口。修复`f989307`由认证registry的tenant_id生成scope，三个认证入口和客户端统一传递；scope version沿现有contact snapshot固定v1，不从回复内容反推租户。新增普通service三种登录→RelatedReplies商机核对→证据GET用例，3项RED后GREEN；后端会话字段断言1项RED后GREEN。修复后受影响HTTP/session/phone两文件59 PASS（合成store，非实际PG/短信），客户端panel+client两文件45 PASS，tsc PASS；这些含前述复跑，不相加。手机号PG断言同步更新，因已知fixture缺失不重复运行。最终仅复审P1增量。
- 最终独立增量审核GO：`f989307b00bd8f80ca18a01df4a7a2ed7928d8f8`，原P1闭合、无新增P1/P2；reviewer只读静态核查，未重跑测试/构包。整批其余审核复用`c9118d9`结论。08与完整Goal继续进行，下一步是原运行时Windows新候选及真实收发/回复同步联验，不重复开发已接只读证据入口。

### 隔离 PostgreSQL 补验（2026-09-12，源码 `8e7e3de`）

上批缺少测试URL不等于本机无数据库能力。本次只读发现Docker可用后，另建本任务专属临时`postgres:16-alpine`容器，绑定随机回环端口、tmpfs数据目录；没有复用或修改现有`yike-identity-contract-pg`库。现有fixture在新空库迁移并创建受限NOLOGIN/NOBYPASSRLS执行角色，通过真实HTTP处理器、Ed25519验签和PostgreSQL查询验证。

唯一测试命令（两个fixture URL仅指向该临时实例）：`python -m pytest tests/test_signed_reply_http_postgres.py -k 'reaches_original or manual_record or later_poll or forged_signature' -q --tb=short`。

结果：**5 passed / 9 deselected / 0 skipped，5.57秒**。覆盖原UNKNOWN发送关联回复但不改SENT、伪造签名/跨所有者拒绝、同事件已读revision 1→2与证明保留、人工记录分型、同ID/新临时ID重复观察复用canonical事件。复用原有用例与产品字节，没有全量回归、构包或重跑已经通过的UI检查。该结果补充此前4 SKIP的数据库证据，不改写原失败/跳过历史。

未覆盖实际Windows、真实平台输入、短信提供商、后台持续同步、生产部署或客户UAT；不能据此标08或Goal完成。临时容器检查归属后停止并移除，tmpfs内仅本轮合成数据随停止丢弃，无需恢复；原数据库容器保持运行。
