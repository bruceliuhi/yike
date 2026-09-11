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

- [ ] RED new default research deny and configured confirmed-start/source/assessment test, then minimal implementation.
- [ ] Adapter API: ResearchAssessmentRunner(resources), CandidateReviewStore(..., research_assessment=None). Internal adapter receives claims, request, captured snapshot, model and minimal kwargs; returns existing value,usage tuple. Capture research provenance in snapshot only for research configurations; ordinary snapshot semantics unchanged. Expose no client-selected task budget.
- [ ] Admission hook and grounded digest, no-repeat, source/current-binding check, cancel/limit/replay tests. Same request alias cache uses no additional permit. Model adapter offers assess_before(deadline, **kwargs); unsupported model fails closed before fresh quota.
- [ ] Report exact files, RED/GREEN and limitations; no commit. Root integrates.

## Task 2: Internal sequential assembly

Owner root. New pilot/research_orchestrator.py and tests/test_research_orchestrator.py. Reuse read_public and review; deterministic UUID5 IDs scoped task/run/action, exact source receipt, authoritative detail binding and current observation. Return bounded truthful progress, preserve unknowns and errors, no scheduling/settlement/API activation. Root also runs one real restricted-PG assembled path with synthetic boundaries when adapter ready.

## Task 3: Review and integration

- [ ] One nonauthor commit-bound full-batch review; fix directed findings and delta-review.
- [ ] Record evidence below, taskbook pointer, push main, verify remote/local parity; stop owned test PG.

## 实施证据

待实施。基线273430d；本片不开放普通客户端研究、生产规则或对外触达。
