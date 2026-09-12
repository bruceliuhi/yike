# Research Page Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this single integrated task with one independent batch review.

**Goal:** Keep research background pages out of candidate assessment while preserving source evidence and auditable page decisions.

**Architecture:** Strict final JSON selection is checked against successful durable READs. Existing candidate batch execution_context stores versioned decisions; BACKGROUND creates a zero-item receipt, ASSESS retains ordinary review. No new classifier calls, tables or columns; migration144 replaces the existing binding trigger so the new 22-key context is evidence-bound while the legacy20 path remains unchanged.

**Tech Stack:** Python, existing Codex worker, PostgreSQL batch journal, pytest.

## Global Constraints

All exact limits, JSON keys, decision/reason values and authorization boundaries in the paired specification `docs/superpowers/specs/2026-09-13-research-page-selection-design.md` are binding. No real model calls, network research, credentials, sends or production operations in implementation. Preserve legacy internal publish calls when selection is absent; explicit invalid selection fails closed. Parent owns taskbook/integration and Git push.

### Task 1: Evidence-bound page selection vertical slice

**Files:** create `pilot/research_page_selection.py`, `tests/test_research_page_selection.py`; modify `pilot/research_context.py`, `pilot/codex_research_worker.py`, `pilot/dynamic_research_runtime.py`, `pilot/dynamic_research_candidates.py` and their focused tests. Adjust existing synthetic dynamic HTTP fixtures only where the new mission result contract requires it.

Also modify `desktop/src/renderer/domain/researchProgressPresentation.ts` and its existing unit tests: dynamic completed/zero-candidate with successful reads must distinguish read pages from selected candidates; the new invalid-selection stop code explains incomplete screening with originals retained. No UI layout/schema/build change.

**Interfaces:** New module exports fixed `SELECTION_INSTRUCTIONS`, strict `parse_page_selection(summary: str, evidences: list[dict]) -> list[dict]` and `validate_page_selection(decision: dict, evidence: dict) -> dict` using `ExecutionRuntimeError('research_selection_invalid',409)`. Parsed decisions use each page's exact schema plus `schema_version: research-page-selection-v1`; module returns detached values. Dynamic candidate `publish` gains keyword-only `selection` with a private omitted sentinel; runtime must always pass validated decisions.

- [ ] Write RED pure parser tests for valid mixed pages; extra/duplicate JSON keys; truncated/fenced JSON; invalid enums/types/size; URL/hash/quote mismatch; missing/duplicate/unread pages; duplicate durable same-version pages; budget/identity uncertainty instruction.
- [ ] Implement strict parsing/validation and bounded versioned instructions exactly as spec. Do not add hostname or keyword classification. Example fixture shape:

```python
decision = {'schema_version':'research-page-selection-v1', 'url':page['url'],
            'content_sha256':page['content_sha256'], 'decision':'BACKGROUND',
            'reason':'INDEX', 'quote':page['text'][:100]}
```

- [ ] Wire compiled instructions/version and contextual message limit. Tests show same returned instruction bytes/hash, no secret relaxation, legacy no-context message cap unchanged, contextual bounded large JSON supported.
- [ ] Add PG RED for selection publication, zero-item background, original preservation, records_used unchanged, conflicting selection replay and quote mismatch. Implement optional selection validation against journal result before receipt replay; include decision+skip count in fingerprint context, preserve all existing locks/checks. Omitted legacy context retains original shape.
- [ ] Wire runtime: require matching research_binding, fetch successful READ evidence ordered by sequence, validate the complete summary before any publish, pass selection for every page, assess only receipts with items. Invalid result stops with fixed code, never all-selected fallback. Update synthetic missions to return explicit binding and JSON, not just status=COMPLETED.
- [ ] Run pure tests first, then isolated restricted PG targeted `tests/test_dynamic_research_candidates_postgres.py tests/test_dynamic_research_runtime.py tests/test_desktop_dynamic_research_http_postgres.py`; parent provisions a unique test container and supplies local fixture URLs. Capture first failures and final result, no full suite or repeated unchanged build.
- [ ] Commit code/tests/spec/plan on existing short branch; report exact SHA, test commands/results and boundaries to `/tmp/yike-page-selection-implementation.md`. Parent runs one independent Spec/Quality/architecture review and normal integration.

## Evidence

### Implementation and independent review

Implemented at `468afed0bc870cbcf29818b1f8739bd572ae1e5f`; two review fixes at `9cda1fc75f9445be5d754c40420a9622bd59f4a0`. All Task 1 implementation steps above are complete. Independent whole-batch review initially required two P2 changes; independent exact-delta review at `9cda1fc` is **Spec PASS / Quality PASS**. This is not production or opportunity-quality acceptance. Full Goal remains active.

- Successful durable READs are all accounted for in strict final JSON, checked before any candidate publication and again against the journal in the publish transaction. BACKGROUND retains original evidence and a zero-item batch without consuming candidate records or ordinary assessment calls. ASSESS remains an unapproved whole-page candidate with unknown author/date until the existing evidence/review path establishes them.
- Compiled instructions/version/hash and contextual final-message bounds are updated. Existing legacy publication and worker paths remain. Migration144 extends the existing trigger's exact20/22-key validation, with no new table, column or grant.
- Client text distinguishes pages read, candidates selected and incomplete screening; no new layout, build or per-page review interface is claimed.

### Focused verification and failures retained

Commands ran in the owned implementation worktree using `.venv/bin/pytest`; PostgreSQL tests used an isolated local PostgreSQL16 container, restricted fixture roles and synthetic customer data. No shared/production database was used.

