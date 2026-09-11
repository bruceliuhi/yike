# 首页机会简报真实服务

> Use subagent-driven-development，复用已批准 R4 P02 及 UI_OPPORTUNITY_BRIEF_CONTRACT；用户要求省 token：只测新增链路，一次整批独立审核，修复只差量。

**Goal:** 普通用户首页直接读取本人当前画像已有的已核验可联系机会与到期跟进，保留来源、日期和未检查范围，不以组件样例充当真实数据。
**Architecture:** 认证只读 PostgreSQL 一致快照→固定 API→既有简报组件。只聚合已存事实，不运行模型/采集/发送、不新建收费或预计算调度系统。
**Tech Stack:** 现有 FastAPI/PostgreSQL、React/Node24/Zod。

## Global Constraints

- 完整请求/响应严格遵循 docs/UI_OPPORTUNITY_BRIEF_CONTRACT.md 与 desktop/src/renderer/domain/opportunityBrief.ts。身份从已认证 claims 派生并等值核对，scopeVersion=1；画像为本人可访问 CONFIRMED 版本。UUID、业务日、IANA 时区严格校验，非法或未知不能转空成功。只支持请求时区的当前业务日，旧/未来日期明确409而非冒充历史快照。
- 普通 Profile.id/请求 profileId 是数据库 profile_version_id（不是 profile_id 实体ID），同时核对整数 profileVersion；遵循现有 mapProfile 和 P02 请求，不重定义字段。
- 只读、无外部网络、无新表。日期边界按 ZoneInfo 当地日历计算（包含 DST），到期不跨下一业务日且最多5分钟；同一读取时间绑定全部时间字段。会话读取前后重验，数据使用 REPEATABLE READ READ ONLY 与现有 tenant/owner RLS。不得客户端直连数据库。
- contact 只选原 INCLUDE 本人已核验的固定 evidence、有逐字需求依据且当前未排除/关闭/已联系的商机；不得单凭画像匹配或任意source_status造高意向。校验 evidence_view 哈希与对象/画像，当前候选或策略负面变化不能沿用旧推荐。按更新时间稳定排序，同组每商机最多一项。依据指向真实人工纳入/来源核验记录及版本，不虚构核验时刻。
- followup 读取最新 ACTIVE 结构化记录（按创建者归属）；nextFollowupAt 在业务日结束前且状态非LOST/WON，保留逾期；同商机取最新仍有效计划，后续记录清空计划、关闭或撤销不能继续提示旧到期。只有 created/recorded真实记录时间作为登记依据，不能把用户填的未来计划称为核验。旧无owner/计划记录不猜到期。
- changes 没有现成已核验变化事实链则为空，并在 uncheckedScope 明示“原帖需求变化尚未核验”；不能把新增观察、人工跟进、FINISH或摘要差异伪装 VERIFIED_CHANGE。此缺口继续保留完整Goal，不宣称变化监测已交付。
- 覆盖仅报告当前业务日本人该画像已保存任务/原run/window；FINISH不能证明全平台已查完。优先声明 PARTIAL：已查的是“库内已核验机会/有效跟进”，未查真实未覆盖来源、原帖变化。无任何可读事实/任务才NOT_CHECKED。lastCompletedCheckAt只用真实已完成任务时间，无则null；读取生成时间不是搜索完成时间。无真实未匹配通道到期规则，不虚构CHANNEL_FOLLOWUP。
- 每组≤1000、runs≤100；超限明确503，不默默截断报完整。各组total真实数组长度；不合并算新增客户。所有返回sample=false但不能把样例数据转正；不存在/过期对象不能指向另一个商机。错误503/no-store，不泄露SQL/密钥。
- 根只修改共享接线及新增客户端文件；实现者只碰其Task1路径。最小受限PG真实API验证使用合成业务来源，不能管理员制造成功的新业务写入；不重跑旧全套/Windows/构包。最终源码独立审核后normal push main，Goal仍完整V0.2。

## Task 1: 只读后台（独立实现者）

Own新增 `pilot/opportunity_brief.py`, `pilot/opportunity_brief_api.py`, `tests/test_opportunity_brief_service.py`, `tests/test_opportunity_brief_postgres.py`。参考已有 opportunity_research.py、search_coverage.py、followup_service.py，但不改它们或shared runtime/db/web/ui_api/store。

接口 `OpportunityBriefService(database).query(claims, raw)`，返回严格BriefSnapshot；`register_opportunity_brief_api(router, service, identity, require_session_https)`，固定 POST `/opportunity-brief/query`（根router已有/api/ui）。请求≤16KiB，拒绝重复JSON键/未知字段；缺服务501。函数名与签名是Root接线边界。

- [ ] 新增缺服务 RED：实际认证API当前不存在/类缺失。实现请求验证、受限只读一致快照和真实facts投影，不用mock替代PG成功。
- [ ] 定向测试业务日/时区错误、精确身份/画像、跨owner/tenant、空库NOT_CHECKED、人工verified INCLUDE后contact、已有联系/负面结论不重复推荐、到期/未来计划及清空/纠正/撤销/关闭历史、无变化依据明确未核验、无任意读请求写库/模型调用。参考 tests/test_confirmed_strategy_review_postgres.py 与 tests/test_opportunity_evidence_postgres.py 的真实受限fixture。
- [ ] 只运行本片新增测试和py_compile，自查并提交own路径，不amend/push。报告失败→通过、范围及剩余缺口。

## Task 2: 普通客户端及联合接收（Root）

新增 `desktop/src/renderer/services/opportunityBriefClient.ts` 工厂 `createOpportunityBriefService(transport, session)`；shared `opportunityBrief.ts` 只依赖zod的严格wireQuery（UUID、scope=1、合理positiveint）。服务query先验证、当前session等值核对→固定 operation `opportunityBrief.query` POST `/opportunity-brief/query`→再次会话核对→parseOpportunityBrief，传递AbortSignal，不重试、不外发。普通client挂opportunityBrief；main/servicePolicy与shared/contracts注册固定操作（16KiB），不接受任意URL。

Root将新服务接 pilot/runtime.py、web.py、ui_api.py；无迁移。既有P02布局与错误状态复用，不放新TEST数据。

- [ ] 新 `desktop/tests/opportunityBriefClient.test.ts` 先写不存在adapter RED；验证精确固定路由、同query响应、错日期/账户响应拒绝、途中切号/取消、501错误不转空。
- [ ] 一个实际ordinary Node→HTTP→受限PG场景，合成真实纳入→主页query→保存实际跟进→刷新contact移出/followup出现→纠正清空计划→刷新移出，依据记录/版本可回查；已有组件只跑最相关文件，类型检查及至多一次renderer构建。
- [ ] 一次整批独立审核，修复只差量；只本计划记完整证据，契约/任务书短引用。核对main同步，清理本轮资源。真实平台/Windows/生产/跨行业UAT和变化/计量等缺口不隐藏。
