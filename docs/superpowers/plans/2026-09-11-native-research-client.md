# Native research client implementation plan

Use subagent-driven-development; root serial git, one whole-batch independent review, no repeated broad suites. User preauthorized technical design within V0.2. Follow the complete spec at `../specs/2026-09-11-native-research-client-design.md`.

## Global constraints

- Deliver ordinary-client confirmation→signed research START→persisted bounded advancement/status→original results/cancel/recovery as one batch. Full goal unchanged; scope explicitly fixed V2EX index, not full-web search. Missing rule/model/runtime remains unavailable, no invented pricing/deployment/sends.
- Token only invocation memory; exact nonsecret journal before POST; original UNKNOWN protected; no research fallback to ordinary execution.apply/FINISH or silent quote replacement. Authentication identity/device from main/server, never renderer claims.
- At most one fresh external effect per advance, sequential client advancement, GET is read-only; source/review effect IDs stable, no automatic retryOf. Coordinator lease/generation, current task/cancel and resource permits remain authoritative; no network transaction. Preserve post-permit final disclosure guard from bac5df1.
- Exact shared camelCase API contract in spec. Source original/analysis counts not qualified opportunities; actualSoubei:null/settlementState:PENDING. New migration137 only;136 belongs to separate SMS/trial task. No auth/session/login edits in this worktree.
- Work only /tmp/yike-v02-scope.Pwf9Fs. Agents use apply_patch, never stage/commit/push or modify other checkout. Root provides test PG port; no production DB, external model/network or new package build before final integration.

## Task 1 — Native research protocol

Owner native implementation agent. Read current executionSession/controller/journal/servicePolicy/shared desktopExecution/main.ts/preload and prior shared/researchExecution.ts. Own changes there plus renderer/services/desktopExecution.ts ONLY; root owns other renderer files. Add shared `researchRuntime.ts` strict capability/status schemas from spec and main service API routing if needed. Notify root names/interfaces before implementation.

- [ ] RED exact research START journal→prepare/sign→research POST and full receipt binding, unknown/restart recovery with no token storage/no ordinary fallback; ordinary compatibility.
- [ ] Extend encrypted versioned research journal safely using existing protection/owner/service boundaries; main user/device resolution, epoch guards, no automatic retry after404.
- [ ] Expose RESEARCH_START/RECOVER/LIST via existing execution bridge, strict union/result and renderer service `researchContractVersion:1`; implement new read/run API transport operations `researchRuntime.capability/status/advance` with spec routes. Root uses schemas/service.
- [ ] Targeted tests/tsc and report exact files/results/limitations, no commit. No UI activation by this task alone.

## Task 2 — Persisted bounded research runtime

Owner backend implementation agent. Own new pilot/research_runtime.py, relevant API module research_execution_api.py (prefer optional runtime parameter), pilot/research_orchestrator.py incremental/read-only status helpers, migration137/db registration/minimal grants and focused PG/HTTP tests. Do not edit pilot/runtime.py, web.py or ui_api.py without coordinating with root (root assembly). No auth/login changes.

- [ ] RED actual confirmed research START→single fresh source advance→single model advances→persisted terminal/result status; GET performs no effect/writes; completed recovery no second effects.
- [ ] Internal coordinator API `ResearchRuntimeService(orchestrator)` exposes `capability(claims)`, `status(claims,task_id)`, `advance(claims,task_id,run_id)` returning spec DTO. Current owner/session on each; active/expired lease behavior conservative; exact generation/terminal checks, no redoing UNKNOWN.
- [ ] Completion only from server-derived stored source/review evidence; record terminal task/run/platform state by internal research path; cancellation and effectsPending distinguished. Usage derives exact resource event counts, no actualSoubei computation/settlement.
- [ ] Add authenticated GET capability/status and POST advance to research_execution_api registration with optional runtime dependency, fixed errors/limits/HTTPS/no-store. Root injects it through web/ui/runtime.
- [ ] Dedicated restricted-PG and HTTP targeted tests, current cancel/concurrent advance/session/unknown isolation cases, report actual evidence. No live models/sources or commits.

## Task 3 — Ordinary UI and runtime assembly

Owner root. Add explicit validated research runtime configuration only when actual model/rule/secret/source available; no defaults for production rates. Pass dependencies through web/ui. Reuse selected TaskWizard native flow, current quote state, task details/filtered candidate list and existing controls. Server capability gates actual source scope; quote/strategy/source changes invalidate user confirmation. Token never enters unknown-start localStorage; main journal owns research recovery. Add progress controller with serial advance/read-only recovery and no automatic unknown retry. Test the real renderer flow in proportion to changes, no visual redesign.

## Task 4 — Integrated evidence / independent review

- [ ] One actual HTTP+restrictedPG+native/renderer integration with explicitly synthetic source/model boundaries; scope/unknown/cancel/results visible, no fake lead counts.
- [ ] Whole-batch nonauthor review, directed fixes/delta review, one relevant candidate build if UI/package inputs changed. Update this single evidence record/taskbook, push main and verify parity; stop owned resources.

## 实施证据

基线c4993b6。待实现。不可将设计、功能菜单或单元双替身称为客户可用/上线。
