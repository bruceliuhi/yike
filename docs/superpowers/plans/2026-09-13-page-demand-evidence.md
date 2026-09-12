# 通用网页需求补证 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. 用户要求压缩重复测试与审核：整批一次独立Spec/Quality审核，问题统一修复后仅差量审核。

**Goal:** 让混合网页不冒充本人意向，且人工补证后真正完成重判与商机导入。

**Architecture:** 新范围投影＋现有不可变来源核验回执扩展＋人工/研究模型路径分离，复用既有UI。原文不改，当前补证进入判断绑定。

**Tech Stack:** Python/Pydantic/FastAPI/PostgreSQL、TypeScript/Zod/React。

## Global Constraints

- 执行[设计](../specs/2026-09-13-page-demand-evidence-design.md)；不发消息、不部署、不重放旧UNKNOWN。
- 同一隔离worktree短期分支，后端任务先实现并固定合同，root并行只准备UI检查与测试，不抢改其文件。
- 用apply_patch；不动共享PG/其他工作；仅owned一次性PG和必要renderer构建（审核修复后仅差量重构）。无原生安装改动，本批不重打发行包，发行包留同版本上线验收批次。
- 补证是人工声明，不宣称机器验证日期归属；作者匿名可定位即可。

## Task 1: 服务端范围、补证与完整重判导入

**Files:** `pilot/candidate_assessment_model.py`, `pilot/candidate_review.py`, `pilot/candidate_review_contract.py`, `pilot/candidate_review_api.py`; 必要时抽出 `pilot/candidate_demand_evidence.py` 纯合同/日期/投影工具，及 `pilot/research_assessment.py`/用量接线。只改关联测试：`tests/test_candidate_assessment_model.py`, `tests/test_candidate_review_postgres.py`, 新 `tests/test_candidate_demand_evidence.py`、`tests/test_candidate_demand_evidence_postgres.py`。

**Interface:** Verification可选demandEvidence严格按设计六字段；服务端回执原样留存该对象，checkedBy/At仍服务端产生。新assessment可选 `demandEvidenceId` 表明绑定回执；无补证省略。候选原始publishedAt不改。前端从当前sourceVerification.demandEvidence取得日精度日期；后端仍独立校验。

- [x] RED：混合scope非UNKNOWN intent引用body拒绝；author_updates本人摘录通过；未知scope拒绝；已结构化旧输入保持。
- [x] GREEN：扩展两种source_read_scope，按范围计算personal citation集合；保留业务/研究输出，不强制全体观察。
- [x] RED：补证三种摘录必须原文匹配，OPEN/动态源/合法日历限制；同request重放固定；旧无补证字节不变。
- [x] GREEN：存不可变回执；在捕获/缓存/披露/结果/列表/INCLUDE使用同一个当前补证选择逻辑，避免状态分叉。快照独立绑定ID/hash，不发给模型。
- [x] RED：动态run已结束→用户显式新ASSESS可用人工额度完成，不使用研究run新permit；后台原有ASSESS继续研究计量。旧UNKNOWN不可因此重放。
- [x] GREEN：分清内部调用来源；保持授权、quota与用量生命周期，不开泛化免许可路径。
- [x] RED：受限PG：未知原始日期混合页→补证→新判断→INCLUDE成功，原文未知日期不变，导入日期和摘录带人工来源；替换同字摘录回执/过期/跨版本/跨用户拒绝旧判断。
- [x] GREEN：UI所需current demandEvidenceId输出；INCLUDE只消费当前证明和新判断，导入本人摘录/来源依据，不导入整页第三方作为买方发言。
- [x] 运行上述新测试＋受影响旧组一次；记录初始失败、命令、通过和未验证项。提交自身文件，报告固定最终接口和兼容方案，不改前端或本计划。

## Task 2: 用户补证与可操作闭环（root）

**Files:** `desktop/src/shared/candidateReviewApi.ts`, `desktop/src/renderer/pages/opportunities/CandidateSourceVerification.tsx`, `desktop/src/renderer/pages/Opportunities.tsx`、相关renderer/main服务/候选适配与既有CSS（仅必要行）；`desktop/tests`内对应合同/组件用例。

- [x] 对齐Task1已固定可选字段；Zod验证六字段/日历/字数/缺省，旧对象通过，新非法拒绝。
- [x] 表单新增补证区与明确人工归属声明，改动取消确认；显示保存回执/本人摘录/日精度来源与需重判状态，不自动发起判断。
- [x] 前端INCLUDE门禁选择原始日期或当前人工确认日期，检查assessment.demandEvidenceId与回执id一致、24h有效、匹配binding，仍请求后端最终核验。
- [x] 旧无补证对象不新增字段；能力/版本不支持时明确提示升级，读回原请求不丢扩展信息。
- [x] 定向合同/组件测试覆盖日期错误与切换清空；隔离Chrome核验1366×900及860×600表单、编辑取消确认、保存后显式重判。不能用静态截图证明后端导入。

## Task 3: 整批交叉验收与交付

- [x] 用Task1受限PG真实HTTP响应喂客户端解析器一次，证明同源补证/判断/候选/导入回执可消费；数据是合成反例，模型可边界替代，不称真实线索。
- [x] 独立审核固定整批diff一次；统一修复material问题，变动覆盖测试后差量review。
- [x] 必要renderer构建；初次77c080f相关产品源及审核修复后的c770137分别通过，不冒充发行包、Windows实机或生产。
- [ ] 更新本计划Evidence、任务书当前状态；合并推送main，核对live SHA，清理仅owned PG。

