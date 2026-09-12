# Customer-bound Research Context Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development; separate compiler/contract from PG loader ownership. One whole-batch independent review followed by delta fixes, not repeated full suites.

**Goal:** A trusted host can load an immutable research context from an authenticated, confirmed customer task without client-supplied business facts, silent profile truncation, or cross-owner history.

**Architecture:** Extend the old context with explicit v2 and opt-in dynamic strategy scope, then bind it to the existing signed task/reservation and confirmed profile/strategy in the same PostgreSQL database. This produces the context foundation consumed by the later per-effect journal/supervisor. Existing v1 bytes/capabilities remain unchanged.

**Tech Stack:** Python, existing strategy Pydantic validation, psycopg/PostgreSQL/RLS, existing Codex worker; no dependencies or real provider calls.

## Global Constraints

- Follow `2026-09-13-dynamic-customer-research-integration-design.md`. No customer capability publication, pricing invention, production deploy, Windows build or external messages in this internal batch. Per-effect durable journal and customer supervisor remain required next, not claimed complete here.
- Raw profile description preserves up to 8000 characters and LF/CRLF/tab (matching existing input); reject other C0/C1 controls and secrets. v1 stays 4000/single-line/32KiB with unchanged output and binding fields.
- v2 keeps old context fields and adds `profile_sha256` plus complete six-field `strategy_snapshot`. Validate snapshot using existing `configuration_digest`, exact IDs and projected queries/exclusions/signals/time scope. v2 maximum canonical JSON is 512KiB (covers 8000*4 profile bytes, 65536-byte configuration, 30*(3*2048 URL+500*4 description+128*4 key) history and bounded remaining fields). No silent truncation of profile or strategy; history is explicitly bounded/partial.
- v2 binding additionally has `schema_version`, `profile_sha256`, `configuration_sha256`; rule_version uses context-v2 prefix while the four original rule files and rule digest stay unchanged. Context JSON contains complete strategy (including industry counterSignals/sourceTypes); its business facts are data, not tool authorization.
- Dynamic strategy opts in with `research.dynamicScope={version:1,maxAgeDays:1..365,timezone:IANA}` paired with `publicSource='public-web-agent-v1'`, only source=search/mode=once/platforms=[PUBLIC_WEB], no links/schedule/sourcePlan/provenance/platformQueries. Old strategy requests must not gain absent or null dynamic fields; explicit null is invalid. Existing capabilities stay closed for this source.
- Store APIs accept trusted TokenClaims + canonical task/run IDs only. Validate current session/device/strategy/profile/material references using existing runtime helpers, not duplicate authority. Lock order follows resource begin: context advisory → task identity/targets → device/connection/profile/strategy → task/run/platform → reservation. No network inside transactions.
- Reference time is signed task `created_at` (server task-start time), not every load's current time. Context immutable per tenant+owner+task+run. Reload revalidates current task authority and stored rule/context/profile/config digests; invalidation does not mutate historical snapshot or authorize continued use.
- History uses current business `profile_id` and tenant+owner candidate source identities, never nickname or shared legacy followup records. Latest ACTIVE structured followup distinguishes manual CONTACTED/CLOSED; actual SENT outreach results count, drafts/queue/claim/UNKNOWN do not. Stored-history coverage is PARTIAL when nonempty, NONE when empty because unowned legacy imports/external history were not scanned. Max30; stable priority CLOSED>CONTACTED>EXCLUDED>KNOWN, fact time DESC, key ASC. Invalid source URLs leave no URL and keep a stable known-project key; do not leak session parameters. Description is a bounded explicit excerpt, not complete evidence.

### Task 1: Dynamic strategy + context-v2 compiler

**Own:** `pilot/research_strategy_contract.py`, `pilot/research_context.py`, `tests/test_research_strategy_contract.py`, `tests/test_research_context.py`.

**Public interface:**

```python
def project_research_context_v2(*, seller_description, profile_sha256,
        strategy_snapshot, reference_time, history_scope, history) -> dict:
    # derive IDs/query_seeds/exclusions/time scope from the confirmed snapshot
    # industry intentSignals if present; otherwise versioned mapping below
    # returns validated v2 raw context accepted by compile_research_context
    ...
```

Demand fallback mapping (fixed v2 rules): INQUIRY=`询问方案、价格或寻找供应商`; COMPARISON=`比较方案或供应商并准备选型`; REPLACEMENT=`替换现有供应商或系统`; CHANGE=`明确业务变化并寻找外部解决方案`.

- [ ] RED: valid dynamic snapshot accepted; mismatch source/scope/null/bool/timezone/combined scope rejected; existing snapshot serialized bytes unchanged. v2 8000 multiline preserved; old v1 newline/4001 still rejected; bad hashes/snapshot IDs/projection/controls/secret/oversize rejected before rules/worker actions.
- [ ] Add strict dynamicScope optional model/serialization and scope validation (including `_raw_fields` optional preservation). Do not alter `research_source_catalog` or runtime capability.
- [ ] Extend `_validate` and compiler using explicit schema branch and limits; v2 normalize whole strategy only through existing validated six-field snapshot contract, reject rather than silently coerce mismatched projections; derive binding configuration digest. Full strategy strings must be secret-scanned as context, not only seller text.
- [ ] Implement projector by deriving strict fields from strategy snapshot, profile hash and server time; keep history exact under existing bounds. Test `compile_research_context(project_research_context_v2(...))` for AI/non-AI, industry signals, demand fallback and stable context digest.
- [ ] Run only two owned test files, commit only owned files, report RED/GREEN and SHA. Do not change worker or PG files.

