# Known READ Outcomes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. One implementation batch, one independent whole-batch review; reuse unchanged tests and artifacts.

**Goal:** A confirmed missing/unsupported/oversize public page is durably recorded as failed without stopping research of other authorized sources; unknown/restricted actions never resume.

**Architecture:** Extend the existing READ failure contract, two-table atomic journal, and dynamic supervisor. Keep FAILED counts, positive-only candidate publication and v4 desktop DTO; no new execution engine or automatic retry.

**Tech Stack:** Existing Python, PostgreSQL, MCP/Codex worker, TypeScript contract tests.

## Global Constraints

- Binding spec: `docs/superpowers/specs/2026-09-13-known-read-outcomes-design.md`; approved within-scope detail under AUTHORITY.md. No additional user design approval required.
- Owned worktree `/tmp/yike-v02-scope.Pwf9Fs`, branch `codex/known-read-outcomes`, base `bd1356be28d3b6895b2c070352d9f7d99d9deeb8`. No edits to other worktrees, personal Skills, credentials or production.
- Exact continuable result: `{status:"FAILED",code:"not_found"|"unsupported_media_type"|"too_large",replayed:false}`. Durable replay may return the immutable stored result; cache alone may expose replayed=true. Do not store cache replays as new effects.
- Keep `effect_result` success-only. Add one explicitly named negative-result validator/predicate shared by dispatcher/journal/supervisor. Unknown/extra fields, wrong kind, URL/hash/context mismatch never qualify.
- Only actual HTTP404/410, HTTP200 unsupported MIME, and existing concrete size-limit failures qualify. HTTP401/403 use `access_restricted`, HTTP429 `rate_limited`; these propagate as fixed codes but are NOT continuable. Generic unavailable/unsupported_content, timeout, cancellation, malformed/invalid evidence and unknown all stop.
- Failed READ consumes the existing SOURCE_READ allowance; no refund, new prices, reset budgets, implicit login or replay. Model and SEARCH failures remain hard stops. No-success-read mission retains `no_verified_reads`.
- Preserve v4 count identities: SEARCH+READ=sourceReads, accepted+unpublished<=positive READ succeeded. UI layout/binary unchanged; no redundant package build.

## Task 1: Typed failure through durable research and accurate completion

**Owner:** one backend implementer; root owns docs and the final independent client-contract check.

**Files:** modify `pilot/open_web_reader_worker.py`, `open_web_reader.py`, `public_read_session.py`, `research_effect_contract.py`, `durable_research_dispatch.py`, `research_effect_journal.py`, `dynamic_research_runtime.py`, `read_tool_client.py`, `research_tools.py`, `codex_research_worker.py`; modify candidate publication only if a success-only guard is required. Add next available migration plus normal migration registry if required. Tests: affected existing `tests/test_open_web_reader.py`, `test_public_read_session.py`, `test_research_effect_contract.py`, `test_durable_research_dispatch.py`, `test_research_effect_journal_postgres.py`, `test_research_effect_gateway.py`, `test_dynamic_research_runtime.py`; inspect exact existing names before editing, no unrelated rewrites.

**Interfaces:** negative validator accepts `(kind,payload,result)`, returns a copied exact validated result or raises existing contract error; safe predicate returns false for anything unvalidated. Journal exposes/reuses a strict prior-effect check that binds resource/journal input, output, action/permit, scope and allowed result. Dynamic stop/status reuse that check, not separate code-only logic. No new public client request fields.

- [x] RED pure error cases and protocol path before implementation. Extend actual worker/MCP gateway fixture (not a pass-through mock) to perform a not-found READ followed by a successful different URL; same URL cache causes no second I/O.
- [x] Implement exact worker HTTP/MIME codes and carry them across parent/session/bridge/client/MCP/event allowlists. Keep other code branches and cancellation semantics conservative.
- [x] RED negative outcome validation/dispatcher tests. Implement strictly classified FAILED result with immutable hash/result/status receipt checks; finish or ACK uncertainty closes dispatcher without a second finish or retry. Success validator remains unchanged.
- [x] Add migration after checking latest number. Alter only journal final-result and resource-result CHECK constraints. Journal FAILED+result/hash permitted only for READ and exact allowed result shape; resource FAILED+hash only SOURCE_READ. Keep old FAILED/UNKNOWN null results and immutable triggers. New deferred constraint trigger on resource FAILED+hash verifies final same-transaction journal match across tenant/user/task/run/action/permit/input/status/output. Do not require final journal state in resource's immediate trigger; do not alter old migration files.
- [x] Implement `journal.finish` strict negative-result branch and replay verification; ordinary `ResearchResourceStore.finish` still rejects FAILED+hash. Prior-effect admission permits only successful or fully validated, paired known READ failures. New sequence of the same failed URL in the same run must not issue another permit or I/O.
- [x] RED restricted PG combined path: SEARCH, known failed READ, different successful READ, publication/assessment, final COMPLETED. Assert failed=1/succeeded=1/unknown=0, positive original/candidate only, no duplicate I/O from cache, and non-UNCERTAIN closeout. Keep external calls fixtures explicitly labeled.
- [x] Use the same strict hard-failure predicate for dynamic outstation/assessment/completion/status. Preserve total failed counts; only hard failures cause STOPPED. Positive READ queries/publication must reject negative results. Never relax canceled/expired/current-context checks.
- [x] Add affected boundary cases: unknown/legacy FAILED, invalid code/fields, wrong kind, mismatched resource/hash, ACK loss, revoked/canceled task and same-URL new sequence; demonstrate no subsequent effect I/O. Test deferred one-sided update rollback and valid atomic finish on actual restricted PG. Fixture names/DSN supplied by root; no production DB.
- [x] Run only changed/affected groups once green, `git diff --check`, commit owned implementation/tests. Report actual commands, RED/GREEN, exact SHA, migration and unresolved limits to `/tmp/yike-known-read-outcomes-implementation-report.md`. No provider calls or remote push by implementer.

