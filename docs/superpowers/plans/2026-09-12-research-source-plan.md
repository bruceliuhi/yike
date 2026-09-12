# Research source plan Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. 一批必要定向验证与独立整批审核，不逐卡构包。

**Goal:** 在同一用户确认的研究任务执行多个公开入口，报告真实逐源进度且不提前完成。
**Architecture:** 冻结sourcePlan，确定性每源action/记录配额，先读全部源再沿用当前候选判断；旧单源路径不变。
**Tech Stack:** Python/PostgreSQL/FastAPI，TypeScript/Zod/React/Electron。

## Global Constraints

逐项遵守 `docs/superpowers/specs/2026-09-12-research-source-plan-design.md` 的精确字段和边界。PUBLIC_WEB三个索引，不声称三个平台；不部署/外发/新增收费；旧字节不变；每advance最多一个新效果；失败/UNKNOWN不越过、不重试。

### Task 1: 后端来源计划完整执行（独立实现者）

Files: `pilot/research_strategy_contract.py`, `pilot/research_source_catalog.py`, `pilot/research_runtime_config.py`, `pilot/research_public_reader.py`, `pilot/research_candidates.py`, `pilot/research_orchestrator.py`, `pilot/research_runtime.py`, `pilot/research_execution_api.py`及对应 `tests/test_research_*`。不改desktop/台账，不commit/push。

- [ ] RED：先以现有确认/报价/START辅助建立两个源sourcePlan，期望初次source读取后canAdvance且不COMPLETED；当前因字段不存在失败。另测legacy dump不含sourcePlan、null/重复/anchor/预算不合法拒绝。
- [ ] 新严格可选sourcePlan，保持缺省摘要；catalog导出计划源、每源UUIDv5 action与固定配额helper，来源和成员校验不接受任意URL。sourcePlan只在exact PUBLIC_WEB/search/once允许；配置及snapshot执行预算双重校验。
- [ ] Reader沿用已支持固定索引。Candidate store读前和事务提交都绑定同快照source/action及input SHA；每源配额为`q+(index<remainder)`，仍受task剩余总数约束。旧单源不强加新action限制。
- [ ] Orchestrator.inspect保留旧state路径；计划路径汇总各源事件、真实receipt、items/reviews。每源receipt分别传入_current_payload确保provenance正确；先读取全部源，再逐次分析当前版本。任何失败/pending/unknown停止，不通过新action绕过。
- [ ] Runtime v3返回sourceProgress精确DTO；全部源SUCCEEDED才给总acceptedOriginals整数，完成条件不提前。capability精确source_plan_version1，旧无参/catalog1不变；API拒绝混合/重复/未知query。
- [ ] 专用受限PG验证有界多源完整链、空源/失败/重复及恢复；假源/模型明确合成，真实HTTP handler+PG结果opt-in导出 `/tmp/yike-source-plan-http.json`，不记录签名/令牌/DSN。集中运行相关测试，不重复相邻全套。报告 `/tmp/yike-source-plan-backend-report.md`，说明RED/GREEN与最终命令结果，冻结后告知主代理。

### Task 2: 用户确认计划与逐源进度（主代理）

Files: `desktop/src/shared/researchRuntime.ts`, `researchStrategies.ts`, `main/servicePolicy.ts`, `renderer/domain/researchUsage.ts`, `nativeResearch.ts`, `task.ts`, `renderer/pages/TaskWizard.tsx`, `pages/tasks/PublicSourceSelector.tsx`, `TaskConfirmationSummary.tsx`, `ResearchProgress.tsx`, 对应tests。

- [ ] RED：解析sourcePlan、v3 capability/status，旧字节不变；目录新增查询IPC和严格只读降级；选择两个源后冻结策略/报价/START；少预算/缺第二源绑定/能力回退均阻断。
- [ ] 新共享sourcePlan schema，跨字段校验；draft可保留人工未完成预算，prepare/start拒绝无效。新增能力不能让旧服务接受计划；全部成员复核，不只主源。
- [ ] 复用既有选择/确认布局，增加多源复选和逐源固定记录配额；改变主源重新排已选源但不悄悄删选择；只剩一个时删可选sourcePlan字段。输出每源状态、真实入库条目和总分析进度，不把同来源观察数当买方数。
- [ ] 用定向Vitest实际页面测试、正式服务路由+实际后端DTO artifact消费及tsc验证。将源码字节和失败修复写入本计划Evidence，不重构未相关UI。

