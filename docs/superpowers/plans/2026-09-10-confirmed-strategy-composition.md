# Confirmed strategy composition implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Execute and review the two bounded tasks; do not repeat completed model, raw-ingestion or desktop work.

**Goal:** Connect the actual confirmed strategy store to signed execution, private candidate review and the shared authenticated API without hiding valid imported candidates or weakening authorization.

**Architecture:** Mutation/execution keeps the existing locking `resolve` on the caller transaction. Candidate presentation uses an explicit read-only strategy snapshot reader inside its existing repeatable-read transaction, with live authentication before and after on the outer connection. Shared API registration and migration installation remain opt-in composition, not a platform capability grant.

**Tech Stack:** Existing Python/FastAPI/psycopg/PostgreSQL services and pytest. No new dependency, UI or migration schema.

## Global Constraints

- Product code goes to `yike-ai2026/main`; preserve concurrent Win work and the dirty original checkout.
- Basic identity/tenant isolation, credentials, confirmation, deduplication, budgets, cancel and recovery are not deferred by phased delivery.
- Default unavailable capabilities remain unavailable. Actual strategy persistence does not authorize a platform, model call, monitor, send or billing.
- Historical receipts remain historical; current writes always use `ResearchStrategyStore.resolve` and `ConfirmedExecutionStrategy`.
- Candidate list data and strategy decisions use the same supplied `REPEATABLE READ READ ONLY` transaction. Its reader cannot reacquire the session fence, lock rows, open a connection, commit, call a network or change identity scope.
- Live authentication remains outside the data snapshot, before and after reading. No `skip_auth`, callback introspection, write-resolver fallback or new generic authentication framework.
- Existing 111/112/113/114 SQL bytes remain unchanged. Append 114 registration only; 108/110 default registration is outside this slice.
- Integration tests use real restricted PostgreSQL, real signed protocol and actual strategy persistence, but clearly synthetic source policy/provider responses. They prove engineering composition only, not platform access or lead quality.

## Ownership and baseline

Base `aba7f4f6d24daa5800c3a54348d6521c2b2b6e66`. CodexiMac owns this shared integration, including the small projection-only addition to Win's accepted `pilot/research_strategies.py`; Win continues 05C/client and actual source consumption, not a second shared API/DB patch. Parent 04B/04C remain in progress/awaiting actual consumer acceptance. 114 stays Win's published schema; no 115 reservation.

Root reproduced the real composition on restricted PG: actual prepare/confirm → signed raw → assessment → source verification → INCLUDE succeeds, but a bounded imported-list query returns total 0 instead of 1. The actual write resolver reacquires the session advisory fence on the inner list connection; its sanitized timeout is then mistaken for stale strategy. Independent architectural inspection agrees. The initial fixture profile-version mismatch was corrected before recording this failure.

### Task 1: Separate snapshot projection from write authority

**Files:**
- Modify `pilot/research_strategies.py`, `pilot/candidate_review.py`.
- Modify `tests/test_candidate_review_postgres.py`, `tests/test_candidate_review_http_postgres.py` fixtures to provide explicit readers.
- Create `tests/test_confirmed_strategy_review_postgres.py` for actual-store composition and reader boundaries.
- Update `docs/contracts/V02_CANDIDATE_REVIEW.md` and `docs/contracts/V02_CONFIRMED_RESEARCH_STRATEGIES.md` with the precise two-callback contract.

**Interfaces:**

```python
def read_snapshot(self, cursor, claims, profile_version_id, strategy_version_id) -> dict:
    """Presentation snapshot under caller RR/read-only identity scope; not execution authority."""

def __init__(self, database, *, model=None, strategy_resolver=None,
             strategy_snapshot_reader=None, max_daily_calls=20):
    super().__init__(database)
    if type(max_daily_calls) is not int or not 1 <= max_daily_calls <= 10000:
        raise ValueError('invalid assessment quota')
    self.model, self.strategy_resolver = model, strategy_resolver
    self.strategy_snapshot_reader = strategy_snapshot_reader
    self.max_daily_calls = max_daily_calls
```