| Scope | Captured result |
| --- | --- |
| `tests/test_research_page_selection.py tests/test_research_context.py tests/test_codex_research_worker.py` at initial implementation | 139 passed, 18.74s |
| `tests/test_dynamic_research_candidates_postgres.py tests/test_dynamic_research_runtime.py tests/test_desktop_dynamic_research_http_postgres.py` | 40 passed, 60.98s, no skips |
| `desktop`: `npm test -- tests/researchProgressPresentation.test.ts` | 26 passed, 241ms |
| Independent legacy actual read/publish/recovery regression | 1 passed, 2.40s |
| Independent synthetic mixed ASSESS/BACKGROUND runtime | 1 passed, 3.73s; accepted/analyzed=1, two receipts, one assessment call |
| New fix-only oversized-integer parser / runtime / direct SQL-trigger checks | each 1 passed; 0.11s / 2.58s / 2.59s |

Initial REDs exposed missing parser/contract, old trigger exact-key rejection and stale synthetic mission outputs. An initial PG run had 4 failures/36 passes: three old expectations published before terminal-effect checks; one synthetic whole-page assessor incorrectly invented author intent. Fixtures now preserve UNKNOWN attribution and require zero publication on incomplete durable effects. One fixture indentation error was corrected before the captured final run. An earlier tool wrapper lost a test process's output; that process was allowed to terminate before the captured rerun, with no success claim from the missing output. UI initially had 2 failures/24 passes, then the result above.

Independent review found SQL space-only trimming admitted whitespace-only quotes and a 5,000-digit JSON integer escaped as plain ValueError. Both were fixed together: SQL now matches all29 Python whitespace characters without modifying literal quotes; decoder conversion failures map to `research_selection_invalid`, with the interpreter digit limit unchanged. The first SQL negative-test harness stopped before the trigger because protected READs reject some control characters; the corrected synthetic, rollback-only journal mutation reached the trigger. Independent re-review compared installed SQL against every Python Unicode code point (exact29 parity), checked nonblank controls and the original integer reproduction. No unchanged full test groups were rerun for these fixes.

The suspected legacy journal-SELECT compatibility defect was **not reproduced**: a valid legacy20 receipt succeeded under a role without journal SELECT. No speculative ACL rewrite was made.

Local detailed author and independent reports: `/tmp/yike-page-selection-implementation.md`, `/tmp/yike-page-selection-review.md`. These are audit aids, not customer deliverables or evidence of new leads. Real-source validation is recorded separately below when terminal; no login, outreach, build or deployment is part of this batch.

### New known-source real probe — STOPPED, not selection validation

At code `9cda1fc75f9445be5d754c40420a9622bd59f4a0`, a new synthetic tenant/task used the actual Codex worker, Doubao model, Serper search, anonymous reader, restricted PostgreSQL role and in-process customer HTTP API. It was limited to the known V2EX project index `https://www.v2ex.com/go/outsourcing` and known calibration post `https://www.v2ex.com/t/1234774`; no new-lead claim, same-condition A/B, prior UNKNOWN replay, login or outreach. Bounds: 8 source actions, 3 minutes, 8 research model calls, 4 candidate records. No bypass of previously blocked LINUX DO/电鸭/飞书 paths.

- Started `2026-09-13 07:30:54+08`; task `79ffcf02-1a3d-456d-bfc0-dc3e66124c00`, run `85872133-5183-41ea-b5cf-6e8571492ccc`.
- Actual result after58.70s: **STOPPED / no_verified_reads**, four successful searches, four successful research model calls, zero durable READs, accepted/analyzed0. Candidate receipts and ordinary assessment diagnostics are both empty. Test terminal assertion correctly failed (`1 failed in60.97s`); it was not retried.
- Queries in order: `v2ex.com/t/1234774`; `v2ex.com/go/outsourcing`; `site:v2ex.com 1234774 相机 标定`; `site:v2ex.com go/outsourcing 外包 项目`. Result counts were8/10/0/10. Neither exact target URL was returned as a result; the index appeared only in snippets. Those snippets are not a verified read or a discovered page link.
- Mission diagnostics recorded `invalid_url` for both attempted target reads. `PublicReadSession.read()` rejects URLs not in the search-result permission set or successful-read discovered links before issuing READ. Merely putting a URL in a description/entry hint does not add it to those sets. Worker consequently returned `no_verified_reads`. This run did **not** reach page selection, and does not demonstrate either a selection failure or live selection success. It also did not establish that the target websites were inaccessible.
- Research usage: input53114 (of which cached26224), output651; total53765 tokens. These are provider-measured token counts, not a monetary bill. Settlement remainedPENDING and resource closeoutOPEN; no completed billing claim.
- Safe local observations: `/tmp/yike-page-selection-real-20260913.json`, `/tmp/yike-page-selection-receipts-20260913.json`, `/tmp/yike-page-selection-assessment-20260913.json`. Raw provider transcripts and credentials were not exported. The harness was `/tmp/test_yike_page_selection_real_20260913.py`; owned fixture data were isolated from production.

**Next substantive gap:** explicitly confirmed/host-catalog public entry URLs need a version-bound, safe seed-reading contract, not another instruction to search until those same URLs appear. Do not automatically whitelist arbitrary URLs from model prose or fetched content; retain public-URL/SSRF/redirect checks, task permissions, budget accounting, source blocks and durable READ evidence. Design and implement this next, then run a new bounded task. Keep broader new-demand supply/quality comparison separate from this known-source integration probe. Do not repeat the same search-only task or claim the personal Skill's effectiveness has been restored.
