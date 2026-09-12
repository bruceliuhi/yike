# 通用网页需求补证 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. 用户要求压缩重复测试与审核：整批一次独立Spec/Quality审核，问题统一修复后仅差量审核。

**Goal:** 让混合网页不冒充本人意向，且人工补证后真正完成重判与商机导入。

**Architecture:** 新范围投影＋现有不可变来源核验回执扩展＋人工/研究模型路径分离，复用既有UI。原文不改，当前补证进入判断绑定。

**Tech Stack:** Python/Pydantic/FastAPI/PostgreSQL、TypeScript/Zod/React。

## Global Constraints

- 执行[设计](../specs/2026-09-13-page-demand-evidence-design.md)；不发消息、不部署、不重放旧UNKNOWN。
- 同一隔离worktree短期分支，后端任务先实现并固定合同，root并行只准备UI检查与测试，不抢改其文件。
- 用apply_patch；不动共享PG/其他工作；仅owned一次性PG和一次同源候选构包。
- 补证是人工声明，不宣称机器验证日期归属；作者匿名可定位即可。

## Task 1: 服务端范围、补证与完整重判导入

**Files:** `pilot/candidate_assessment_model.py`, `pilot/candidate_review.py`, `pilot/candidate_review_contract.py`, `pilot/candidate_review_api.py`; 必要时抽出 `pilot/candidate_demand_evidence.py` 纯合同/日期/投影工具，及 `pilot/research_assessment.py`/用量接线。只改关联测试：`tests/test_candidate_assessment_model.py`, `tests/test_candidate_review_postgres.py`, 新 `tests/test_candidate_demand_evidence.py`、`tests/test_candidate_demand_evidence_postgres.py`。

**Interface:** Verification可选demandEvidence严格按设计六字段；服务端回执原样留存该对象，checkedBy/At仍服务端产生。新assessment可选 `demandEvidenceId` 表明绑定回执；无补证省略。候选原始publishedAt不改。前端从当前sourceVerification.demandEvidence取得日精度日期；后端仍独立校验。

- [ ] RED：混合scope非UNKNOWN intent引用body拒绝；author_updates本人摘录通过；未知scope拒绝；已结构化旧输入保持。
- [ ] GREEN：扩展两种source_read_scope，按范围计算personal citation集合；保留业务/研究输出，不强制全体观察。
- [ ] RED：补证三种摘录必须原文匹配，OPEN/动态源/合法日历限制；同request重放固定；旧无补证字节不变。
- [ ] GREEN：存不可变回执；在捕获/缓存/披露/结果/列表/INCLUDE使用同一个当前补证选择逻辑，避免状态分叉。快照独立绑定ID/hash，不发给模型。
- [ ] RED：动态run已结束→用户显式新ASSESS可用人工额度完成，不使用研究run新permit；后台原有ASSESS继续研究计量。旧UNKNOWN不可因此重放。
- [ ] GREEN：分清内部调用来源；保持授权、quota与用量生命周期，不开泛化免许可路径。
- [ ] RED：受限PG：未知原始日期混合页→补证→新判断→INCLUDE成功，原文未知日期不变，导入日期和摘录带人工来源；替换同字摘录回执/过期/跨版本/跨用户拒绝旧判断。
- [ ] GREEN：UI所需current demandEvidenceId输出；INCLUDE只消费当前证明和新判断，导入本人摘录/来源依据，不导入整页第三方作为买方发言。
- [ ] 运行上述新测试＋受影响旧组一次；记录初始失败、命令、通过和未验证项。提交自身文件，报告固定最终接口和兼容方案，不改前端或本计划。

## Task 2: 用户补证与可操作闭环（root）

**Files:** `desktop/src/shared/candidateReviewApi.ts`, `desktop/src/renderer/pages/opportunities/CandidateSourceVerification.tsx`, `desktop/src/renderer/pages/Opportunities.tsx`、相关renderer/main服务/候选适配与既有CSS（仅必要行）；`desktop/tests`内对应合同/组件用例。

- [ ] 对齐Task1已固定可选字段；Zod验证六字段/日历/字数/缺省，旧对象通过，新非法拒绝。
- [ ] 表单新增补证区与明确人工归属声明，改动取消确认；显示保存回执/本人摘录/日精度来源与需重判状态，不自动发起判断。
- [ ] 前端INCLUDE门禁选择原始日期或当前人工确认日期，检查assessment.demandEvidenceId与回执id一致、24h有效、匹配binding，仍请求后端最终核验。
- [ ] 旧无补证对象不新增字段；能力/版本不支持时明确提示升级，读回原请求不丢扩展信息。
- [ ] 定向合同/组件测试；浏览器核验长短屏表单、日期错误、切换清空和成功后重判引导。不能用静态截图证明后端导入。

## Task 3: 整批交叉验收与交付

- [ ] 用Task1受限PG真实HTTP响应喂客户端解析器一次，证明同源补证/判断/候选/导入回执可消费；数据是合成反例，模型可边界替代，不称真实线索。
- [ ] 独立审核固定整批diff一次；统一修复material问题，变动覆盖测试后差量review。
- [ ] 必要同源候选构包一次；记录源码与产物对应，不冒充Windows实机或生产。
- [ ] 更新本计划Evidence、任务书当前状态；合并推送main，核对live SHA，清理仅owned PG。

## Evidence

设计和实施准备中，未实现/验收。先前真实原文成功仍绑定bd864f5，不能追认本设计的补证闭环。
