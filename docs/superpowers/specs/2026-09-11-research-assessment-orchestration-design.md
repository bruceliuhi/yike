# Research assessment and bounded orchestration

User authorized technical refinement inside full V0.2. This slice connects an already-started, confirmed PUBLIC_WEB research task to existing candidate analysis. It does not enable production research, price rules, external sends, or claim full multi-platform research.

## Decision

Reuse CandidateReviewStore ASSESS reservation, exact source/profile/strategy validation, snapshot cache, explicit retry, grounded assessment schema and persistence. Add an optional trusted research assessment adapter only at the actual model boundary. Do not wrap the entire review in a resource event: cache hits must not spend model permits.

Research provenance comes from current candidate observation → persisted batch → task/reservation, never client-provided task IDs. Research candidates without this adapter are denied before a fresh review/quota write. Ordinary candidates retain their current path. A fresh research model invocation requires a MODEL_CALL permit; action identity is deterministic from task/run/review request, and input digest includes the captured binding, observation, strategy and model input/metadata. Default services remain unconfigured.

Admission uses an internal optional gate in resource begin after existing task/reservation locks and before permit insertion. It locks/checks current projection and exact persisted research source binding, alongside existing current task/device/strategy/session checks. No network/model call holds the transaction. Same-action recovery never executes the gate or model again. A final disclosure recheck retains existing profile/material qualification immediately before invocation.

The configured model must support a bounded invocation deadline without mutating a shared model instance. The existing OpenAI-compatible adapter uses a per-call copy with timeout no greater than remaining permit time. Validate grounded assessment before recording the resource output digest. Resource SUCCEEDED means a validated model effect completed; it does not assert assessment persistence or candidate qualification. Existing review commit may still fail or become UNKNOWN. Such ambiguity never automatically repeats the effect; explicit retry is a new request and consumes a new permit.

## Internal sequential pilot

An internal orchestrator uses a stable source action per task/run, calls existing ResearchCandidateStore.read_public, and consumes that exact receipt. It derives review payloads from authoritative current candidate detail, skips changed/ambiguous/or-other-task current observations, and uses deterministic per-candidate/version request IDs. Existing model decisions remain REVIEW until human verification. Re-running the same invocation returns prior source/review receipts, not new network actions. Pending/UNKNOWN or failed reviews stop further model dispatch. Bounds are enforced by the stores; this orchestrator never silently starts a new task, expands sources, retries failed work, finishes task settlement or sends messages.

Output distinguishes source not ready, no accepted originals, analyzed originals and stopped/partial review; analyzed count is not qualified lead count. Only the fixed V2EX index supported by the existing reader is exercised here. This is internal assembly, not a background scheduler or ordinary-client activation.

## Validation

Targeted tests: no-adapter fail closed, ordinary review compatibility, actual confirmed research start/read/assess persistence, same-action/cache no repeat, exact source provenance, current-version/source race, cancellation/limits/UNKNOWN, bounded model timeout and sequential resume. Use dedicated restricted PostgreSQL with synthetic source/model boundaries; no repeated real public fetch or production model needed. One independent whole-batch review before main push. Full goal remains active; UI activation, complete source planning, settlement, Windows and real customer proof remain separate.
