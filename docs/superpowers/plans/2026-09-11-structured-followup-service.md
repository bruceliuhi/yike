# 结构化跟进与原请求恢复接线

> Use subagent-driven-development。沿用已批准P14/P15和UI_FOLLOWUP_CONTRACT，不改页面设计；用户要求省token：定向测试、一次整批独立审核，不重跑全量。

**Goal:** 普通客户持久保存实际联系时间、负责人、下一步与下次跟进；可纠正/撤销并核对原请求，同时保留旧人工登记和已验签回复。
**Architecture:** 现有认证/租户PG、追加式记录/回执与现成P14/P15。结构化服务不解析旧备注，不轮询平台、不发消息、不假称发送到期通知。
**Stack:** FastAPI/PostgreSQL、现有React/Node24/Zod。

## Global Constraints

- 按 docs/UI_FOLLOWUP_CONTRACT.md 的FollowupService.list/replies/mutate/operation，字段匹配 desktop/src/renderer/domain/followup.ts。source/sample/tenant/profile由服务端核验，不能信客户端身份。
- requestId与binding/完整values/reason原子绑定；重复同请求返回原回执，改内容409；operation只读本人原请求，无记录404不冒充FAILED。同targetRevision并发纠正/撤销只能一个成功，事务内重验身份/目标/当前画像，无外部网络。
- 记录按tenant与创建用户隔离，负责人可从同租户真实成员选择（不改变读写归属），名称来自已保存成员资料；无显示名时明确成员标识，不伪造人名。旧pilot_followups没有owner/历史画像，不回填推断；list额外返回legacyRecords沿用已授权旧人工只读字段。前端legacyRecord显示未知负责人/时间且禁改，不能隐藏历史。
- 新数据：已确认画像/真实商机、UUID、正整数revision；note必填≤500，nextStep≤500，时间有时区ISO，occurredAt不可未来；nextFollowupAt可历史。只有结构化日期产生本地到期标签，不创建通知。
- correct产生新ACTIVE记录+correctsId，旧记录保留原文投影CORRECTED且revision递增；void原id投影VOID且revision递增；历史不能覆盖或恢复ACTIVE。撤销/纠正必填原因≤500。当前状态按有效记录计算，不能让已撤销旧记录继续支配新工作台。
- replies只投影已有DEVICE_ATTESTED_PLATFORM_REPLY且归属/发送关联有效的事件；不从人工REPLIED生成通道消息，不隐藏读取失败。无目标只返回未匹配集合，当前存储全部有明确opportunity因此可为空；目标必须存在/当前用户可访问。mark-read仅本应用已读，保留原始平台事实/签名，不调用平台标读；UI注明这个语义。
- 新表FORCE RLS、最小授权、追加不可变，管理员仅迁移/grant；不暴露内部payload/credentials。普通路由固定、no-store、严格请求限32KiB。快照最多5000记录/回复，超限明确503，不截断伪称完整。

## Task 1: 后台（独立实现agent）

Own `pilot/followup_service.py`, `pilot/followup_api.py`, `migrations/131_v02_structured_followups.sql`, `deploy/grant_structured_followups.sql`, `tests/test_structured_followup*.py`。必要辅助模块以followup_前缀，不改共享runtime/db/store/ui_api/web（Root接线）。

接口 `FollowupService(database, reply_store=None)`：`.list(claims)`返回{records,members,legacyRecords}；`.replies(claims,opportunity_id=None)`数组；`.mutate(claims,raw)`/`.operation(claims,raw_binding)`同前端契约回执。`register_followup_api(router, service, identity, require_session_https)`。GET `/followup-workspace`，GET `/followup-workspace/replies?opportunityId=UUID`（可无query），POST `/followup-workspace/mutate`、POST `/followup-workspace/operation`；无服务501。

list legacyRecords为旧客户端Followup字段{id,opportunityId,title,status,note,createdAt,kind:'manual'}，不塞入结构化records。records/member/receipts的时间输出毫秒ISO；各记录没有sample=true。仅create/correct/void/mark-read接受mutate，legacy-create不可写。members读取同tenant有效成员（姓名无则“成员+短ID”）。已验签回复列表复用signed_replies.evidence_row及原始payload校验，不直接把任意旧reply_events当签名事实。

新增追加式结构化记录修订+原请求结果表，以及本应用reply read修订（可同操作表投影，避免再造平台事件）。source记录/机会/目标采用既有锁顺序，原请求和目标串行锁保CAS。历史operation只核对原请求归属不因后来correct/void篡改回执。失败异常不返回假的confirmedFAILED。

- [x] RED新增service缺失及严格input/回执规则；实现有限模块。
- [x] 定向受限RoleDatabasePG：实际confirmedstrategy→signedingestion→humanverify/include；create完整字段/同request重放/改body冲突、correct→oldCORRECTED+newACTIVE、void→revision上升、旧回执不变、旧revision拒绝、跨owner/tenant/错member/profile拒绝、原无request404、legacy仍可读。使用现有签名reply fixture验证本应用read不改平台记录；不能管理员/replica造成功。
- [x] 自查+追加commit，仅own files，不amend/push；报告RED/GREEN/命令与未验证边界。Root共享接线、ordinaryNodeHTTP联验和全批review。