## Evidence

实现固定：服务端 `591ba87`，实际策略UUID的HTTP测试修正 `008be5d`，客户端与隔离验收入口 `77c080f`，审核反例实际HTTP捕获 `a044f8b`，客户端修复 `c770137`。独立首审两项P2已合批修复；独立差量审核绑定 `c7701372675d519939d160cf882f136573772057`，**Spec PASS / Quality PASS / Ready to merge YES**。先前真实原文成功仍绑定bd864f5，不能追认本设计的实网效果。

### 接口与实施

- 人工研究源重判使用 `sourceResearch` 保留来源，`humanResearchAssessment` 标记普通用量路径；原研究执行仍使用 `research` 与permit。没有迁移、放宽用量SQL门禁或恢复结束run。
- 新客户端候选列表/原请求/重判/核验及商机详情都显式 `evidenceVersion=1`；旧候选读回省略扩展字段。带人工证明的商机旧详情请求返回409 `client_upgrade_required`，不抹掉快照或改原始日期。
- 商机证据原body/published_at保留，`HUMAN_CONFIRMED_EXCERPT` 配合唯一本人摘录；核验保留六字段、回执ID及服务端确认人。个人本地Skill未修改。

### 验证（均为合成来源/模型边界，数据库与HTTP为真实受限PG）

- 服务端初始RED包括范围误归属、补证缺省、旧HTTP形状、普通用量被研究字段拦截、撤回复用旧缓存，均修正。8文件定向回归 **350 passed / 1 failed**；唯一旧rule_version断言随合同升级修正，差量 **3 passed**。不重复全套、不累计重叠数量。
- 命令：`.venv/bin/python -m pytest tests/test_candidate_demand_evidence.py tests/test_candidate_demand_evidence_postgres.py tests/test_candidate_assessment_model.py tests/test_candidate_review_postgres.py tests/test_candidate_review_api.py tests/test_opportunity_evidence.py tests/test_opportunity_evidence_postgres.py tests/test_research_assessment_postgres.py -q`。使用独立postgres:16-alpine、loopback55442、fixture受限角色，不用共享库。
- `test_finished_dynamic_research_human_assessment_uses_manual_usage_not_permit`：真实READ/publish→签名CANCEL终态→人工补证/重判/INCLUDE，只有原研究permit，人工独立DISPATCH/FINISH 3tokens。不是自然调度COMPLETED或真实模型证据。
- 客户端10文件定向回归 **304 passed / 2 failed**，两个旧机会URL断言修为显式版本协商后`tests/ui/client.test.ts` **38 passed**。此前动态UI闭环暴露并修正恢复摘要漏demandEvidence，动态用例1通过，requestOperation56通过。
- 前后端原样wire交叉读首次发现测试策略ID不是UUID，修正为真实持久化journal策略并单HTTP测试1通过；`YIKE_DEMAND_WIRE_PATH=/tmp/yike-page-demand-wire.json npm --prefix desktop test -- tests/candidateDemandWire.test.ts` **1 passed**。未修改回执字段来迁就解析；无该环境变量时该用例跳过，不计集成通过。
- `npm --prefix desktop run build` 类型检查与生产renderer通过（既有>500kB chunk警告）；无安装包构建/安装。后加隔离动态夹具 `tests/visual/candidate-review.test.ts` **7 passed**，typecheck再次通过。
- 可复现隔离UI：`desktop`下启动`vite --config vite.visual.config.ts`，进入`?scenario=P07&candidateReview=dynamic`。只有TEST内存；真实Chrome1366×900和860×600填写补证、编辑清除确认、保存后入库仍禁用、显式重判后放开；窄屏表单353px无横向溢出。首个脚本因填入相同值未触发change而断言失败，改为真正变更字段后通过，不是产品修复。

未验证：新版本实网研究/模型质量、授权评论深读、更多高质量线索、发送/回复、发行包/生产部署及客户UAT。下一步应以旧Skill认可/排除样本先校准判断，再用相同画像和预算做新真实来源对照，不继续仅凭测试数量宣称获客改善。

### 首审反例与合批修复

独立审核固定 `fe920ee..77c080f`，Spec/Quality FAIL、NO MERGE，两项P2：

1. 服务端24h过期投影保留补证但status变为EXPIRED，TS错误拒绝整页。现在写入仍只允许OPEN，读取允许原回执的EXPIRED投影，过期不能通过入库日期门禁。
2. 服务端允许本人摘录加逐字背景的混合引用，TS错误拒绝背景。商机快照不含各维等级，不能在这里重新推断UNKNOWN规则；现在保留所有合法逐字引用，非UNKNOWN必须包含本人引文仍由服务端判断校验负责。没有删除真实引文或放宽模型归属校验。

新增反例初始 **3 failed / 43 passed**；修复后两个文件46通过。真实PG单HTTP再次捕获混合引文与25h后`expired_page`（1通过，原OPEN回执未变），最终三个受影响TS文件含原样wire **47 passed**。其中一处测试类型字面量拓宽导致typecheck失败，改用已解析的回执类型后最终`npm --prefix desktop run build`类型与renderer通过；不重跑全套。两次renderer构建仅因审核修复改变产品字节，没有重复安装构包。
