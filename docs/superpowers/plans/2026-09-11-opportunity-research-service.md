# 机会研究只读服务与多找类似 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development。步骤按变更风险定向验证，整批独立审核，不重复全量测试。

**Goal:** 将已批准R4的机会分类、同来源版本证据和多找类似草稿接到真实服务；补齐首发亮点，不改变完整V0.2目标。

**Architecture:** 复用现有机会、候选版本/观察/判断/复核、确认画像/策略和跟进台账，新增只读投影服务与固定HTTP操作。类似建议从该机会已确认策略与原文证据确定性派生，不调用模型、不采集、不扣费；采用仍走既有本机草稿和最终策略确认。

**Tech Stack:** Python/FastAPI/PostgreSQL；TypeScript/Zod/现有Electron IPC与React页面。

## Global Constraints

- 基线 `67dda24521aa1d2a0e9e3237bc1f6a8da5fe5441`；既有隔离工作树，保护其它工作树。设计依据 `docs/UI_OPPORTUNITY_RESEARCH_CONTRACT.md` 与现有 `desktop/src/renderer/domain/opportunityResearch.ts`，输出精确匹配已批准DTO。
- 所有读请求由真实session派生tenant/owner；客户端binding/accountScope只核对不授权。同一返回值在同一只读一致快照事务内读取，最多1000记录，超限明确报错，不截断冒充完整。
- 分类必须来自已有判断/人工复核，不从关键词猜采购；原文缺证据保留UNASSESSED/缺口，不能编造认可、来源版本、预算、费用或成交。原有客户商机不得因新服务启用被隐藏；同画像同来源去重不得静默丢不同评论。
- 时间线只拼同来源真实版本，当前机会固定证据为锚；后续未复核内容不能悄悄替换认可证据。来源访问失败不等于关闭；人工跟进不等于平台回流；超过合同上限明确报错。
- similar为只读预览，稳定suggestionId绑定原requestId及真实语义；每次重读当前画像/来源/认可/策略/能力，变化则拒绝旧绑定或eligible=false，不执行模型/任务/消息。关键词引用已确认策略或有证据的原词，不编词；usage UNKNOWN明确未计量。当前策略无可用平台/缺旧资料时明确不可用，不宣称五平台均支持。
- 不新增写库/迁移/收费/自动发送；无法由既有证据满足的字段要明确报错或缺口，不能用合成值上线。测试fixture不是实际平台/模型/Windows/生产证据。

### Task 1: 后端只读投影和API（独立实现agent）

**Files:** 新增 `pilot/opportunity_research.py`、`pilot/opportunity_research_api.py` 和专项 `tests/test_opportunity_research*.py`；只改这些文件。根负责共享ui_api注册与desktop，不占用其文件。

**Interfaces:** `OpportunityResearchService(store, *, supported_platforms)`，方法 `list(claims)`, `timeline(claims,binding)`, `similar(claims,binding,request_id)` 返回现有camelCase DTO。`register_opportunity_research_api(router, service, identity, require_session_https)` 注册 GET `/opportunity-research`、POST `/opportunity-research/timeline`（body `{binding}`）、POST `/opportunity-research/similar`（body `{binding,requestId}`）；POST只是有界只读请求。错误使用稳定code/status且不含客户原文，读响应no-store。服务初始化只保留依赖，不调用数据库或外部服务。

- [ ] 先写缺实现的定向测试，覆盖真实数据库里的认可/未分类、相同原文不同评论、租户/owner隔离、绑定过期、source/profile变更、原认可撤销、原策略/平台不可用、超限及不写库。
- [ ] 最小实现，以 `pilot/store.py` / `candidate_review.py` / `opportunity_evidence.py` / `research_strategies.py` 实际schema为准；不要另建事实表。已迁入旧机会缺不可变原文时仍可列出为未分类，但类似/时间线不可伪造证据；必要合同冲突先报告根而非塞假字段。
- [ ] 类似建议须真实限定范围（业务/来源/服务），不是原始条件改名。只从已确认策略与对应来源引用提取可解释词项，保留原排除词；不能隐含扩大预算/平台。缺足够依据明确不可用。
- [ ] 用现有隔离PG fixture跑新增专项，不跑全量；报告精确命令/结果、实际假边界、未覆盖项。可以用极少量API单测验证格式/错误，根另做真实共享接线与客户端。
- [ ] 串行提交：仅自己文件，先与根协调commit窗口。私有报告放git-dir/sdd/opportunity-research-backend-report.md，不把报告放产品目录。

### Task 2: 原生固定路由与现有页面接线（根）

**Files:** `pilot/ui_api.py`；`desktop/src/shared/contracts.ts`、新增`desktop/src/shared/opportunityResearchApi.ts`；`desktop/src/main/servicePolicy.ts`；`desktop/src/renderer/services/opportunityResearch.ts`、`client.ts`；对应定向测试。

- [ ] 新增三固定operation `research.list/research.timeline/research.similar`；strict binding schema、固定path、正文上限、无任意URL/SQL/tenant选择。
- [ ] 注册后端只读服务，supported_platforms来自当前collection policy，不硬编码全部平台开启。service原list/timeline/similar适配接现有解析器；失败不转空集合、Abort与身份变化保留原UI防护。
- [ ] 客户端请求协议通过定向测试；现有类似草稿/详情/列表组件测试复用，若有新接线失败只修真实差异，不重写页面或降低绑定检查。
- [ ] 运行新增后端场景、受影响TS文件、tsc及一次renderer构建；数据源保持合成、无真实外发。整批独立代码/架构/质量审核；修复只差量复查。
- [ ] 更新任务书/整合状态链接与本计划证据，正常推送main并核对SHA；完整Goal及平台/Windows/部署/UAT仍未完成。
