# 04B 已确认研究策略接入合同

2026-09-10；CodexWin工程片已独立审核，合同`0678383`、HTTP`808f44b`、持久层`eadcd2c`，见[限定验收](../qa/V02-04B_CONFIRMED_STRATEGIES_WIN_REVIEW.md)。非Mac已接收ACK。唯一状态见[任务书](../V02_IMPLEMENTATION_TASKBOOK.md)，实施边界见[计划](../superpowers/plans/2026-09-10-win-confirmed-strategies.md)。114归Win本片；不改111执行、112候选、113判断。

## 确认什么

保存完整公开配置后，服务端创建策略版本和摘要；用户确认这个快照，才可供执行服务核验。prepare不确认、confirm不创建采集任务，任何一步都不表示平台可用、已执行、扣费或买方意向已核验。

画像沿用当前tenant共享版本，策略按tenant+当前user私有。客户端Profile.id/TaskDraft.profileId是画像版本ID，不是父业务ID。身份只取已认证会话；请求不提供tenant、owner、复核人或批准时间。

## 五个入口

以下路径前缀`/api/ui`，通过独立`register_research_strategy_api(router, service, identity, require_session_https)`注册。共享app/db入口仍需Mac串行接收，当前没有自动安装或启用默认能力。

| 方法/路径 | 严格输入 | 返回 |
|---|---|---|
| POST `/research-strategies/prepare` | PrepareStrategyRequest | PREPARE原回执 |
| POST `/research-strategies/confirm` | ConfirmStrategyRequest | CONFIRM原回执 |
| POST `/research-strategies/revoke` | RevokeStrategyRequest | REVOKE原回执 |
| GET `/research-strategy-operations/{request_id}` | 原请求UUID | 原不可变回执 |
| GET `/research-strategies/{strategy_version_id}` | 策略版本UUID | 当前版本视图 |

沿用既有`_UiRoute`、同Origin中间件、HTTPS、SessionRegistry及no-store。请求正文只接受UTF-8 JSON对象，实际字节上限128KiB，不相信Content-Length；拒重复key、非JSON数字和未知query。POST身份检查与数据库调用不阻塞异步事件循环。无服务返回501 capability_unavailable；不是降级合成策略。原始错误、请求正文与凭据不回显。

prepare精确字段：schema_version=`strategy-confirmation-v1`，request_id/draft_id/profile_version_id规范小写UUID，draft_revision严格正整数≤2147483647，configuration，有序platforms，max_records（1..10000），max_runtime_seconds（1..86400）。每个字段均明确提供，不能把bool当整数；不从搜贝或去重来源数推导技术预算。

configuration使用`research-strategy-v1`：任务名、source search/links、keywords、exclusions、links、mode once/monitor、schedule及research基础设置。完整字段及限制见计划Chunk1；额外任意字典、凭据字段、未实现证据验证的provenance明确拒绝，不能静默丢弃后启动。R4切换source保留另一侧输入，所有字段参与确认；真正执行只采用选定source，不因隐藏输入有值扩大范围。URL通过结构验证不代表站点已获运行许可。

confirm精确字段：同schema_version、原request_id、strategy_version_id、完整configuration_sha256及human_confirmed=true。revoke为同schema_version、request_id、strategy_version_id；画像过期/改变不阻止用户撤销自己的策略。

## 快照、状态及原请求

完整执行快照恰含profile_version_id、strategy_version_id、configuration、platforms、max_records、max_runtime_seconds。摘要是sorted-key/紧凑/UTF-8 JSON SHA256，排除configuration_sha256本身；平台顺序也参与。此摘要与旧UI taskFingerprint/hash不是同一协议，必须分别保留。

版本状态DRAFT→CONFIRMED或REVOKED，CONFIRMED→REVOKED，不恢复撤销。更高draft_revision准备成功后，旧版本即不再是当前执行策略；同内容新revision仍须确认。相同revision用不同request_id准备时，画像版本/原内容摘要/配置/平台顺序/两个预算必须全部一致才可复用，不能只比较关键词。旧revision不能回退当前指针。

成功操作与回执同一事务。原request_id重放原状态，不随以后确认/撤销/修改而改变；同ID不同操作/内容409。同用户新有效会话可核对历史，不重新执行动作。错误、超时或连接中断后先查原request_id，404只代表当前未找到可见回执，不证明此前确定失败；不换ID猜测重试。

原回执固定字段：schema_version、request_id、operation（PREPARE/CONFIRM/REVOKE）、strategy_version_id、draft_id、draft_revision、profile_version_id、profile_sha256、configuration_sha256、snapshot、state、recorded_at。

当前版本视图不包含request_id/operation/recorded_at，包含同一版本核心绑定、state、created_at/confirmed_at/revoked_at、is_current和profile_current。历史回执的CONFIRMED不等于当前可执行，当前视图也不能代替执行时的事务护栏。

## Mac同事务接收

