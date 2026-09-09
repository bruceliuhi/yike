# Candidate ingestion vertical slice implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete V02-02B raw candidate upload and authenticated raw-inbox reads, consuming the reviewed 02A and 01C/03A contracts. This is the next backend connection in the real-source vertical slice, not proof of real collection or approved opportunities.

**Architecture:** Existing PostgreSQL and active session/owner boundaries; immutable raw content and observations with a stable candidate projection. Call ExecutionRuntime submission guards inside the same transaction as insertion, budget accounting and the immutable receipt. No external calls in database transactions. Keep existing reviewed imports and UI candidate contracts unchanged.

**Base:** `3874d6225d9dad1bd5b1e3f915ef03c7f9fd60f8`, existing isolated `codex/mac-device-authorization`. Migration **112** reserved for this slice; 108/110 remain Win. No desktop, business profile, strategy or source-adapter implementation is claimed here.

## Contract and constraints

- Validate original JSON with `validate_candidate_batch(..., now=database_clock)`. Reuse frozen `candidate-upload-v1`, source identity, content hash, fingerprint and Ed25519 signing payload. Batch request IDs remain opaque (1–128), not UUID-only.
- Owner-private source identity is `(tenant, owner, source_identity)`; stable candidate is `(tenant, owner, profile_version, strategy_version, source)`. Do not claim tenant-wide or global discovery dedup. All tables enforce owner/tenant RLS and full execution binding where relevant.
- Immutable content versions include original public fields; observations preserve original query, claimed observation time, database receipt time, task/run/platform-run, collector/normalizer, batch and original record index. No keys, cookies, authorization tokens or signatures stored in receipts.
- Batch uniqueness is exactly `(tenant, platform_run_id, request_id)`. After active-session validation, matching original body returns the old receipt without reauthorizing new work; changed body is 409. A replay costs zero. A new batch costs `len(records)`, including observations of known sources. Concurrent retries serialize; errors roll back every write and budget change.
- Candidate IDs are server UUIDs and persist across batches/runs with the same profile/strategy/source. `revision` is a server projection revision, not a platform edit count. First content is revision 1. Strictly newer changed content advances revision and current version; same-content newer observation advances the watermark without a new revision. Older observations never roll current content backwards. Same-timestamp conflicting content sets `ambiguous=true`, preserving evidence without picking a platform truth; the first ambiguity transition advances revision. A strictly newer observation resolves ambiguity and advances revision even if current content is unchanged. A→B→A can reuse immutable A with candidate revision 3.
- Raw records are always `UNVERIFIED`; no insertion into approved opportunities, no scoring/review claim. Unknown publication times remain null. New read output is `candidate-inbox-v1`, an explicit raw contract, not a forged R3 Candidate DTO.
- Lock sequence: active session → original batch key → receipt lookup → existing runtime authority/lease/shared task budget locks → deterministically ordered source/candidate locks → writes/budget/receipt → runtime final fence → commit. No cursor or terminal platform state is invented: v1 batch has no cursor/end/stop-ack fields. Empty receipt is accepted 0, not task success.
- Minimum non-superuser app permissions; append-only versions, observations and receipts. Current deployment-role inherited privilege audit remains a separate launch gate.
- Add only focused tests each iteration; integrate relevant suites once after frozen code. No fabricated production source, actual strategy resolver, platform send or customer UAT evidence.

## Task 1: Atomic raw ingestion and owner-scoped inbox persistence

**Owner:** independent implementation agent; root reviews/integrates. Root implements Task 2 in non-overlapping files.

**Files:** create `migrations/112_v02_candidate_ingestion.sql`, `deploy/grant_candidate_ingestion.sql`, `pilot/candidate_ingestion.py`, `tests/test_candidate_ingestion_postgres.py`; update only necessary migration/grant registration in `pilot/db.py`. Do not edit `pilot/ui_api.py`, `pilot/web.py`, API tests or shared docs. Migration 111 and Win-reserved 108/110 are immutable/out of scope.

**Required context:** Read this entire plan (including global constraints), `docs/contracts/V02_CANDIDATE_INGESTION.md`, `docs/contracts/V02_EXECUTION_RUNTIME.md`, existing candidate contract/runtime/db/grants, and execution PG fixtures. Read private preflight report `/Users/xingheimac/Developer/Work/意客AI-MVP/.git/worktrees/dual-agent-taskboard/sdd/candidate-ingestion-preflight.md`. Reuse reviewed mechanisms instead of copying a second authorization engine.

**Public Python API to freeze for Task 2:**

