# Fixed original-source evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Execute the bounded persistence/read task with TDD and independent review; root owns shared HTTP verification and final integration.

**Goal:** A human-included opportunity exposes its exact retained public source, observation and verbatim source citations through the existing authenticated detail API, without exposing private research history or replacing old evidence with current raw data.

**Architecture:** Add one tenant-shared immutable evidence row per newly created opportunity in the existing INCLUDE transaction. Read it with the existing opportunity/profile/source query in one statement; no joins into owner-private raw/request history on shared reads. Existing legacy imports return explicit unavailable evidence. This implements the already-approved original-evidence design and does not redesign R4 or change send authority.

**Tech Stack:** Existing Python/PostgreSQL/psycopg/FastAPI and pytest; no new dependency.

## Global Constraints

- Product code goes to `yike-ai2026/main`; preserve concurrent Win work and the dirty original checkout.
- Basic identity/tenant isolation, credentials, confirmation, deduplication, budgets, cancel and recovery are not deferred by phased delivery.
- Human INCLUDE shares only the included public source and approved judgment. Never share profile-description quotes, private search query, request payloads, connection/session/device data, or unrelated raw observations.
- COMMENT title is the parent post/container title; its body belongs to the current author, while parent.body belongs to a separate parent comment. Never assign container title to the parent comment author or treat parent text as current buyer intent.
- Persist only on `created=True` in the existing import transaction. ALREADY_IMPORTED, exact request replay and later source/strategy/profile changes do not replace the original shared evidence.
- Evidence is a historical inclusion snapshot, not current source accessibility, a live-source claim, sending authorization or permission to run a platform.
- Observation time is the signed collector's declaration; received time is the server ingestion time; captured time is the server human-INCLUDE time. Unknown publication/parent times remain null. Same-content observations do not require a new assessment; capture the current selected observation at inclusion, not a falsely claimed earlier preview observation.
- Existing migrations111–114 are immutable. Reserve new115 for Mac evidence;108/110 remain Win. No automatic capability enable, production deployment, source access or external send.
- Tests use real restricted PostgreSQL and actual strategy/signature interfaces with explicitly synthetic source/provider content. They do not prove customer or platform acceptance.

## Ownership and scope

Base `aac3fe9c6cc926108d70a551b90bc3e133984880`. Mac owns new115, `pilot/opportunity_evidence.py`, small `candidate_review.py`/`store.py`/`db.py` integration and its tests. Win owns05C/05F strategy/client and05G/05E original-evidence adapters; do not edit desktop files here. Preserve candidate review private payload/hash/replay semantics. No generic evidence history engine, evidence backfill, ORM replacement, or private-history endpoint.

### Task 1: Immutable inclusion evidence and existing detail read

**Files:**
- Create `pilot/opportunity_evidence.py`, `migrations/115_v02_opportunity_evidence.sql`, `deploy/grant_opportunity_evidence.sql`.
- Modify `pilot/candidate_review.py`, `pilot/store.py`, `pilot/db.py` only at the capture/import/detail/registry seams.
- Create `tests/test_opportunity_evidence.py`, `tests/test_opportunity_evidence_postgres.py`.
- Adapt `tests/test_candidate_review_postgres.py` fixture to apply new explicit grant; use ON DELETE CASCADE to the shared opportunity for existing trusted cleanup. Do not change old migration bytes or broaden runtime grant privileges.
- Root separately owns `tests/test_confirmed_strategy_http_postgres.py` and final contracts/QA/taskbook.

**Interfaces / exact public shape:**

```python
# pilot/opportunity_evidence.py -- no DB/network in builder or presentation function
def build_evidence(*, opportunity_id, snapshot, assessment, observation, verification, captured_at) -> dict: ...
def evidence_view(payload, digest, *, opportunity_id, profile_version_id) -> dict: ...

# Existing GET /api/ui/opportunities/{id} -> opportunity gains this one field.
# Legacy/missing row only:
source_evidence = {"status": "UNAVAILABLE", "reason": "NOT_CAPTURED"}
# Present row (fresh ordinary JSON data, never execution authority):
source_evidence = {"status": "CAPTURED", "snapshot_sha256": digest, "snapshot": payload}
```

