# 行业策略进入任务快照 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development。执行已批准 V02-04/05 可纠正行业策略与 R3 搜索条件/最终确认，不新增页面或产品范围。

**Goal:** 将建议中的内容方向、意向信号及反例显式采用、编辑并绑定最终任务策略；不再只保存在模型回执中。

**Architecture:** 复用 TaskDraft、ResearchStrategyConfiguration、原准备/确认/恢复协议；配置新增可选 industryStrategy，旧配置不增加null或改变摘要。它是用户任务意图，不是模型认证事实或执行权限。模型原始依据仍在原回执，本配置不冒充来源认证。候选模型实际消费留下一批接续，当前页面明确未用于自动评分/内容筛选。

**Tech Stack:** React/Zod、Pydantic、既有PostgreSQL策略快照。

## Global Constraints

- “行业模板不是允许名单”；用户可编辑信号，不引入行业准入列表。
- “不能自动增加连接平台、监控频率或费用预算”。配置不是买方证据、平台能力、触达批准。
- 已有人工策略不被新建议覆盖；明确清除后可重新采用。切换画像保留旧策略但阻止准备，须明确按当前画像确认或移除。
- 无新增真实模型/平台调用、发送、数据库迁移或角色授权；受信配置进入既有不可变摘要、确认失效与恢复流程。
- 每批只做变更定向RED/GREEN、一次独立整批审核；不全量测试或构包，不把技术快照绑定称为真实平台/客户效果。

### Task 1: 后端最终配置兼容（独立实现）

**Files:** pilot/research_strategy_contract.py；tests/test_industry_task_strategy.py。只改这两个文件。

**Interfaces:** 配置可选 industryStrategy；存在时必须是以下完整严格对象，不接受null、额外权限键或未知版本：
```json
{"version":"industry-task-strategy-v1","sourceTypes":["SOCIAL_POST","COMMENT"],"intentSignals":["正在寻找供应商"],"counterSignals":["同行广告"]}
```
sourceTypes为1–5个不重复枚举SOCIAL_POST/COMMENT/PROCUREMENT/COMPANY_UPDATE/INDUSTRY_SITE；intentSignals为1–5条、counterSignals为0–5条，每条1–160字符、现有Unicode限制、规范化空白大小写去重但不改值。行业解释角色/依据仍由画像/原建议提供，不伪称任务条件就是采购事实。

- [ ] RED：新配置能经过PrepareStrategyRequest→strategy_snapshot→configuration_digest；缺席旧配置保持原字节/摘要；null/重复/额外权限拒绝；变更信号改变摘要。断言新配置在旧实现被extra拒绝。
- [ ] 复用当前_Schedule联合类型的兼容办法：保留旧ResearchStrategyConfiguration，新增带必填industryStrategy的子类，_StrategyScope.configuration使用新子类|旧类；不要给旧模型增加隐式None或绕过_raw_fields严格校验。新对象复用_Frozen、_visible_text、_term_key等边界。
- [ ] 增一个真实受限本地PG流程：复用test_material_profile_strategy的env/authority/ready_strategy，prepare含新配置→confirm→resolve配置字段仍在；修改配置同draft高revision导致旧策略不能新resolve，历史回执保留。可用自有临时PG、只操作自有container，不触碰共享PG。不调用外部服务。
- [ ] 只跑本新增测试和旧配置摘要/结构相关定向用例；报告RED/GREEN与证据范围，提交自己两文件，不push/amend。

### Task 2: 原客户端显式采用、编辑与快照（root）

**Files:** shared/industryTaskStrategy.ts、shared/researchStrategies.ts；renderer/domain/models.ts、industryTaskStrategy.ts、researchStrategies.ts、task.ts；renderer/app/taskDraft.ts；renderer/pages/TaskWizard.tsx、tasks/SearchSuggestionPanel.tsx、IndustryTaskStrategyEditor.tsx、StrategySnapshotDetails.tsx；tests/ui/industry-task-strategy.test.tsx。

**Interfaces:** shared行业类型与Task1 JSON一致；TaskDraft可选industryStrategy:{profileId:string,configuration:IndustryTaskStrategy}，profileId是画像版本ID。最终prepare.configuration仅发configuration内容（外层已有当前profile_version_id）；本地profileId不作为服务端新身份输入。
```ts
// 显式采用后保留现有策略，不由新建议静默覆盖。
if (draft.industryStrategy || receipt.profile_version_id !== draft.profileId) return draft;
// strategyPrepareRequest/任务错误对旧画像绑定fail closed。
if (draft.industryStrategy?.profileId !== draft.profileId) throw new Error('请核对当前画像的行业策略');
```
- [ ] RED：采用不改变词项/平台/预算且保留人工策略；编辑/移除改变fingerprint；本地持久化往返；切画像阻止准备；prepare与快照展示包含最终编辑值，旧配置缺席不新增字段。
- [ ] 原建议弹窗新增“采用任务策略”按钮，经现有getReceipt重新校验/currentBinding后调用独立onApplyStrategy，保留原回执以便仍能采用词；已有策略不替换。原词项采用按钮逻辑保持，只说明该按钮只作用词项。
- [ ] 原P06/P20表单新增简洁策略编辑区（复用Field/Button/Notice）：无策略可手填；有策略用checkbox选择内容类型、每行一条信号/反例，人工编辑即时持久化，显示超限/无效；明确移除；旧画像显示“按当前画像确认”动作。不使用新弹窗或导航，不生成图片。角色/预算/采购真实性不由这些条件推断。
- [ ] strategyPrepareRequest条件性写入新字段、验证本地绑定；taskErrors及fingerprint涵盖配置，旧确认自然失效；StrategySnapshotDetails展示服务端最终条件并注明尚未用于自动评分/筛选。原手动配置可以不使用行业策略。
- [ ] 定向测试+一次typecheck；完成后对Task1+Task2一次独立整批审核，更新单一证据和任务入口，正常push main。

## 实施与验证

基线cf1f912。本批执行中；不关闭完整V02或父卡，候选判断实际消费、真实平台质量、Windows/生产/UAT继续独立验收。
