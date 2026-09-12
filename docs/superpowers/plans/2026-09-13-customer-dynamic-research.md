# Customer Dynamic Research Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. One backend implementer alongside root frontend/integration; one whole-batch independent review, affected tests only.

**Goal:** Customer-confirmed task → original Skill driven public research → durable original candidates → assessment/review in the existing workbench.

**Architecture:** Reuse signed research START, context-v2, effect journal, PostgreSQL candidate/review stores and R3/R4 pages. Add an explicitly negotiated v4 background mode; fixed-source v1–v3 keep their contracts. Do not reopen the personal Skill or build a second application.

**Tech Stack:** Existing Python/Codex worker/PostgreSQL/FastAPI and Electron/React/Zod.

## Global Constraints

- Design `docs/superpowers/specs/2026-09-13-dynamic-customer-research-integration-design.md` binds this batch; user 2026-09-11 authorized within-scope detail and implementation.
- Shared owned worktree `/tmp/yike-v02-scope.Pwf9Fs`, branch `codex/customer-dynamic-research`, base `0ddad40`. Stage only owned files. Do not touch other worktrees, shared containers, personal keys or production.
- `public-web-agent-v1` is separate from the fixed catalog. PUBLIC_WEB/PUBLIC_ANONYMOUS, source=search, mode=once, no links/schedule/sourcePlan/provenance/platformQueries, dynamicScope version1/maxAgeDays1..365/IANA timezone. No platform login or external outreach under this permission.
- All planning/search/read I/O uses DurableResearchDispatcher; candidate assessment uses existing ResearchAssessmentRunner and current coordinator admission. SOURCE_READ allowance is shared by actual SEARCH and READ; no new prices, no tool/summary counts presented as qualified opportunities.
- Source fields come only from successful READ journal evidence. Unknown author/publication time stays null. No silent truncation of body >20,000. Never publish SEARCH snippets as candidate originals.
- Background work lives independently of the requesting page. Cancellation/revocation/lease loss stops further actions. Unknown/failed admitted effects stop; no blind restart, replay or refund. Known-unreadable-source continuation remains a separately stated limitation of the current journal contract, not a false claim of full local-Skill parity.
- Real empty PostgreSQL tests prove storage/lifecycle, not genuine buyer quality. Real provider/customer evidence remains separate. Full goal remains active after this vertical.

## Frozen transport between backend and frontend

GET `/research-execution/capability?dynamic_research_version=1`, internal request `{dynamicResearchVersion:1}`. Exclusive with existing version flags. Unsupported dynamic mode returns exact 422/invalid_request for negotiation fallback; malformed input fails likewise, no effect retry.

```json
{"contractVersion":4,"sourceScope":"PUBLIC_WEB_AGENT","sourceLabel":"公开网页自主研究","sourceIds":["v2ex-latest-v1","v2ex-qna-v1","v2ex-outsourcing-authors-v1","public-web-agent-v1"],"maxPlannedSources":3,"executionMode":"SERVER_BACKGROUND","limits":{"maxSearches":10,"maxSources":100,"maxModelCalls":20,"maxMinutes":30,"maxRuntimeSeconds":1800},"settlementState":"PENDING"}
```

This advertises fixed selections and dynamic separately; old requests retain old exact responses. Dynamic limits must be sources2..100/modelCalls2..20/minutes1..30, task max_records1..100/max_runtime_seconds1..1800. Reject oversized confirmed configuration rather than silently shrink it. Shared total allowance remains authoritative; at most10 distinct searches, reads at most source limit, mission requests at most modelCalls minus one reserved assessment call; remaining allowance may permit additional assessments. The UI describes these as ceilings, never guarantees all will be spent. Server deadline also respects task age and reservation minutes.