`payload` exact top-level keys: `schema_version` (`opportunity-source-evidence-v1`), `opportunity_id`, `captured_at`, `source`, `observation`, `assessment`, `verification`. Fields are allowlisted, not a deepcopy of the private snapshot.

- `source`: `platform`, `kind`, `external_source_id`, `external_comment_id`, `public_url`, `version_id`, `content_sha256` (raw content_version), `title`, `container_title`, `body`, `author_public_id`, `published_at`, `parent`. For COMMENT: title=null; container_title=raw.content.title. Otherwise title=raw title, container_title=null. Parent is null or exact raw public parent keys `external_comment_id/body/author_public_id/published_at/public_url`; it does not acquire container_title. Do not include source query or internal execution IDs.
- `observation`: `id`, `observed_at`, `received_at`. Read the exact current_observation_id under the existing locked projection, scoped by tenant/owner/candidate/version. Do not use legacy pilot_source_observations or import timestamp. Missing or mismatched selected observation fails the INCLUDE transaction, not a fallback.
- `assessment`: `id`, `assessed_at`, `profile_version_id`, `profile_version`, `strategy_version_id`, `provider`, `model`, `rule_version`, `rule_sha256`, `citations`, `omitted_profile_citations`. Citations are ordered flat records `{dimension,field,quote}` from businessMatch/intent/urgency/actionability. Allowed public fields: `source.title`, `source.body`, `source.container_title`, `source.parent.body`. Map original title/body/parent.title/parent.body to these exact paths. Drop profile.description quotes and count them; no private dimension reason, full model response or profile description in this new payload. Approved human reasoning remains in existing opportunity fields. All remaining quotes must be verbatim in the addressed source field, preserving whitespace; malformed or impossible citation fails, not silently reattached.
- `verification`: `method`=HUMAN_REOPENED, `status_at_capture`=OPEN, `checked_at`, `opening_method`, `contact_method`. These are historical human declarations from the already-validated verification; do not include free-form locator/excerpt or represent current platform status. Existing opportunity source_status remains separate and defaults UNVERIFIED.

Builder validates selected binding against assessment and observation, including raw version/hash and comment roles. It returns new primitives without mutating inputs. Use a single canonical UTF-8 JSON SHA256 helper for stored payload. `evidence_view` requires valid schema/hash and matching opportunity/profile IDs, returns a fresh structure, and raises a fixed safe error on corrupt present data. Corrupt/read failure is not UNAVAILABLE/NOT_CAPTURED. It does not infer current profile/strategy validity from this historical payload.

**Persistence:** table `pilot_opportunity_evidence` with `(tenant_id TEXT, opportunity_id TEXT)` primary key, same pair FK to pilot_opportunities ON DELETE CASCADE, `payload JSONB NOT NULL`, `payload_sha256 TEXT` lowercase64hex. Enforce payload is object/schema/version/opportunity binding; enable and force tenant RLS with USING/WITH CHECK. UPDATE trigger always rejects evidence changes; no runtime UPDATE/DELETE/TRUNCATE or table ownership. Explicit repeatable grant script accepts only existing non-superuser/non-bypass/non-createrole/non-owner application role, revokes previous rights on this new table and grants SELECT,INSERT only. Register115 once in existing migration list. No foreign key from shared row to owner-private history.

**Insertion seam:** after actual import and only when created, fetch the exact observation using the existing cursor, construct the allowlisted payload, and insert with the same cursor. No extra transaction or independent commit; any failure also rolls back opportunity/source changes/review/receipt. No ON CONFLICT overwrite or silent evidence failure.

