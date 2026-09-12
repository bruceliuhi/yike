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

Not implemented or validated yet. Full Goal remains active.