Dynamic status uses the existing common status fields with `contractVersion:4`, exact dynamic scope/label, no sourceProgress; additionally required:
```json
{"executionMode":"SERVER_BACKGROUND","discovery":{"searches":{"issued":0,"pending":0,"succeeded":0,"failed":0,"unknown":0},"reads":{"issued":0,"pending":0,"succeeded":0,"failed":0,"unknown":0},"unpublishedOriginals":0}}
```
`acceptedOriginals` is a nonnegative integer counting persisted batch items; analyzed/skipped stay tied to existing review records, candidates unique <=100. `unpublishedOriginals` is successful READ entries without accepted candidates (oversize/budget/not yet published), not a buyer count. Search/read counters are journal facts and sum to sourceReads. Status includes no raw model thinking or keys. QUEUED canAdvance=true; RUNNING is observe-only canAdvance=false/newActionsBlocked=true (no second launch), terminal false/true. Resource-closeout invariants remain. Task canceled/lost/unknown does not become completed because a worker returned.

### Task 1: Backend dynamic customer lifecycle and original publication

**Owner:** backend implementer. Files: new `pilot/dynamic_research_runtime.py`, `pilot/dynamic_research_candidates.py`, `pilot/dynamic_research_config.py`; modify `pilot/runtime.py`, `pilot/research_runtime.py`, `pilot/research_runtime_config.py`, `pilot/research_execution_api.py`; targeted tests `tests/test_dynamic_research_runtime.py`, `tests/test_dynamic_research_candidates_postgres.py`, `tests/test_dynamic_research_config.py`. Additional minimal DB migration only if actual schema requires it; choose next number on current branch, tell root. No desktop edits.

**Interfaces:** construct a dynamic service from existing ResearchRuntimeService/orchestrator/resources, journal/context store and configured mission callable. Existing runtime delegates status/advance based on the stored task strategy, capability only explicit new flag; fixed methods remain untouched in behavior. Expose service shutdown and bind app lifespan cleanup to stop owned workers; bounded in-process max2 active workers with persisted coordinator fencing across processes. Admission must happen before worker starts and must not be stranded by executor rejection.

- [ ] Add failing config tests: old mode accepts unchanged, explicit `YIKE_PILOT_RESEARCH_MODE=public-web-agent-v1` requires agent Codex/Python absolute executable paths and nonempty server-owned keys/model, all-or-none `YIKE_PILOT_RESEARCH_AGENT_{CODEX_BINARY,PYTHON_BINARY,API_KEY,MODEL,SEARCH_API_KEY}`. Secrets repr-hidden; existing rule and assessment config still required. Missing/incomplete => fail closed; no credential discovery in runtime. Existing worker's current provider is Ark-compatible Responses, not claimed arbitrary-provider support.
- [ ] Implement explicit config and shared snapshot policy for dynamic only under configured mode; old fixed routes remain supported. Bind worker args and context-v2 from current store, no client business snapshot or key input.
- [ ] Candidate test starts signed dynamic task/context/coordinator, commits real journal READ, then publishes from that stored entry, not caller-supplied result. Representative interface:
  ```python
  store.publish(claims, task_id=task_id, run_id=run_id, sequence=read_sequence,
                generation=generation, coordinator_owner=owner, context_binding=binding)
  ```
  Assert repeated publish returns same receipt, only one candidate batch/records-used increment, SEARCH fails, oversize becomes explicit zero-accepted receipt, unknown dates/author null, tampered hash/event/current context/canceled task/stale generation reject. Use existing20-key execution_context and deferred135 trigger, event alreadySUCCEEDED must not be refinished. `_persist_records` plus batch plus records_used in one transaction, current journal/context/coordinator checked in that transaction. No unrelated refactor.