```python
if opportunity['created']:
    # Existing locked snapshot provides current_observation_id and binding.
    cursor.execute('''SELECT observation_id, candidate_id, version_id, observed_at, received_at
        FROM pilot_candidate_observations
        WHERE tenant_id=%s AND owner_user_id=%s AND observation_id=%s''',
        (tenant, claims.user_id, raw['current_observation_id']))
    observation = _primitive(_row(cursor))
    public = build_evidence(opportunity_id=opportunity['opportunity_id'], snapshot=snapshot,
        assessment=assessed, observation=observation, verification=check[2], captured_at=now)
    cursor.execute('''INSERT INTO pilot_opportunity_evidence
        (tenant_id,opportunity_id,payload,payload_sha256) VALUES(%s,%s,%s::jsonb,%s)''',
        (tenant, opportunity['opportunity_id'], canonical_json(public), evidence_digest(public)))
```

Keep this seam small; builder lives in the new focused module. Existing `get_opportunity` changes its one SELECT to LEFT JOIN the evidence table on both tenant/opportunity keys, invokes `evidence_view`, removes internal payload/hash aliases, and returns the existing fields plus `source_evidence`. No fallback query into raw history. Existing HTTP endpoint naturally returns it. Registry/schema/grant failure is an operational error, not a fake legacy result.

**Test cycle:**

- [ ] Write pure RED for source-vs-parent roles, exact quotes, profile quote omission, no input mutation, corrupted view and null parent dates. Use exact selected fields and unique private marker, not mock return-value assertions. Run `.venv/bin/python -m pytest -q tests/test_opportunity_evidence.py`; expected missing module/feature failure, then implement the pure builder/view and GREEN.
- [ ] Write restricted PG RED using existing actual `real_strategy_env` + `prepare_review` helpers from `tests/test_confirmed_strategy_review_postgres.py` (import their prerequisite fixtures explicitly). Assert real INCLUDE then `env.store.get_opportunity(...)["source_evidence"]["status"] == "CAPTURED"`. Demonstrate missing field/table before integrating schema/write/read. Add migration/grant twice, current role privileges/RLS, same-tenant other-user minimal view while raw remains private, different-tenant denial, COMMENT parent role, replay/ALREADY_IMPORTED unchanged evidence, signed subsequent changed raw/observation cannot replace snapshot, legacy NOT_CAPTURED, rollback on evidence insert failure and corrupt present digest raising safely. New tests must exercise real production builder/store, not construct an allegedly persisted snapshot by direct insert except deliberate corruption/permission fixtures.
- [ ] Implement115/grant/registry and small producer/getter seams. Add explicit grant to existing review fixture so all consumers use actual upgraded restricted roles. Capturing evidence is now mandatory for new approved candidate imports, while legacy trusted imports remain explicitly unavailable.
- [ ] Run focused GREEN during implementation, then once final affected set: `.venv/bin/python -m pytest -q tests/test_opportunity_evidence.py tests/test_opportunity_evidence_postgres.py tests/test_candidate_review_postgres.py tests/test_confirmed_strategy_review_postgres.py`. Root assigns exclusive dedicated PG lane. Preserve RED/other failures, exact counts/skip status; do not run broad desktop/package/model suites.
- [ ] Verify no111–114 SQL delta and `git diff --check`; self-review; ask root before staging (shared index). Commit only owned files. Write full TDD/results/concerns report; fresh independent task review must pass before final root integration.

## Root integration and handoff

Before producer implementation, extend existing actual strategy shared-HTTP chain with a failing opportunity-detail assertion. After Task1, verify CAPTURED payload matches source version/current observation and actual model citations; same tenant can read only the approved projection, cross tenant gets404, logout gets401, no-store stays set. Keep actual strategy, signed upload, local owned model fixture, human verification and INCLUDE; do not replace chain with mocked store. Run this modified HTTP module plus existing candidate-review HTTP and pure UI routes once; no repeated full tests for docs.

Publish `docs/contracts/V02_OPPORTUNITY_SOURCE_EVIDENCE.md` with the exact DTO, sharing/capture-time rules, legacy/corrupt behavior and Win05G/05E consumption boundaries. Update only unique taskbook, current integration record and focused QA; existing P07 hash/source-verification adaptation and R4 display remain Win work. Final independent code/architecture/quality review covers all source/tests and root docs. Normal fetch/merge/push, live main SHA parity; no parent card or full Goal completion claim.