```python
CandidateIngestionStore(database, execution_runtime=None)
store.ingest(claims, payload: dict, signature: str) -> dict
store.get_receipt(claims, platform_run_id: str, request_id: str) -> dict
store.list_candidates(claims, *, task_id=None, platform=None, page=1, page_size=20) -> dict
store.get_candidate(claims, candidate_id: str) -> dict
# Sanitized CandidateIngestionError(code, status=400), exposing .code and .status.
```

Methods require an active registered session; no caller tenant input. Return primitives (UUID/time converted to strings). Receipt includes schema, request/platform-run/task/run IDs, accepted count, original-order record items with candidate/version/observation IDs and revision at acceptance. Inbox returns schema, items, page/page_size/total; detail includes projection/current version and a bounded observation page with explicit total/truncation (not unbounded JSON). Task filter uses observations, not only most recent task. Document exact returned fields in report for root contract.

- [ ] Write failing real restricted-PostgreSQL tests before production changes; capture initial RED command/output.
- [ ] Add repeatable migration/grants, owner policies, keys/FKs/checks and immutable tables; migration must run twice on fresh dedicated DB. Never grant Web administrator connection.
- [ ] Implement transaction, historical idempotency, version/observation/projection and raw reads. Guard signature and current execution only for new work. Check final fence using the same cursor and roll back on failure.
- [ ] Test exact replay/service recreation, changed body conflict, concurrent same-key retry, rollback including final fence, tenant/owner isolation, old receipt after invalidated lease/strategy, source version and temporal cases (A→A→late B; A→B→A; same-second ambiguity/resolution), original order, null/anonymous/unicode/web-origin, empty accepted batch.
- [ ] Add shared-budget and different-valid-session competition tests missed by execution-only slice; only one remaining record can be spent across two platforms. Test wrong device/run/generation, revocation/cancel/expiry denies new writes and leaves no partial rows.
- [ ] Use the exclusive dedicated PG lane communicated by root. Never log credentials. Do not alter/kill other tests or containers. Root will avoid PG while you run.
- [ ] Run focused tests and diff check; commit only owned files after results are known. Report exact commit, commands/RED/GREEN, output contract, limitations and test environment boundary to private `sdd/candidate-core-report.md`. Do not self-approve release or mark full 02B DONE.

## Task 2: Thin authenticated upload/read HTTP surface and handoff

**Owner:** root. **Files:** create `pilot/candidate_api.py`, `tests/test_candidate_ingestion_api.py`, `tests/test_candidate_ingestion_http_postgres.py`; surgical updates `pilot/ui_api.py`, `pilot/web.py` if needed. Update public contracts, taskbook and QA only after reviewed code. Never edit Task 1 owned implementation files concurrently.

- [ ] Add failing HTTP contract tests using a boundary double (not production/PG evidence) and existing real auth/origin plumbing.
- [ ] Fixed routes: POST `/api/ui/candidate-batches` with strict `{batch: object, signature: canonical-base64url-Ed25519}`; GET `/api/ui/candidate-batches/{platform_run_id}/{request_id}`; GET `/api/ui/raw-candidates`; GET `/api/ui/raw-candidates/{candidate_id}`.
- [ ] Bound raw request transport at 4 MiB before JSON parsing and document that clients must split larger valid DTO batches. Do not trust Content-Length or silently trim records. Retain original parsed raw body for 02A strict validation; reject extra envelope keys, non-object batches and malformed signatures without reflecting bodies.
- [ ] Use current session and HTTPS/Origin checks; default unavailable is 501 and does not advertise real source support. Map sanitized contract/runtime/ingestion errors; authenticate receipt/read paths. Pagination bounds 1–100, UUID only for server IDs; opaque batch request IDs remain valid.
- [ ] After core freezes/releases PG lane, add real HTTP→Ed25519→restricted PG tests for upload/read/retry/conflict/authorization rollback. Do not call synthetic source a real platform.
- [ ] Run focused affected integration, independent task specification and code/architecture/quality review at exact commit; fix/re-review actionable issues. Do not re-run unrelated desktop test suite when its files are unchanged.
- [ ] Update raw output/grant/integration handoff and one authoritative taskbook; retain Win in-flight work, formal launch gates and goal. Fetch main; preserve others with normal merge if needed, then verified non-force push to `yike-ai2026/main` and feature branch per existing authority.

## Evidence boundary

This slice can prove an authorized signed synthetic source batch survives retries and becomes a readable unreviewed record in real PostgreSQL. It cannot prove real platform collection, confirmed strategy availability, intent quality, outreach, reply association, installation or revenue. Those remain the next vertical integration tasks; original M3 and customer UAT requirements are unchanged.
