# 公开作者来源到普通客户端判断回读

**Goal:** 让同一次授权采集的原文经普通客户端ASSESS、正式worker与受限PG持久化后由严格客户端合同回读，而不是拼接两份独立证据。
**Architecture:** 扩展既有public-community HTTP集成入口，增加显式opt-in判断模式；默认不调模型。fixture模式用本地HTTP provider排查连接，network模式仅允许既有作者来源、明确来源ID和部署式模型环境。只发一次ASSESS，随后GET恢复和列表回读；无自动重试/纳入/核验声明/外发。
**Tech Stack:** 既有Node24客户端service/controller、Python runtime/worker、隔离受限PostgreSQL。

本方案在用户2026-09-11已批准V0.2内自主细化。选择扩展现有链路，不复制独立模型脚本；直接操作生产客户账号会混入真实数据与审批，此轮不用。仍不代表Electron窗口、HTTPS生产、真实客户或Windows验收。

- [ ] `tests/test_public_community_http_postgres.py` 增加 `YIKE_PUBLIC_COMMUNITY_ASSESSMENT=fixture|network`，严格限制authors源；network要求显式来源ID、NETWORK=1及完整模型配置。测试画像经已有存储确认，模型密钥只给Python runtime，不给Node。
- [ ] `desktop/tests/integration/public-community-live.test.ts` 使用正式 `createCandidateReviewService`，从上传结果选择指定原文，最多一次ASSESS；按当前binding回读请求和列表，断言尚未人工核验/纳入，摘要只记录ID、枚举及用量，不输出原文或联系方式。
- [ ] 先一次本地provider全链验证，若暴露真实bug先RED再最小修复；再明确有界实网一次，找不到指定原文/未知结果即记录失败，不循环重试或换题制造通过。
- [ ] 核实assessment行与原候选版本/画像绑定、零商机/零人工核验、provider用量，做一次整批独立审核后合main。记录fixture/实网分母，完整Goal继续。

运行选择为 `pytest -q -s tests/test_public_community_http_postgres.py -k outsourcing`。只有专用loopback `/yike_public_flow` 库可运行。真实调用选择已知来源1240655用于连接验收，不计新增机会；开发画像不声称已具备该项目要求的作品。数据库与账号为隔离fixture，验证结束清理此fixture，不影响生产客户。
