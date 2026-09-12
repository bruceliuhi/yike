# Trusted Public Entries Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development for one integrated implementation task and independent batch review.

**Goal:** A bound customer research task can actually read trusted public entries without needing their rediscovery in search results.

**Architecture:** Compiler derives entries from the existing public catalog and scoped KNOWN history. One validated immutable list crosses existing MCP, host-read and event-observation gates; all actual reads retain durable metering and strict page selection.

**Tech Stack:** Python, existing Codex/MCP worker, PostgreSQL runtime fixtures, pytest.

## Global Constraints

The paired `2026-09-13-research-trusted-entries-design.md` is binding in full. Maximum20 canonical URLs and45KiB encoded JSON. Activation requires valid compiled+controlled+search-enabled context. No-context/uncontrolled legacy paths keep their existing behavior. No prose URL extraction, wildcard permission, new DB/API/frontend layout, grants, source-block bypass, credentials, network research or deployment during implementation. Parent owns test DB, real probe and main integration. Use existing isolated worktree; do not switch branches or touch other worktrees. Keep the full V02 goal active.

### Task 1: Bound trusted-entry vertical slice

**Files:** create `pilot/research_entry_urls.py`, `tests/test_research_entry_urls.py`; modify `pilot/research_source_catalog.py`, `pilot/research_context.py`, `pilot/codex_research_worker.py`, `pilot/research_tools.py` and their existing focused tests. Modify `pilot/public_read_session.py` only if needed to wire the existing callback safely, not to loosen its guards. Add focused evidence in `tests/test_dynamic_research_runtime.py` and `tests/test_customer_research_context_postgres.py` where the existing fixtures support runtime and history integration. No unrelated module refactoring.

**Interfaces:**
- Shared validator `validate_entry_urls(value) -> tuple[str, ...]`: list/tuple only, at most20 distinct canonical URLs, empty allowed, reject duplicates/malformed/noncanonical with fixed ValueError and no echoed input. JSON transport decoding accepts list only and checks45KiB before parse. Inputs do not get silently broadened or normalized into a different URL.
- Catalog helper `research_public_entry_urls() -> tuple[str, ...]`: reuse `SOURCE_IDS` and `research_source()` node mapping; return public HTML entries. `research_entry_hints()` consumes it so permission list and displayed URLs cannot drift.
- Compiler output adds `entry_urls` from a deterministic helper over the validated context; negative states remove exact URLs before dedupe/cap. Existing binding fields unchanged. Instructions/version bind the new semantics as specified.
- `build_server(..., entry_urls=())` validates the list and seeds its local discovered set. CLI reads only the host env JSON and rejects seed activation without both host clients. `_ReadEvents(..., entry_urls=())` accepts only exact allowed seed results, never treats entries as successful searches. Worker supplies seeds from compiled output only under the activation condition and changes `_execute` completion check only for those seeded events.

- [ ] **Step 1: RED derivation and permission tests.** Example required behavior:

```python
assert validate_entry_urls(["https://www.v2ex.com/go/outsourcing"]) == ("https://www.v2ex.com/go/outsourcing",)
# A KNOWN history URL is included; the same URL anywhere in CLOSED/CONTACTED/EXCLUDED is omitted.
# A URL appearing only in seller_description/query_seeds is not included.
# Catalog and history order stable, cap20, compiled hash/version changes with rule changes.
```

Add actual assertions using existing context fixtures, MCP call helpers and `_ReadEvents` events: a seeded read before any search succeeds, an unseeded nearby URL still fails, failed read never adds its links, fake success for ungranted URL is rejected, empty seeds preserve old conditions. Run new focused tests to capture expected failures before production edits.

- [ ] **Step 2: Compiler and transport implementation.** Follow this projection (after existing context validation), using the shared canonical validator:

```python
blocked = {url for item in validated["history"] if item["state"] != "KNOWN" for url in item["source_urls"]}
ordered = list(research_public_entry_urls()) + [url for item in validated["history"] if item["state"] == "KNOWN" for url in item["source_urls"]]
entries = tuple(dict.fromkeys(url for url in ordered if url not in blocked))[:20]
```

Return detached entries; bind algorithm/version/catalog through instructions. Use `json.dumps(list(entries), separators=(",", ":"))` for the clean process env; reject malformed JSON before CLI tool setup. Do not expose provider keys in outputs or extend tool argument schemas.

- [ ] **Step 3: Wire all three gates and completion.** Host callback allows `url in entries or search_service.allows_read(url)`; existing `PublicReadSession` still validates/dispatches/meters. Pass the same entries into MCP args/env and event validator. `if events.search_enabled and not events.searches and not events.entry_urls: ...no_verified_searches`; the subsequent actual-READ requirement remains. Make seeded instruction text coherent with catalog hints, with no hidden forced search requirement. Existing unseeded tests must continue passing.

- [ ] **Step 4: Focused integration GREEN.** Run `.venv/bin/pytest -q tests/test_research_entry_urls.py tests/test_research_context.py tests/test_research_tools.py tests/test_codex_research_worker.py tests/test_public_read_session.py` (confirm existing filenames first). Add at least one controlled worker test proving seed transport to actual host read dispatch and final event validation; preserve budget/cancel failures. Parent supplies isolated DB for only affected customer-context/runtime cases. Seed-only completed runtime must have real synthetic durable READs, zero SEARCH receipts, correct selected/background publication and no invented totals. Negative tests assert zero IO/publication for invalid/unbound/denied setup.

- [ ] **Step 5: Commit and report.** Commit code/tests on current short branch, not push. Write exact SHA, changed files, captured RED/GREEN commands/results, failures and concerns to the report path supplied by parent. Run `git diff --check`. Do not rerun prior139/40/26 suites wholesale, call models/network or build clients. Parent performs one exact-SHA independent architecture/spec/quality review and a separate real probe after fixes.

## Evidence

Implementation pending. Previous real source failure is retained in the page-selection plan. This plan alone is not progress on live collection or supply quality.