### Task 2: PG immutable customer context and scoped history (root)

**Own:** new `pilot/customer_research_context.py`, new `pilot/research_history.py`, `migrations/141_v02_customer_research_context.sql`, `deploy/grant_customer_research_context.sql`, `pilot/db.py`, `tests/test_customer_research_context_postgres.py`, affected worker tests and docs.

```python
class CustomerResearchContextStore:
    def __init__(self, runtime): self.runtime = runtime
    def load(self, claims, *, task_id, run_id) -> dict:
        # full authority checks in short transaction, insert once or validate replay
        # return compile_research_context(stored_context); no model or customer API
        ...
```

- [ ] RED restricted-PG test creates real confirmed dynamic strategy, quote + signed START, loads v2; 8000 multiline intact, fixed server reference time, stable same-task replay and one DB row; local fixture provider only, no public IO.
- [ ] Migration141 registers in PilotDatabase; owner RLS SELECT/INSERT only, immutable UPDATE guard, task/run/reservation/profile/strategy FKs and input/digest checks, JSON<=512KiB plus bounded binding. Grant only select/insert for snapshots and necessary history SELECT on owner-RLS tables, no admin runtime role.
- [ ] Loader uses `_active`, `_key`, `_connection`, `_strategy`, `_locks` and reservation binding before creating/reading snapshot; task/run live and same run; no dynamic scope => reject. Get profile description/hash after authority, task.created_at reference, history via same cursor. Advisory serializes one snapshot per task; INSERT and recheck session in same transaction. Stored context recompilation must match exact stored binding and task/profile/config IDs/digests; mismatch fails fixed error, no overwrite.
- [ ] History SQL uses owner candidate source/version/projection join and same profile entity. EXCLUDE only successful review; structured followup latest revision per record and ACTIVE; actual SENT results through owner-scoped queue/review opportunity chain. Collapse identity, order deterministically and LIMIT31 before returning30; explicit excerpts and safe URL normalization. No entire private material/contact bodies copied into context.
- [ ] PG tests: cross owner/tenant/run denied; forged stored binding/direct cross-task insert denied; profile/strategy/material invalidation denies reload; cancellation denies reload; no effects or resource consumption on context load; concurrent load one immutable row; failed transaction no snapshot. History tests separate KNOWN/EXCLUDED/manual contact/closed/SENT from drafts and UNKNOWN, repeated source versions and >30 cutoff, same business only.
- [ ] Existing worker test proves actual fixture subprocess receives v2 JSON through stdin (not argv/env), returns matching binding, credentials guard remains. No public provider research or customer capability claim.
- [ ] Freeze whole batch and independent spec/quality review; delta fixes only. Merge latest main preserving Win changes, targeted integration check, push parity. Stop/remove only the owned disposable test PostgreSQL container; keep shared project containers untouched.

## Evidence

Implementation candidate: contract `5d7d20b` + fail-closed legacy-input delta `179aec2`; store/migration/worker tests `e738ded`; history tests `2cd319b` + assertion strengthening `03d104a`. Independent whole-batch review pending; not deployed or customer-capability enabled. Full goal ACTIVE.

- Initial missing-store RED; restricted PG then exposed ambiguous source join and missing candidate-id on reviews, fixed by explicit source identity join and review-request link. Initial six tests passed. Direct forged-profile-hash regression then failed and the unpublished migration guard was strengthened against actual profile hash/description.
- Final root `.venv/bin/pytest -q tests/test_customer_research_context_postgres.py --tb=short`: **13 passed in 11.17s**, real disposable PostgreSQL with restricted runtime role. Covers exact 8000-character multiline input, fixed task reference, concurrent single-row replay, immutable snapshots, owner/tenant/run boundaries, cancellation, profile/strategy/material revocation, tampering, rollback and zero effect consumption.
- Contract `.venv/bin/pytest -q tests/test_research_strategy_contract.py tests/test_research_context.py`: **270 passed in 0.52s** after reproducing/fixing raw TypeError for a legacy snapshot embedded in v2; four research/industry combinations now reject with fixed error.
- History `.venv/bin/pytest -q tests/test_research_history_postgres.py -x`: **3 passed in 15.90s**, separate disposable PG database. Actual synthetic persisted candidate/review/followup/outreach rows distinguish successful EXCLUDE, manual CONTACTED/WON/latest VOID, SENT vs UNKNOWN/QUEUED; source dedupe/cap30/stable order, exact unsafe-key retention without URL, tenant/owner and real second-business exclusion. This is not evidence of real external contact.
- Actual fixture-process v1/v2 stdin/instructions/binding test: **2 passed** within 268-test root run before unrelated fail-closed contract delta. Customer text not in argv/env and provider credentials not in capture; no real model or search calls.
- One parallel fixture setup deadlock occurred when two migrations shared a disposable DB; isolated databases removed that test-environment conflict. New migration tested from empty DB and replayed by fixtures. No deployed migration was edited.

Remaining next: same-PG per-effect permits/action journal and coordinator-generation admission, supervisor/API/candidate evidence/customer UI vertical, then same-evidence/same-budget Skill behavior comparison and real cross-day useful opportunities. Rule loading/these checks do not prove the original local research quality was restored.