## Task 2: 普通客户端/现有页面（Root）

新增shared/structuredFollowup.ts严格UUID wire、services/structuredFollowup.ts固定route适配；所有mutate/operation保原binding及当前session边界，list/readReplies/readReceipt复用既有域验证。普通client挂followup；IPC只允许4种固定operation，不接受任意URL。现有服务可选约定不变。

域FollowupSnapshot增加可选legacyRecords（旧mock不必提供），独立readWorkspace合并legacyRecord到FollowupView，仅P14列表/相关人工记录使用；P15仍结构化records/members。已读文案明确“仅意客内”，不制造实际平台已读。

注册迁移/runtime/web/ui_api，部署新增grant；根核对旧opportunity的latest_followup_status消费者，当前用户结构化有效记录须参与状态投影（历史VOID/CORRECTED不算，旧三字段记录保留）。不让新登记一份同时写成无owner历史副本。

- [x] 新adapter及legacy合并测试RED→GREEN；固定route、原回执、切账号迟到、401/404保留未知；受影响UI定向测试。
- [x] 一个ordinaryNode→runtimeHTTP→受限PG场景完成完整字段create、原操作恢复、纠正/撤销与历史保留；类型检查，必要一次renderer构建，不重跑全套。

## Task 3: 接收

- [x] 一次整批独立审核，修复只差量；仅本计划存完整证据，契约/任务书简短引用。Goal仍完整V0.2，不用本片证明上线/盈利。

接收后执行 fetch、正常推送 main 并核对远端 SHA，清理本轮隔离测试资源；推送结果以 Git 实际状态为准。

## 实施与验证

2026-09-11：后台 `a6c3f9e`、普通客户端接线 `7e2ff63`、边界补充 `2815d86`。整批独立审核对 `2815d86` 判定 NO-GO：同租户其他负责人可选但保存被 RLS 拒绝；已验签回复的撤销历史被当成普通活跃回复。两项各经一个受限 PostgreSQL 最小反例确认；只修复并回归这些差量，不重跑整批。

- 普通客户端现接入结构化登记、实际联系时间、同租户负责人、下一步和下次跟进时间；纠正/撤销保留历史，保存响应丢失可按原请求找回回执。旧人工记录保留只读，不推断负责人或把新记录重复写入旧表。
- 相关回复来自既有已验签事件；应用内已读不更改平台原始事实。原始证据和显式同步仍可从相关回复区打开。到期标签不是已发送提醒。
- 后台新增测试缺模块 RED 后定向 API/受限 PostgreSQL **5 passed**；追加隔离、并发纠正/撤销、签名回复及应用已读边界 **6 passed**。修复目标锁读取和 mark-read 嵌套事务，拒绝 NUL、非法 Unicode 和越界 revision。
- 普通适配器新增测试缺模块 RED 后 **3 passed**；受影响两组 UI 测试最终批次 **9 passed / 1 failed**（失败为已读文案旧断言），修正该断言后仅重跑对应项 **1 passed / 5 skipped**，不重复累计。此前 UI 检查暴露原始证据组件遮盖结构化操作，已改为显式展开原始证据入口。
- `tests/test_followup_client_postgres.py`：实际普通 Node 客户端→运行时 HTTP→受限 PostgreSQL **1 passed，4.75s**，内部 Node 场景 **1 passed、未跳过**。覆盖完整字段保存、丢失响应恢复、同请求重放、纠正、撤销、历史回执、当前状态和退出登录；发现并修复当前商机状态忽略结构化记录的问题。旧历史数据仅作为管理员合成夹具准备，成功的新业务写入使用受限应用角色。
- TypeScript 类型检查通过；单次 renderer 构建通过（474ms）。未重跑全套测试、Windows 或 Electron 构包；本批采用一次整批独立审核，修复仅差量验证。

审核修复 `2f67036`：负责人验证复用同租户 ID-only 成员函数，不扩大原用户表或记录所有者权限；普通回复列表只投影未被有效 CORRECTED/VOID 事件控制的 ACTIVE 事实，历史仍在原始证据入口。授权脚本同时改为核对实际表 owner。只运行有效同租户成员、VOID、CORRECTED 三项差量：**3 passed，3.00s**；未重跑 Node/HTTP、UI 或构建。

独立差量复审 **GO，绑定 `2f6703640b820360ae49c2572620ec1b48721222`**；两项 Important 关闭，控制事件关联沿用原入库的租户/用户/发送/商机校验。本增量可接收，未将此结论扩大到完整产品。

以上是本地隔离数据库与合成业务输入的工程证据，签名回复也使用合成来源，不是实际平台回复、客户试用、生产部署或盈利证明。部署须先执行迁移 131 与 `deploy/grant_structured_followups.sql`，再启动新运行时；本轮未操作生产。完整 V0.2 Goal 保持进行中。
