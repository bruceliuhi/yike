# 公开作者来源到普通客户端判断回读

**Goal:** 让同一次授权采集的原文经普通客户端ASSESS、正式worker与受限PG持久化后由严格客户端合同回读，而不是拼接两份独立证据。
**Architecture:** 扩展既有public-community HTTP集成入口，增加显式opt-in判断模式；默认不调模型。fixture模式用本地HTTP provider排查连接，network模式仅允许既有作者来源、明确来源ID和部署式模型环境。只发一次ASSESS，随后GET恢复和列表回读；无自动重试/纳入/核验声明/外发。
**Tech Stack:** 既有Node24客户端service/controller、Python runtime/worker、隔离受限PostgreSQL。

本方案在用户2026-09-11已批准V0.2内自主细化。选择扩展现有链路，不复制独立模型脚本；直接操作生产客户账号会混入真实数据与审批，此轮不用。仍不代表Electron窗口、HTTPS生产、真实客户或Windows验收。

- [x] `tests/test_public_community_http_postgres.py` 增加 `YIKE_PUBLIC_COMMUNITY_ASSESSMENT=fixture|network`，严格限制authors源；network要求显式来源ID、NETWORK=1及完整模型配置。测试画像经已有存储确认，模型密钥只给Python runtime，不给Node。
- [x] `desktop/tests/integration/public-community-live.test.ts` 使用正式 `createCandidateReviewService`，从上传结果选择指定原文，最多一次ASSESS；按当前binding回读请求和列表，断言尚未人工核验/纳入，摘要只记录ID及枚举，不输出原文或联系方式。当前普通判断store不持久化provider用量，本轮未取得实际token数，不伪造。
- [x] 先一次本地provider全链验证，再明确有界实网一次；失败后本地复现、修复并限定验证，不循环实网重试或换题制造通过。
- [x] 核实assessment行与原候选版本/画像绑定、零商机/零人工核验，完成整批独立审核后按批准流程合main。记录fixture/实网分母，完整Goal继续。

运行选择为 `pytest -q -s tests/test_public_community_http_postgres.py -k outsourcing`。只有专用loopback `/yike_public_flow` 库可运行。真实调用选择已知来源1240655用于连接验收，不计新增机会；开发画像不声称已具备该项目要求的作品。数据库与账号为隔离fixture，验证结束清理此fixture，不影响生产客户。

## 实施与失败驱动修复

`aeba5d6` 扩展测试入口。首次本地provider：1 passed / 3 deselected，6.68秒；同一合成原文两次采集任务、一次ASSESS，固定来源/版本复用。不是两次模型或真实商机。

2026-09-12 17:26实网一次：指定1240655确已在当次真实采集结果中，客户端发出ASSESS，但请求返回前报NETWORK_ERROR，1 failed / 3 deselected，27.34秒；Node内层15.90秒含先前采集。当时测试transport丢失底层ApiResult错误码，不能倒填为已观测SERVICE_TIMEOUT，也未得到实际模型决策/用量。没有重试或宣称完整链通过。原输出只保存仓外0600文件，不入仓密钥/原文。

根因调查发现确定的预算冲突：`servicePolicy.ts` 的普通 `candidates.review` 未配置超时，`serviceClient.ts` 12秒默认值早于正式模型30秒默认/60秒最大时限；服务端同步等待模型与PG提交才响应。独立审核给首批NO-GO。最小修复 `fb28f4b` 仅给ASSESS已有75秒预算，覆盖模型及提交且低于review 90秒期限，INCLUDE/EXCLUDE和GET不变；不自动重试、不修改模型或权限。该冲突与本次实网现象吻合，本次原始底层错误仍不可追认。

- 新增假时钟验证：先纠正测试helper命名错误，再RED 2 failed / 10 passed（20秒响应被提前中断，75秒边界提前结束）；修复后整个 `serviceClient.test.ts` 12 passed，类型检查通过。包括20秒响应成功、75秒仍截止、人工INCLUDE及回执GET仍12秒，每项仅一次fetch。
- 同一正式HTTP/runtime/worker/受限PG链，合成provider实际延迟13秒：1 passed / 3 deselected，19.40秒。一次ASSESS后严格parser成功、同请求GET回读相等、列表同assessment且未过期；零人工review/verification/opportunity。不是假时钟集成、不是窗口操作，也不是新的实网成功。
- 错误诊断仅保留安全ApiResult code/status，不输出响应正文。模型密钥只进Python运行环境，Node仍是系统变量白名单与隔离测试会话；不把API调用计作用户批准。

此次真实来源＋模型整链尚未通过；下一次有计划的客户端实测需包含该超时修复。无需为测试文件或文档重构服务镜像，Windows旧a56aab2安装验收不能覆盖新客户端字节。普通判断用量未落库是仍需处理的计量缺口，不修改收费规则或把调用次数换成搜贝。本批无部署/构包/外发，完整Goal保持ACTIVE。

独立审核 `author_context_review` 对修复SHA `fb28f4b292d10bf9601a4e3435e864a360a6cc9a` 给GO，无剩余P1/P2；首批NO-GO及实网失败保留。审核另指出测试本身45秒总期限无法覆盖来源20秒＋模型30秒，已仅将opt-in判断测试外层提升为120秒、Python父进程150秒；普通无模型入口保持45/90秒。不改变任何生产权限/模型预算/重试，也不为调整测试等待上限再次消费实网。
