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

### Implementation and independent review

Implemented at `0f2a8feb257dcca35c53719961758b5f86b690a5`; exact-list guidance clarified in spec at `82f8c40`; two-line production review correction at `fc1638339340b27a6d9a53514c7333fa661db82b`. Independent whole-batch review initially CHANGES_REQUESTED (P2 guidance contradiction, P3 decoder error consistency), then **Spec PASS / Quality PASS** at exact `fc1638339340b27a6d9a53514c7333fa661db82b`. All Task1 implementation steps are complete; this is code/contract acceptance, not deployment or live supply quality.

Derived immutable entries now cross compiler, host callback, clean MCP process, tool discovered set, event validation and explicit model guidance. Only compiled+controlled+search-enabled runs activate seeds; actual seed READ retains original source guards and durable accounting. Catalog guidance is advisory, and zero-search completion still requires actual successful original reading. No new API, DB table/grant, frontend layout, login, sending, build or deployment.

### Focused tests and retained failures

- Core `.venv/bin/pytest -q tests/test_research_entry_urls.py tests/test_research_context.py tests/test_research_tools.py tests/test_codex_research_worker.py`:155 passed in22.65s.
- PublicReadSession split checks:12 passed/3 deselected in0.16s, then three constructor cases explicitly run immediately:3 passed in0.10s. The combined initial command had1 failed/166 passed, because an unchanged `time.monotonic()+1801` parameter is constructed during collection and becomes valid after more than1s; independent deterministic clock check confirmed this old fixture issue. This is not a claim that the combined command passed, and no production deadline logic was relaxed.
- Owned restricted PostgreSQL only: `test_trusted_entry_only_runtime_has_durable_read_and_zero_search_receipts` and `test_history_is_same_business_owner_scoped_known_not_draft_contact`:2 passed in4.08s. Synthetic durable seed READ, zero SEARCH rows, background zero-item batch, no ordinary assessment and completed runtime; scoped KNOWN history contributes the expected URL. These are not live model/MCP proof.
- Independent uncovered actual host-session+durable-dispatch synthetic probe: seed read succeeded and cached, second seed hit the read ceiling, ungranted nearby URL denied; one reader call and one successful durable finish. No network/production DB involved.
- Initial7 REDs included missing features and one test-helper argument mistake; corrected worker tests then failed on the intended missing behavior. First GREEN attempt exposed an uninitialized `entries` regression on legacy workers, fixed to empty default before final results.
- Review fixes: P2 RED1 failed/2 passed and P3 RED1 failed; final decoder subset2 passed in0.10s and guidance/compiler/worker subset9 passed in2.40s. Parser limit unchanged. Independent review parsed the complete active JSON, confirmed negative removal and legacy instruction consistency, then independently checked the5000-digit decoder input. No unchanged core/PG groups were rerun for the fixes.
- Compile and diff checks passed. Local author/review reports are `/tmp/yike-trusted-entries-implementation.md` and `/tmp/yike-trusted-entries-review.md`.

Nonblocking test-quality note: one new negative-guidance regression splits at the first period (inside a URL), so its own substring assertion covers only a prefix. Independent full-JSON decoding and existing full transport assertions cover actual behavior. Replace that assertion with `JSONDecoder.raw_decode` in a later test-only cleanup; do not call it independent full-list coverage.

Previous real source failure remains in the page-selection plan; new actual-provider evidence is recorded separately below after its terminal result. Full V02 Goal remains active.

### New real task — direct entry and navigation succeeded; result validation stopped

Code `fc1638339340b27a6d9a53514c7333fa661db82b`, started `2026-09-13 07:53:32+08`. New synthetic customer task `8ed18b2e-305b-4c10-bc45-d250bd09eb8a`, run `910b9817-4737-42eb-9ec4-8bab3b40e86d`. Used actual Codex+Doubao, anonymous reader, durable restricted-PG dispatch and in-process customer HTTP API. Bounds remained8 sources/3minutes/8model calls/4records; no known original URL was injected as permission through prose. The task was limited to a catalog directory and at most one returned original, with previous excluded/blocked paths unchanged.

- **0 searches, 2 successful durable READs, 3 successful research model calls.** Direct read `https://www.v2ex.com/go/outsourcing` returned “V2EX › 外包”,1877 extracted characters; following its returned link read `https://www.v2ex.com/t/1239289`, “安卓自动化脚本定制开发”,620 characters. This proves actual catalog→original navigation without search rediscovery under the new controlled worker; it is not an author/intent/date qualification of the second page.
- Worker mission reportedCOMPLETED, but customer runtime ended **STOPPED/research_selection_invalid** after41.35s, with accepted/analyzed0, two unpublished originals and no candidate receipts or ordinary assessment calls. Captured pytest result `1 failed in43.72s` correctly retains the terminal stop. The previous no_verified_reads gap did not recur; overall task success and real page-selection success are **not proven**.
- Provider usage:39382 input tokens (24176cached) and1071 output, total40453; settlementPENDING, resource closeoutOPEN. Not a billed amount, production tariff or efficiency A/B claim.
- Raw final model summary and returned binding were not captured by this probe's observation wrapper. The fixed stop code covers both binding and final selection validation; therefore the exact rejected field/cause is **unknown**. Do not claim a malformed hash, bad JSON, quote mismatch or model-quality root cause without evidence. No automatic retry was made.
- Local artifacts: `/tmp/yike-trusted-entries-real-20260913.json`, `/tmp/yike-trusted-entries-receipts-20260913.json`, `/tmp/yike-trusted-entries-assessment-20260913.json`; the last two are empty. They omit credentials and raw provider transcripts. Harness: `/tmp/test_yike_trusted_entries_real_20260913.py`. Public original snapshots were retained in the safe artifact, not promoted to customer opportunities.

**Next:** first make binding/selection failures diagnosable with safe fixed reason categories and minimal structural evidence, keeping public error compatibility and avoiding raw provider/private text logs. Use the two retained original snapshots for offline checks; a new bounded diagnostic task may capture the previously missing failure evidence, but do not replay the old task or pay for repeated broad searches. Do not relax quote/hash/source checks or fallback to publishing every page just to complete. Then verify actual selection and ordinary assessment before new-demand supply/quality comparison. No new qualified lead, customer UAT, build, production deployment or outreach is claimed; full Goal ACTIVE.