## Task 2: Root integration, independent acceptance, publish

- [x] Root verifies actual v4 status containing one known failed and one successful read is accepted by existing desktop schema. Use existing integration test helper; fixture output is not real provider evidence.
- [x] Independent reviewer examines fixed full batch from base to final code SHA and both Spec/Quality verdicts. No repeated full suite; one fixer handles all material findings, one delta review.
- [x] Record concise evidence here, update taskbook/tools pointer, fetch/merge only if remote changed, merge accepted branch into main, push and verify exact remote parity. No production/Windows/real-user claims; no unchanged client rebuild.
- [x] Stop only owned disposable DB/processes. Next real experiment uses a different buyer-source hypothesis and diagnostics for precise failure codes, never old UNKNOWN replay. Continue to actual opportunity quality and authorized comment depth; full Goal remains active.

## Evidence

Final code: `e32df5aa4e0026a6819eaa6c6b155acfc2806b66`; initial implementation `cac85a8`, root client compatibility test `12dae93`. Independent whole-batch plus one correction review: Spec PASS / Quality PASS, zero open material findings. Prior real probe failures remain in `docs/qa/DYNAMIC_RESEARCH_REAL_PROBE_20260913.md`; this batch made no provider calls and does not replace those failures.

- RED: precise codes/negative contract/dispatcher 24 failures; actual local worker/bridge/MCP continuation 1 failure; restricted-PG negative finish/deferred pairing/mixed completion 3 failures. Strict status UNKNOWN/PENDING initially failed 2 checks and now uses the shared predicate.
- GREEN: restricted-PG atomic/deferred/mixed path 3 passed (7.39s), including actual backend v4 status consumed by `desktop/tests/knownReadOutcomeCompatibility.test.ts` (1 passed). SEARCH → one failed READ → same-URL cache → another successful READ → one candidate/assessment → COMPLETED; READ counts 2 issued / 1 succeeded / 1 failed / 0 unknown, RECORDED closeout. Network/model inputs are local fixtures, not real buyers.
- Final affected run: 353 passed, 1 failed, 1 deselected (166.75s). The failure was an existing publication-tamper test unable to ALTER a table while the new deferred trigger unnecessarily queued successful resource updates. Migration 143 trigger is now scheduled only for FAILED with a hash; immutable guards and the old test were not relaxed.
- Final delta: strict status, both publication tamper cases, deferred one-sided rollback and atomic negative finish/replay: 6 passed, 81 deselected (11.75s). The unpublished migration was reapplied only in the owned disposable database after removing its own schema_meta checksum row; no business data was deleted, old migrations unchanged. Do not describe these separate runs as one all-green suite.
- Additional targeted evidence: negative/admission boundaries 32 passed; session plus actual local worker/bridge/MCP 17 passed. Ordinary resource finish still rejects FAILED+hash; hard failures and lost ACK close execution without subsequent I/O. Failed originals cannot become candidates.
- Root inspected implementation/report and `git diff --check bd1356b..cac85a8` exited 0. No unchanged client build, production migration, Windows acceptance, external message, or sustained lead-quality claim.

Full local implementation/test evidence: `/tmp/yike-known-read-outcomes-implementation-report.md`, `/tmp/yike-known-read-outcomes-test-evidence.log`. This committed summary remains the portable evidence pointer after temporary files expire.

### Final independent acceptance

The sole initial P2 was malformed/missing MIME being treated as explicitly unsupported. `e32df5a` adds a narrow type/subtype guard; invalid MIME remains a hard failure, valid PDF remains known-negative. RED10 failed/1 passed; correction21 passed (0.21s). Root independently ran the 11 malformed/actual-decoder continuation cases: 11 passed,62 deselected (0.26s). Whole-batch and one delta review accepted final code; no further material issue. Reviewer report `/tmp/yike-known-read-outcomes-final-review.md`.

Owned disposable container `yike-known-read-pg-20260913` stopped and auto-removal verified; other environments untouched. No active batch processes, build, provider call or production change. Accepted branch fast-forward merged into main and pushed: `28b0fa0f248e0d0f9088417d6bf955d0e0194bc2`, clean local/origin/live SHA parity verified. This final closeout is documentation-only; full product Goal remains ACTIVE.
