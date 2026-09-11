# 相似研究来源进入确认策略

> 执行：subagent-driven-development。用户已授权V0.2内自主细化；本批完成来源绑定前置，不解除research执行与收费保护。

**Goal:** “多找类似”草稿可完整进入策略PREPARE/CONFIRM/回读，服务端在同事务核验本人原机会、画像、证据及当前认可。
**Architecture:** 扩展现有research可选provenance；复用机会证据及当前认可查询，复用策略快照/摘要/回执。无迁移、无新网络或模型、无启动/发送。
**Tech Stack:** Python/Pydantic/PostgreSQL与既有TypeScript/Zod策略链。

## 共同合同

- provenance可选但显式null非法；旧无字段序列化不增加键，保持旧摘要。coverageProvenance仍拒绝，本批不丢弃后降级。
- provenance精确字段：requestId（UUID）、suggestionId（`suggestion_`+64位小写hex）、userId、opportunityId、profileVersionId、sourceUrl、evidenceVersion、accountScope:{id,version:1}、originalScope、additionalScope。身份字段非空最多512，scope说明可空最多8000，URL遵守既有公开http(s)无凭据规则。sourceUrl最大2048。所有类型严格、拒绝额外字段和控制字符。
- 服务端从真实session取得user/tenant，accountScope必须完全相等，provenance.profileVersionId必须等于新策略画像。复用`_recognized`与`_current_recognition`核验原机会、纳入人、URL、证据版本、当前INCLUDE与24小时内OPEN核验。检查沿调用者事务执行，写路径继承同画像锁（原复核也先取此锁）；不另开快照连接。
- PREPARE、CONFIRM、resolve、read_snapshot都核验；get_strategy和历史receipt仍可回读历史原文，不因来源失效删除历史。source资格失效以`research_origin_unavailable`409报告，resolve对外继续既有strategy_conflict，存储错误仍503。旧无来源策略不访问机会表。
- requestId/suggestionId和scope说明是客户端保留的建议标签，不代表已证明AI生成或采购事实。服务端证明的是原机会/画像/证据的资格，不用这些说明授权执行、评分或收费。需要证明原建议本身时另接服务端建议回执，不能冒称本批已验。
- 不把research字段剥掉启动once；用量与研究启动继续拒绝。新旧解析器须配套升级；无生产规则默认值、無新计费承诺。

## Task 1：后端合同与同事务资格（独立实现）

Files：`pilot/research_strategy_contract.py`、`pilot/research_strategies.py`，必要`pilot/research_origin.py`；`tests/test_research_strategy_contract.py`、新增限定来源测试。不要编辑TS、文档、Git分支或推送。

- [x] 写RED：完整provenance可model_validate/model_dump并进入摘要；缺字段/错scope/null/额外字段拒绝，旧研究序列化不增加provenance。
- [x] 在_Research加入单独严格来源模型与可选字段，并用wrap serializer仅缺值省略。准备/确认/解析/只读投影在已有画像资格检查后调用同一个来源校验函数；函数没有来源时立即返回。
- [x] 测试使用真实受限PG既有include→绑定，不用stub替代服务端证据；正常prepare/confirm/resolve/回读保留全部字段，跨用户/租户/画像/URL/证据拒绝。来源EXCLUDE后旧回执保留、CONFIRM/resolve/read_snapshot不再可用；实际锁路径覆盖写资格，未做独立双线程时序测试。
- [x] 只跑修改所涉合同和上述PG用例，不跑全量。root统一提交并独立整批审核。

## Task 2：客户端草稿到真实策略转换（root）

Files：`desktop/src/shared/researchStrategies.ts`、`desktop/src/renderer/domain/researchStrategies.ts`、`desktop/src/renderer/pages/TaskWizard.tsx`及对应定向tests。

- [x] 写RED：带provenance的正常草稿调用strategyPrepareRequest成功，深拷贝保留全部来源；不匹配画像/缺accountScope/coverageProvenance/无research来源等反例拒绝。缺来源时旧配置字节一致。
- [x] 共享schema加入同合同的严格可选provenance；移除转换函数与TaskWizard对合法provenance的全拒绝，继续拒绝coverageProvenance。公开来源允许准备research意图，但普通采集器仍不得执行research；用共享schema校验来源，不从body片段推断身份证据；策略准备后字段随原摘要/回执传递。
- [x] 跑researchStrategies与来源相关定向Vitest+tsc；连同后端的独立整批审核见完成记录，不改研究执行保护、不构包或实网。

## 完成标准

本批来源绑定技术链可验收并记录拒绝/历史边界，不标完整R4、研究执行或Goal完成。后续继续按上层设计接可信quote、原子START、资源事件、结算和实际跨行业验证。

## 实施证据

- 后端先验RED：合同1失败/8通过；真实数据库首次未配置而7项跳过，不计通过。随后专用tmpfs PostgreSQL及既有受限应用角色下，`pytest -q tests/test_research_origin_postgres.py` 8通过；`pytest -q tests/test_research_strategy_contract.py` 205通过，py_compile和diff检查通过。来源为合成测试数据，非实网或真实采购验证；覆盖同cursor画像锁路径，但未额外做双线程时序测试。
- 同requestId的有来源PREPARE/CONFIRM重放也重新核验来源，历史GET保留原回执。旧无来源策略不访问机会表、序列化不增加键。未构包、未部署、未调用模型；后续仍缺可信估算、原子启动与实际计量。
- 客户端先验RED：来源转换2失败/18通过；TaskWizard来源准备按钮1失败；公开来源research转换另1失败。对应最小修改后4文件50项通过及tsc通过。测试覆盖真正的草稿→PREPARE→receipt与普通TaskWizard确认，不只用现成策略fixture；公开research准备不授权普通desktopStart执行，coverage补查仍拒绝。
- 测试文件：`researchStrategies.test.ts`、`ui/strategy-confirmation.test.tsx`、`monitorCollectionDomain.test.ts`、`publicCollectionRenderer.test.ts`。以上为JS/模拟UI证据，不证明后端、平台、模型或Windows成功。
