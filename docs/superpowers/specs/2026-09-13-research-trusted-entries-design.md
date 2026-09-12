# Version-bound trusted public research entries

Status: implementation authorized within full V02 under AUTHORITY.md's 2026-09-11 autonomous technical-design approval. Baseline `5b7aa48a701791197e41a8c983489eb26d55e56e`. No new product scope, production enablement or outreach authorization.

## Problem and choice

The previous real task searched four times but could not read two known URLs because search did not return them. It stopped before selection. Prompt hints alone are not URL permission. Keep open-web discovery, but allow bounded host-derived entry URLs to start an actual read without needing the search engine to rediscover that URL.

Options: repeated exact searches preserve the failing dependency; arbitrary URLs extracted from prose would erase the provenance boundary; **repository catalog plus existing owner-scoped KNOWN history** reuses already bound host context without adding a new public API or model-controlled permission field. Choose the third. Arbitrary customer-provided seed input requires a separately explicit configuration flow and is not pretended to exist here.

## Entry contract

- Maximum20 unique canonical public URLs. Use existing `normalize_public_url` checks; canonical equality, strings only, reject malformed/credential/private/unsafe inputs, never broaden to host/domain wildcards. Empty tuple is valid and keeps legacy behavior.
- Derive the list inside `compile_research_context`, never from description, keywords, model output, search snippets or unparsed text. Start with the three public HTML entries derived from existing `research_source_catalog` (not its API endpoints); append `source_urls` of validated history entries whose state is KNOWN, in context order. Remove any exact URL mentioned by EXCLUDED, CLOSED or CONTACTED history before stable deduplication and truncation to20. History is loaded through existing tenant/owner/profile scope and frozen in the context. No other customer's or global research queue is loaded.
- Catalog entries are optional navigation choices, not a universal industry source or automatic buyer evidence. Customer industry, exclusions, freshness and known access restrictions remain part of the research instructions. Exact URL removal is not a new platform-wide blacklist or permission to re-enter a blocked platform via a different URL.
- Return derived `entry_urls` alongside existing compiler output. Append `/trusted-entries-v1` to both rule versions; fixed selection/permission semantics and catalog entries are included in compiled instructions/hash, while the existing context hash binds history and states. No DB migration or binding-schema change. Changed rules continue to reject silent continuation of old stored contexts.

## Runtime and tools

- Activate seeds only for a valid compiled, controlled (`effect_dispatcher` supplied) search-enabled research mission. No-context, unbound and uncontrolled search/read workers retain their old behavior and success criteria.
- Pass the exact validated list through the clean MCP process environment as JSON (`YIKE_PUBLIC_ENTRY_URLS`), not through model-authored arguments. Seeded CLI setup requires both configured host search and read clients; malformed or partial configuration fails closed. Maximum encoded seed JSON45KiB. Model tools keep the same schemas; there is no add-permission tool.
- Apply the same list at all three existing boundaries: MCP `build_server` initial discovered set, host `PublicReadSession` allowed-url callback and `_ReadEvents` initial authorized URLs. Reuse a small shared validator, with detached immutable tuples for host use. Neither failed reads nor free-form summaries add permission. Successful page links and search results retain existing behavior.
- For such seeded tasks, instructions permit reading a relevant entry first or searching for a new source; neither action is forced. Zero SEARCH plus successful verified READ can complete. Keep the legacy mandatory-search condition when no trusted entries are active; every successful mission still requires an actual verified READ and runtime still checks matching binding, durable effects and strict complete page selection.
- Seed listing itself is not a SEARCH or READ result. Actual seed READ consumes existing shared source allowance and has normal per-read limits, deadline, cancellation, same-run cache and durable journal/unknown-result handling. Do not prefetch in a hidden unmetered path or fabricate SEARCH/READ receipts. Background selection still creates a zero-item receipt; known history remains known, not net-new.
- Public URL, DNS/SSRF, redirect, credential, unsupported-content and platform restriction gates stay unchanged. No login, retry bypass, sending, extra model classifier, provider switch, schema/table/grant, frontend layout or deployment change.

## Verification

Use focused RED/GREEN tests for deterministic compiler derivation/exclusion/cap/hash, invalid transport inputs, exact-entry read-before-search through all three gates, source-link navigation, legacy missing-search rejection, seeded no-read rejection and cancellation/limits. Cover one complete controlled seeded worker path and one restricted-PG customer runtime path with durable background/assess selections; synthetic evidence proves wiring only. Independent exact-SHA batch review precedes a new bounded real task. The real task starts at a catalog index and can follow one relevant returned original; no fixed original is injected through prose to fake a seed, and previously blocked paths remain excluded. Report a stop faithfully, without retrying the prior task or claiming recovered Skill quality from tests.
