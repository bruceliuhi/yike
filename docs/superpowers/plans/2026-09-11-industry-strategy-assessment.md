# 行业策略实际用于候选判断 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development；执行已批准V02-04/05下一链，采用既有任务、候选、确认与模型边界。

**Goal:** 候选模型实际接收该候选所属已确认任务的行业规则，并保持原文证据、确认权限与历史结果边界。

**Architecture:** CandidateReviewStore已有服务端解析/摘要比对/预留前后复核及快照缓存键；从这个快照中读取configuration.industryStrategy，作为独立的industry_strategy输入传入真实模型适配器及固定子进程。无规则旧任务保持旧输入形状；不拼入description/content、不增加证据字段或由客户端声明规则。

**Tech Stack:** Python/httpx/固定worker、PostgreSQL、现有React页面。

## Global Constraints

- 策略是用户已确认的研究意图，不是采购事实，不扩大来源、发送权限或预算。
- 仅服务端验证过的当前候选绑定快照可作为策略输入，客户端ASSESS协议不得增加策略字段。
- “intent 和 urgency 的非 UNKNOWN 判断至少有当前 title/body 引用”，策略不能替代原文证据；缺证保留UNKNOWN/REVIEW。
- 不跨模型网络持有数据库事务；原缓存、未知结果、撤销/画像/策略版本重查继续适用。输入深拷贝，模型不能修改服务端快照。
- 无新真实provider调用、平台/发送、迁移/授权或构包；用户要求省token，只变更定向测试与一次独立审核。

### Task 1: 服务端到实际模型/worker（独立实现）

**Files:** pilot/candidate_review.py、candidate_assessment_model.py、candidate_assessment_worker.py；pilot/research_strategy_contract.py（只将_IndustryTaskStrategy公开命名为IndustryTaskStrategy复用）；tests/test_industry_strategy_assessment.py；tests/test_candidate_assessment_model.py（仅实际受影响规则版本期望）。

**Interfaces:**
```python
def assess(self, *, description: str, content: dict, industry_strategy: dict | None = None): ...
industry_strategy_version = 'industry-task-strategy-v1' # 当前适配器声明其理解能力
rule_version = 'candidate-assessment-v1/ai-project-lead-research-1.0.0/industry-task-strategy-v1'
```
strategy内容严格复用已存在的IndustryTaskStrategy格式（version/sourceTypes/intentSignals/counterSignals），不要再定义平行宽松schema。模型输入新键为industry_strategy；仅存在有效策略时加，旧无策略不发null。固定worker允许旧精确键集合或加一个industry_strategy键；未知/空null/无效策略在网络前拒绝。HTTP用户消息中的行业策略是分析条件而非指令，结果的引用field枚举不变。

- [ ] RED：当前实际httpx适配器接industry_strategy失败；增加受控localhost HTTP+真实worker一例，确认wire字段真实传过子进程；原文字段原样、信号不进evidence来源。测试无规则legacyexact shape、非法额外权限网络前拒绝、伪造strategy引用拒绝。
- [ ] 模型的公开/私有process/child链传递独立最小策略并深拷贝；更新固定合同：比较来源与意向信号/反例、说明匹配与反证，不把规则转为来源事实、不自动丢弃内容、不授权发送。更新rule_version及原对应单项测试；rule_sha由新合同自动绑定，不改旧回执。
- [ ] CandidateReviewStore从snapshot['strategy']['configuration']读取规则；在预留额度/模型前验证且核对模型industry_strategy_version支持（不支持时assessment_unavailable，不能悄悄忽略或用TypeError变成UNKNOWN）；仅有策略时额外kwargs，旧边界模型调用兼容；返回评估校验仍只description/content，保持服务端策略与模型缓存键。
- [ ] 受限自有PG定向：真实候选快照带策略→边界模型收到精确规则和原文，客户端伪造规则拒绝；模型修改收到dict不影响服务端记录；无能力模型在调用/预留前拒绝。可复用test_candidate_review_postgres fixtures，但规则解析器fixture属合成边界须如实写。另用真实适配器/worker测试证明传输，不冒充模型语义质量。
- [ ] 新增文件定向+受影响旧规则/old input精确用例，py_compile/diff；一份短报告、只提交自己文件，不push/amend。不改root前端文件。自有PG结束时清理，不能碰共享PG。

### Task 2: 客户端使用说明（root）

**Files:** desktop/src/renderer/pages/Opportunities.tsx、tasks/IndustryTaskStrategyEditor.tsx、tasks/StrategySnapshotDetails.tsx；desktop/tests/ui/industry-task-strategy.test.tsx（更新状态期望）、candidate-live-review.test.tsx（原不隐式调用用例补披露断言）；复用页面，不新增组件。

- [ ] 候选判断按钮附近说明：点击会把当前候选所属任务已确认的行业规则（如有）、画像和候选原文发给配置模型；不会自动联系。重试仍沿用原确认/核对链，不新增自动分析。
- [ ] 行业编辑/快照说明改为“发起候选AI判断时作为研究条件使用，不自动过滤采集内容”；不能说已有线索提升或每条旧历史结果已用新策略。
- [ ] 定向UI文案与原策略测试；整批一次独立审核后集中版本证据、更新任务入口并正常push main。实际模型语义质量与平台/Windows/生产/UAT仍未完成。

## 实施与验证

基线db7c3dc；本批执行中，不改变完整V02完成标准。