- [ ] Supervisor tests use injected bounded callable only for process boundary, real PG authority/ledger. Signed start + advance launches once, second advance/status no I/O; query progress from persisted journal, then publish and assess with existing `_review_action/_current_payload` identities. Assessment admission rechecks context/material + coordinator. Budget exhaustion keeps candidates pending and STOPPED with actual code, not complete. Late worker cannot publish/complete after cancel/lease loss; admitted original journal facts remain.
- [ ] Lease lasts only remaining confirmed task lifetime (<=1800s); status detects expired running lease as STOPPED/worker_lost with no restart. If a launched process dies before any effect, coordinator still prevents replay. Shutdown sets local cancellation; new actions fail under current authority. Do not hold DB connection during model/browser/network waits. Queue-full launch fails before electing lease, capacity always released.
- [ ] Wire capability/API/runtime only with full dynamic service; do not expose placeholder capability. Implement frozen v4 DTO and old compatibility. Test HTTP negotiation, isolation and customer→journal→candidate→assessment path with synthetic provider responses explicitly labeled test-only.
- [ ] Run new targeted tests on root-provided isolated DB, report command/results/diff concerns to `/tmp/yike-customer-dynamic-backend-report.md`, commit only owned backend/tests. Root handles integration docs and main push.

### Task 2: Existing customer workbench consumes the dynamic flow

**Owner:** root. Files: `desktop/src/shared/dynamicResearch.ts`, `researchStrategies.ts`, `researchRuntime.ts`; renderer domain models/task/researchUsage/researchStrategies/nativeResearch; service negotiation + main servicePolicy; existing PublicSourceSelector/TaskWizard/ResearchProgress and researchProgressPresentation; targeted desktop tests.

- [ ] RED strict v4 capability/status tests, old schemas unchanged, malformed/mixed versions rejected, search/reads counters match shared source usage and accepted+unpublished<=successful reads. Strategy dynamicScope exact validation and source coupling; snapshot must be PUBLIC_WEB-only. Use fixture v4 above, no synthetic UI results claimed live.
- [ ] Add separate dynamic-source type without broadening fixed publicSources/foreground capability. Preserve saved unavailable selection. Dynamic server capability, signed device and strategy authorize start; no fabricated PUBLIC_WEB connector row. `nativeResearchStartCommand(..., dynamicCapability?)` requires validv4 for dynamic, fixed sources retain connection binding. Existing start blockers distinguish dynamic mode; fresh capability rechecked immediately before START.
- [ ] Public source selector adds dynamic only when v4 available; explicit switching clears incompatible sourcePlan/provenance, offers visible60day/AsiaShanghai defaults and valid20-source/15min/20model ceilings, requires strategy reconfirmation. Never silently mutate a confirmed configuration. Dynamic age editable1..365. Existing eight entries/layout reused.
- [ ] Strategy preparation/saved drafts persist dynamicScope; settings validation tells user actual ceilings, not clamps. API and Electron IPC negotiate dynamic first, fallback only exact422/invalid_request for read-only capability.
- [ ] Progress dynamic start invokes advance once, then bounded read-only polling while mounted; page leave stops polling, not server. No unchanged-progress error for a still-running job, no repeated advance. Existing global cancel remains. Display searches/read originals separately and pending-review/candidate entry, unknowns visible. Old page-driven semantics unchanged.
- [ ] Run targeted schema/service/component tests and typecheck; real browser of existing components for running/empty/unknown states. One candidate build only after integrated review; no unrelated rebuild/test loop.

### Task 3: Integrate, verify and hand off

**Owner:** root plus independent reviewer. Existing clean baseline evidence is the previous reviewed batch; no full-suite repeat.

- [ ] Exercise fresh restricted PG signed customer path with injected provider transport: same task context + per-effect ledger + candidate + assessment + statusv4; repeat/cancel remain no-new-effect. Distinguish fixture from live provider/customer acceptance.
- [ ] Independent whole-batch spec/code review exact commit and diff; fix all important findings and run covering delta tests.
- [ ] Update this plan evidence and current taskbook only once, fetch/main integration preserving other AI work, minimal merged check, push main and verify exactremote SHA. No production config/keys altered without actual deployment step.
- [ ] Next actual provider/customer small run uses configured server credentials securely, then dedicated comments and cross-industry iteration. No unsupported claim that this batch proves opportunity supply, Windows/production or full Goal completion.