### Task 3: 独立审核和main集成

- [ ] 冻结产品提交，独立审核者检查整批执行/隔离/预算/恢复/客户端。阻断项定向修复并复审。
- [ ] 唯一任务书记录限定证据和剩余全目标，更新部署兼容说明；fetch确认main后ff合并/push/远端SHA回读，Goal保持ACTIVE。

## Evidence

产品提交 `32e0501445091220f16ba66523baf78bbcaf5899`，基线 `0fe86ac`；后端独立实现、主代理客户端并行。非作者 `research_source_plan_review` 整批审核 PASS / CODE_CANDIDATE_ONLY，未发现可操作的Critical/Important/Minor缺陷；复用定向证据、检查实现及实际artifact摘要，未重复广泛测试。上述任务清单是原计划；本节为唯一实际验证记录。

- 已实现可选冻结 `sourcePlan`、逐源固定 action/均分记录配额、先读后分析、每推进一次最多一个新动作及逐源真实回执。已接客户端选择→确认配额→报价/签名启动→逐源进度；每个来源均核对服务能力和执行绑定。缺失新字段不改变旧策略摘要；无计划的旧协议不加新字段。
- 后端 TDD：初始新字段拒绝、v3能力422、第一源后仍QUEUED分别复现并修复。风险范围合并检查初次283通过/35失败，发现旧Pydantic实例重验证补出sourcePlan=null；按既有缺省字段方式修复后合同205通过，原运行时/隔离/租约/入库PG失败集32通过。新增计划14单元＋7真实受限PG场景最终21通过，包括两/三源、公平配额、空源、重复身份、失败/UNKNOWN/pending阻断与action/摘要校验。一次误并发PG迁移测试夹具导致7个setup死锁，串行重跑通过；不是产品错误，未隐藏。
- 客户端 TDD：先复现草稿/v3协议、第二来源未核实仍启动、降级次数不足、缺多源选择/配额/进度。修复后合同/runtime9通过；native/client/selector14通过；实际向导/进度及相邻任务页38通过。追加启动前第二绑定失效与能力回退，相关6文件55通过。最终还复现并修复普通源标签误称“作者回复”、准备策略允许101条与后端不一致；最终4文件35通过。`tsc --noEmit` exit0，`git diff --check` clean。以上为重叠定向样本，不相加成全仓总数，不宣称全仓测试通过。
- 正式服务调用桥接：后端实际认证HTTP handler＋受限PG输出 `/tmp/yike-source-plan-http.json`；最后版本SHA256 `2872963553a800c83154dd2c7fdd6495b5d4455fe752f936c1fc216b2c7ec97e`。Node正式serviceClient/IPC策略→renderer transport/严格schema读取真实输出，末次1通过；新计划单元＋新/旧artifact桥接共7通过。来源/模型输入为合成，Node网络由保存回执替代；不是公网TLS、V2EX实采或真实模型效果。旧单源artifact来自上一批，复用其旧查询拒绝证据，无新增旧服务部署声称。

可复现：专用受限PG环境运行 `tests/test_research_source_plan.py` 和 `tests/test_research_source_plan_postgres.py`；可选 `YIKE_SOURCE_PLAN_HTTP_OUTPUT` 导出上述匿名测试回执，再在desktop设置 `YIKE_SOURCE_PLAN_HTTP_ARTIFACT` 运行 `tests/researchSourcePlan.http.test.ts`。不得将测试模型/计价参数复制生产。客户端相关测试为 `researchSourcePlan`、`researchRuntime`、`researchRuntimeClient`、`nativeResearch` 及 `ui/targeted-research-source`、`ui/task-desktop-execution`、`ui/research-progress`。

未部署、未构包、未读取真实平台、未外发、未结算；Windows/生产/跨行业客户闭环未验。此批只是同一公开平台的多个索引编排，完整多平台研究、覆盖补查、评论深读及完整V02仍须继续，Goal ACTIVE。
