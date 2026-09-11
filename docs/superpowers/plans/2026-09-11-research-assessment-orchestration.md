# Research assessment orchestration plan

Use subagent-driven-development. Root owns serial git, orchestrator and documents; implementer owns model/resource/review integration. One independent whole-batch review, targeted tests only. User preauthorized technical design; no production enablement, pricing, deployment or external messages.

Design: ../specs/2026-09-11-research-assessment-orchestration-design.md

## Global constraints

- Reuse existing CandidateReviewStore _assess cache, request/quota/retry/persistence. Trusted research adapter runs only for a fresh actual model effect, never on cache or replay. Default research ASSESS without adapter fails closed before quota/request writes; ordinary path unchanged.
- Derive task/run/observation from DB, never request task IDs. Begin permit performs existing task/session/device/strategy checks plus an internal same-transaction exact candidate/source provenance gate. No network transaction, mutable per-request shared state, client callback or new grants.
- Validate grounded output before resource success digest. MODEL_CALL success is effect completion only, distinct from durable review result. Unknown never automatically retried. Deadline bound via invocation-local model copy, no shared timeout mutation.
- Internal sequence uses one deterministic source action and review request per exact candidate version/observation. Consume exact receipt only, skip stale/ambiguous/cross-task current observations, stop on uncertainty/failure. Never claim analyzed originals are qualified opportunities, finish settlement or send.
- Work only /tmp/yike-v02-scope.Pwf9Fs; apply_patch edits. Agents do not stage/commit/push. No external network/model, broad test reruns or builds. Use existing dedicated test PG only after root provides actual port.

## Task 1: Trusted assessment effect

Owner implementation agent. Files: pilot/candidate_review.py, new pilot/research_assessment.py, pilot/research_resources.py and pilot/research_resource_runner.py internal admission hook only, pilot/candidate_assessment_model.py bounded method; focused tests in tests/test_research_assessment_postgres.py and tests/test_research_assessment_model.py. Avoid other files unless a concrete dependency requires it.

- [x] RED new default research deny and configured confirmed-start/source/assessment test, then minimal implementation.
- [x] Adapter API: ResearchAssessmentRunner(resources), CandidateReviewStore(..., research_assessment=None). Internal adapter receives claims, request, captured snapshot, model and minimal kwargs; returns existing value,usage tuple. Capture research provenance in snapshot only for research configurations; ordinary snapshot semantics unchanged. Expose no client-selected task budget.
- Internal `assess_research(claims,payload,*,task_id,run_id,observation_id)` binds the orchestrator's exact persisted receipt to capture/admission; it also checks original stored provenance on replay. These arguments are not public request fields. They prevent an observation switching to another task between sequence selection and dispatch from changing which budget is charged.
- [x] Admission hook and grounded digest, no-repeat, source/current-binding check, cancel/limit/replay tests. Same request alias cache uses no additional permit. Model adapter offers assess_before(deadline, **kwargs); unsupported model fails closed before fresh quota.
- [x] Report exact files, RED/GREEN and limitations; no commit. Root integrates.

## Task 2: Internal sequential assembly

Owner root. New pilot/research_orchestrator.py and tests/test_research_orchestrator.py. Reuse read_public and review; deterministic UUID5 IDs scoped task/run/action, exact source receipt, authoritative detail binding and current observation. Return bounded truthful progress, preserve unknowns and errors, no scheduling/settlement/API activation. Root also runs one real restricted-PG assembled path with synthetic boundaries when adapter ready.

## Task 3: Review and integration

- [ ] One nonauthor commit-bound full-batch review; fix directed findings and delta-review.
- [ ] Record evidence below, taskbook pointer, push main, verify remote/local parity; stop owned test PG.

## 实施证据

基线273430d；方案effe145，内部顺序编排4cdfd87，随后整合受控评估、原请求绑定防护。当前等待整批非作者审核，未推送主线；本片不开放普通客户端研究、生产规则或对外触达。

- 独立只读架构检查确认复用现有 `_assess`，不另建模型结果合同；候选来源校验与许可同事务，模型与数据库事务分离。采用保守分事务恢复：模型事件SUCCEEDED只证明有效模型结果曾完成，后续评估提交仍可能UNKNOWN，不重调同action。
- 编排正例先以NOT_IMPLEMENTED行为RED；内部恢复收到不属于该候选版本的结果也先RED。实现后15项顺序策略测试通过（0.16s），覆盖精确receipt、版本/观察/任务变化、空原文、停止、失败与恢复。不把这些单元双替身称为真实存储。
- 研究评估/deadline新增10项通过（15.35s），含受限PG真实确认任务/来源/评估存储；已有模型/resource runner兼容195项通过（4.44s）；普通review/cache选定3项通过（2.98s），非全产品回归。测试中修正二次topic夹具published_at漂移导致的正确ambiguous，不降低生产判定。
- root独立整合：`tests/test_research_orchestrator_postgres.py`在最终修改后1项通过（3.04s）。实际确认START→来源事件→2条原文持久化→2次MODEL_CALL→现有复核列表，原请求恢复无第二次读取/模型；均为合成来源与模型边界、真实专用受限PG。两条仍是UNVERIFIED/PENDING_REVIEW，不能算已核验商机或客户验收。
- 模型使用调用专属浅复制和绝对monotonic截止，不重载规则文件、不改变共享实例；剩余任务许可、评估90秒期限与原模型时限共同约束。当前未加入新迁移/权限；136保留给独立短信登录/试用权益侧任务。
- 仍待用户启动/结果接线、完整研究来源规划、结算、真实模型、Windows/生产与跨行业用户证据；完整Goal保持active。
