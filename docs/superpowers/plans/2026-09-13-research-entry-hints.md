# Research Entry Hints Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this single task and perform one independent batch review.

**Goal:** Reuse verified source-entry knowledge in dynamic research without granting access or changing confirmed customer strategies.

**Architecture:** The existing closed source catalog supplies advisory public page entries, not API endpoints or candidate evidence. Research context appends those hints to its host instructions and hashes the complete instruction text. Search/link discovery and dedicated connector authorization remain unchanged.

**Tech Stack:** Python, existing Codex research worker, pytest.

## Global Constraints

- Full V02 remains active; this batch only improves research context. No deployment, external messages, new credentials, paid research or platform bypass.
- Preserve existing catalog source IDs, endpoint/input hashes, source plans and confirmed strategy snapshots. No new connector.
- V2EX hints are conditional technology-community examples, not every industry's default source or an exhaustive platform catalog.
- Hints grant neither URL read permission nor evidence status; existing search/link, authorization, budget, tenant and UNKNOWN boundaries remain authoritative.
- Bind all delivered research instruction bytes, including hints, to rule_sha256. A changed rule requires fresh context binding; do not silently reinterpret old runs.
- Tests prove wiring and contracts, not improved lead quality or commercial success.

## Design decision

The local comparison read the project node `/go/outsourcing` successfully, unlike a workforce-heavy `/tag/外包` page. Existing `v2ex-outsourcing-authors-v1` already covers the project node, so duplicating a connector is rejected. Trusted-seed URL permission changes and candidate-publication selection are outside this batch. A hint may guide an authorized search, but guessed URLs still cannot be read.

### Task 1: Catalog advisory context and exact instruction binding

**Files:**
- Modify: `pilot/research_source_catalog.py` — add `research_entry_hints() -> str` using existing catalog entries.
- Modify: `pilot/research_context.py` — append catalog hints and bind full instructions.
- Test: `tests/test_research_context.py` and existing worker context wiring test.

**Interfaces:** `research_entry_hints()` returns a deterministic repository-owned string. `compile_research_context(value)` retains its exact return and binding keys; context/strategy hashes are unchanged. Rule version gains `/entry-hints-v1` for both context schema versions.

- [x] Write and run failing tests: instruction hints include the existing three IDs and public entry URLs but no `/api/`; changed hint text changes rule hash and not context hash; full instruction SHA equals binding; non-AI scope remains in context and hints explicitly conditional; existing worker receives the same compiled instructions.

```python
import hashlib
assert result['binding']['rule_sha256'] == hashlib.sha256(
    result['instructions'].encode('utf-8')).hexdigest()
```

- [x] Add catalog rendering using `SOURCE_IDS` and `research_source(source_id).node`. Map node `None` to `https://www.v2ex.com/recent`, otherwise to `https://www.v2ex.com/go/` plus the existing node. Explain latest topics include ads/non-buyers; qna is problem discussion without assumed payment; outsourcing includes quotes but requires checking author time, status and terms. State node/tag difference, conditional industry fit, search/link prerequisite, no login/retry on access restriction, no exhaustive claim.
- [x] Compile instructions once, append hints after host header, compute `sha256(instructions.encode('utf-8')).hexdigest()` for rule binding and return those same bytes. Preserve source document size limits and old catalog hashes; remove only now-unused private document digest computation if appropriate.
- [x] Run `.venv/bin/python -m pytest -q tests/test_research_context.py tests/test_codex_research_worker.py` plus existing source-catalog unit tests if a separate file exists. Use existing tests for stable connector behavior; no full suite/build/live API calls.
- [x] Commit the code/tests/plan. Independent reviewer checks exact range against constraints; fix all material findings as one delta batch.
- [ ] Parent updates taskbook/integration evidence and pushes normal `main` after review. Lead queue remains SEND_READY 0 unless new real evidence exists.

## Evidence

Initial RED: the focused 5-test selection failed because the hint renderer and version suffix did not exist and worker instructions lacked the catalog IDs. After the minimal implementation, `.venv/bin/python -m pytest -q tests/test_research_context.py tests/test_codex_research_worker.py tests/test_research_public_reader.py` passed `140 passed in 19.25s`. Independent review remains with the parent task; no live research, deployment, outreach, or new research outcome is claimed.
