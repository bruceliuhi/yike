# 作者更新普通链路验证

**Goal:** 验证已实现作者源通过普通确认、签名上传、HTTP原文回读与客户端严格解析；不把单层测试当完整链路。
**Architecture:** 复用已有 `tests/test_public_community_http_postgres.py` 和 `desktop/tests/integration/public-community-live.test.ts`；仅扩显式测试来源，不改产品权限或生产配置。设计沿用 `2026-09-11-public-author-context-design.md`，已获范围内自行细化授权。
**Tech Stack:** 既有Python/Uvicorn/隔离PG、Node24/TypeScript客户端。

按 brainstorming/writing-plans 收敛：不新建另一测试框架，不直接管理员导入；选择现有实际HTTP链，因为前轮PG未用实际客户端schema重验导致遗漏nullable回归。本片只补跨边界验证，模型效果后续单独记录，不做新模型接口。

- [ ] 新source参数采用新mode、最多3篇，合成fetch提供分开的topic和作者reply；断言固定总请求数/回复保留/无重复采集。
- [ ] 原文回读调用 `parseRawCandidateEvidence`，逐条对照source_context，不只检查几个主帖字段；输出只留sourceID、回复数量等元数据，不输出正文/凭据。
- [ ] 默认合成新source一次实际HTTP/PG客户端链；非零样本才有链路结论。任何缺陷先保留失败，再最小修复。
- [ ] `YIKE_PUBLIC_COMMUNITY_NETWORK=1` 仅新source一次真实读取，不重试失败或为凑量补读；最多3篇/4GET。零结果记不充分，不宣布商机或链路通过。
- [ ] 独立审核固定提交；合主线但不部署/构包/外发。保留实际账号、OS密钥库、Windows、客户价值的未验边界。

命令：`pytest -q -s tests/test_public_community_http_postgres.py -k outsourcing`，仅显式本机专用 `/yike_public_flow` 数据库，子进程不得携带数据库环境。真实读取增加NETWORK=1，其余合同不变。不得重跑旧latest/qna实网。新增断言代码核心：`expect(content.source_context).toEqual(record.source_context)` 和 `parseRawCandidateEvidence(response.data, expected)`；三源能力目录与服务器真实结果一致。