`ResearchStrategyStore.resolve(cursor, claims, profile_version_id, strategy_version_id)`供[执行合同](V02_EXECUTION_RUNTIME.md)及04C的ASSESS/INCLUDE写入使用，返回真实`ConfirmedExecutionStrategy`。它校验当前用户的当前已确认版本、画像仍CONFIRMED且完整payload摘要与prepare一致、不可变快照及摘要重算一致；不读取客户端自报已批准结果。

锁序兼容现有会话→画像父行/版本→策略draft→策略version。resolver不取原操作request锁，不commit、不另开连接、不网络，不反锁设备/任务/候选；拒绝autocommit cursor。调用方事务回滚不被resolver吞掉。撤销/编辑与实际提交通过相同策略行互斥，不靠UI本地复选框实现撤销。

`ResearchStrategyStore.read_snapshot(cursor, claims, profile_version_id, strategy_version_id)`仅用于列表展示：要求调用方已经建立非autocommit的`REPEATABLE READ READ ONLY`事务及`yike.user_id / yike.tenant_id`，user必须匹配claims。它不会调用会话验证、重新获取会话锁、改作用域、另开连接、提交、取行锁或联网；身份实时检查由候选列表外层READ COMMITTED事务在读取前后负责。按tenant/owner查询版本与draft，按tenant查询画像版本及父行，校验CONFIRMED、当前draft指针/修订、完整画像payload摘要与profile/prepare双重绑定和策略`_intact`。

reader返回新建的普通JSON字典：六项执行快照字段加`configuration_sha256`，platforms是JSON列表，不返回`ConfirmedExecutionStrategy`，不能用于START、上传、ASSESS或INCLUDE授权。无效/撤销/被替代/损坏的数据产生409 `strategy_conflict`；缺失或不匹配身份作用域产生401 `invalid_session`；数据库故障产生脱敏503 `strategy_store_unavailable`。候选列表仅将409视为stale，401/503不是空结果。原CONFIRM回执在撤销后仍为历史回执，不恢复当前授权。

共享入口由Mac串行接收以下最小接线；Win本片没有编辑这些共享文件：

1. `pilot/db.py`迁移清单追加`("v02-research-strategies", migration_path.with_name("114_v02_research_strategies.sql"))`，保留111/112及Mac在途113。114依赖已存在的用户和画像表，不要求先启用110建议服务。
2. 受信升级路径设置准确的`yike.app_role`后执行`deploy/grant_research_strategies.sql`；它不授予基础身份/画像权限，这些沿用已验收的应用角色配置。禁止将管理员数据库连接传给Web或桌面。
3. `pilot/web.py:build_app`和`pilot/ui_api.py:register_ui_api`增加可选`research_strategies=None`并逐层传递；在现有`_UiRoute` router上调用`register_research_strategy_api(router, research_strategies, identity, require_session_https)`。没有注入时认证请求得到501；保留既有Origin/会话/no-store及所有旧接口。
4. 受信组合入口以**同一个受限应用数据库**创建`strategies = ResearchStrategyStore(application_database)`，将`strategies.resolve`注入`ExecutionRuntime(..., strategy_resolver=strategies.resolve, capability_check=verified_source_policy)`；候选上传继续复用该runtime。`verified_source_policy`必须由实际验收范围产生，不是本片提供的可部署默认值，不提供`lambda True`生产替代。04C显式注入`CandidateReviewStore(..., strategy_resolver=strategies.resolve, strategy_snapshot_reader=strategies.read_snapshot)`：写入保持同事务resolver与锁序，列表只用同快照reader，无写入resolver回退。
5. 接收时最少验证迁移重复执行、默认未注入501、认证后的真实prepare→confirm→读取/撤销，以及真实策略替代合成resolver后的START→CLAIM→签名上传、撤销后提交拒绝/CANCEL仍可用。现有可复用回归在`tests/test_research_strategies_postgres.py`；其来源policy和候选内容明确是测试边界，不是实际平台验收。

Mac接收须绑定实际合入SHA和消费结果另行ACK。本片不直接将`task_execution`、研究预算或任一来源能力设为可用。

## 05C接续及未完成能力

P19准备时保留旧草稿、旧hash、旧未决ledger；另记录prepare UUID、server策略UUID/完整hash与对应draft/revision。核对服务端快照各项与当前准备展示内容一致后，用户主动确认绑定该快照。编辑、版本漂移或来源/预算变化使该确认失效；不能直接携带旧复选框的true确认未展示的新快照。CONFIRM成功后，05F才可用新签名协议衔接START；两步未知各核对自己的原回执。

R4全部停止条件、搜贝真实预留/计量、monitor调度、类似/覆盖来源核验仍须接通；114存下这些设置不证明执行器已强制它们。没有完整对应护栏就不得启用相应执行模式；不取消首发原文证据、多找类似或短句建联，也不以工程测试替代真实来源、实际客户使用或生产验收。