- [ ] Write the actual-store regression before implementation. Reuse the existing fixture chain with a freshly saved/confirmed intact profile; read its actual integer version, not the old helper's hard-coded 1. Prepare/confirm through `ResearchStrategyStore`, use its resolver for signed execution/assessment/INCLUDE, and its new reader only for lists. A database wrapper with local lock timeout 300ms and statement timeout 2s makes self-wait bounded. Assert normal imported list and original-review projection both keep the same assessment ID and valid current binding.
- [ ] Run the regression RED; distinguish missing new method from the already reproduced zero-result old composition. Record exact commands/results.
- [ ] Implement the reader using the passed cursor only. Require non-autocommit, transaction isolation `repeatable read`, read-only `on`, and existing `yike.user_id`/`yike.tenant_id`; reject absent scope or owner mismatch. Reuse pure claims validation if extracted from `_active`, but never call session validation from this reader. Read version/draft with tenant+owner predicates and the tenant-bound profile parent/version without locks. Validate requested IDs, CONFIRMED state, current draft pointer/revision, complete profile payload digest against both profile and prepared strategy hash, and `_intact`. Return a fresh ordinary JSON snapshot plus `configuration_sha256`, not `ConfirmedExecutionStrategy`.
- [ ] List calls only `strategy_snapshot_reader`. Validate the exact seven returned keys (the six snapshot fields plus hash), platform list and digest/bindings against stored review snapshot. Missing reader fails closed; no locking resolver fallback. Map strategy conflict to stale state, invalid session to 401, backend failure to sanitized 503 rather than an empty list. Preserve these distinctions in `_capture` too when the actual write resolver reports them; invalid/unconfirmed data stays 409.
- [ ] Change inner SQL to `SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY`. Retain initial/final live auth and the deterministic snapshot-conflict boundary. Replace old row-lock-resolver test premises with read-only reader tests, preserving existing expiry/revocation and two-candidate coherence coverage.
- [ ] Add actual-store regression cases: another valid session of the same owner revokes between two reader calls (first list coherent, next stale, new write rejected, receipt recoverable); wrong owner/tenant/profile and missing GUC; unconfirmed/revoked/replaced strategy; corrupted profile/hash; cannot use plain reader result to authorize execution; DB unavailability is not stale/empty. Test fixture writes may use admin for setup/corruption only; product calls use restricted role.
- [ ] Run the new module plus existing candidate review PG/HTTP modules once. Existing contract/provider tests need rerun only if their code changes. Record bounded evidence, update the two contract sections, self-review, commit only owned files. Independent task review before integration acceptance.

### Task 2: Shared API, migration and complete protocol chain

**Files:**
- Modify `pilot/db.py`, `pilot/web.py`, `pilot/ui_api.py` and the existing trusted deployment grant path if one exists for other optional services.
- Create `tests/test_confirmed_strategy_composition.py` and `tests/test_confirmed_strategy_http_postgres.py`.
- Reuse Task 1's fixture/module helpers rather than copying another tenant/device/strategy setup.
- Update `docs/contracts/V02_CONFIRMED_RESEARCH_STRATEGIES.md`, `docs/qa/V02_CONFIRMED_STRATEGY_COMPOSITION.md`, unique taskbook and integration record.

**Interfaces:**

```python
# pilot/db.py migration_paths: append, do not replace another migration.
("v02-research-strategies", migration_path.with_name("114_v02_research_strategies.sql")),

# Add research_strategies=None to build_app and register_ui_api.
# Forward it unchanged through the existing call, then register:
from pilot.research_strategy_api import register_research_strategy_api
register_research_strategy_api(router, research_strategies, identity, _require_session_https)

# Explicit trusted service composition (not an automatic factory):
strategies = ResearchStrategyStore(application_database)
runtime = ExecutionRuntime(application_database, strategy_resolver=strategies.resolve,
                           capability_check=verified_source_policy)
review = CandidateReviewStore(application_database, model=model,
                              strategy_resolver=strategies.resolve,
                              strategy_snapshot_reader=strategies.read_snapshot)
```

Use the existing local router/dependency names in `register_ui_api`; do not create a second identity or Origin middleware.

- [ ] Write shared-build-app boundary tests RED: five paths registered, valid authenticated absent service returns 501, absent/expired identity returns 401, cross-Origin/HTTP restrictions unchanged, exact service receives original claims; no new default-enabled capabilities. Assert 114 is in registry with exact published filename/checksum, fresh migration and second migrate succeed under admin, restricted service gets only the accepted grant script's rights.
- [ ] Add the thin optional argument/forwarding/registration and append 114 tuple. Do not instantiate services from request input or change production feature switches. Use the existing restricted grant mechanism; no broad runtime schema/role grants.
- [ ] Build actual shared app with the actual strategy/runtime/ingestion/review services, real registered session and signed device. Through shared HTTP: prepare → confirm → signed START/CLAIM → signed candidate batch → ASSESS via existing local provider fixture → source verification → INCLUDE → current/history list → revoke → current stale, new write/old lease upload refused, original receipts readable. Reuse existing signed helper protocol, correcting profileVersion to the actual saved version.
- [ ] Run focused shared boundary and integration modules GREEN, plus affected strategy contract/HTTP and existing signed runtime regressions as needed. No real provider/platform calls. Record exact code SHA, commands, skips and limitations in QA; do not sum overlapping test sets.
- [ ] Independent whole-slice code/architecture/quality review, fix blocking findings with targeted tests. Fetch/normal merge concurrent main, review any meaningful delta, push main without force and verify SHA parity. Keep goal ACTIVE and hand off actual Win client/source consumption plus shared fixed-source opportunity evidence as next work.

## Acceptance boundary

This slice is complete when an actual persisted confirmed strategy survives the shared authenticated signed workflow and produces an inspectable current/historical candidate without lock self-wait; revocation and session boundaries still fail closed. It does not complete the first market trial, source adapters, Windows, actual model quality, sending/replies, customer UAT or M3. Next delivery must move the customer E2E forward rather than expand advanced administration.
