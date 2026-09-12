# Open Web Research Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Whole-batch independent review replaces redundant per-file reviews under repository instructions.

**Goal:** Provide an executable Codex discovery -> independently read arbitrary public HTTPS sources -> unreviewed evidence pipeline, without per-site adapters.

**Architecture:** Separate trusted reader, Codex process adapter, and research orchestration. Preserve the existing task, resource and review services; never synthesize authority from model output.

**Tech Stack:** Python 3.11–3.12, installed Codex CLI, stdlib, existing Pydantic/candidate contracts; no new provider SDK required.

**Runtime decision resolved:** User explicitly prefers the open-source Codex Harness, authorizes use of existing domestic-model API keys for compatibility validation, and asks to develop through delivery/launch. Task 2 proceeds with this preference, with actual provider/tool compatibility checked before customer activation. Customers never require Codex installation/account/key. Search and original reading use independent tools, not an assumption of built-in search support. Full V02 Goal and real acceptance standards remain unchanged.

## Global Constraints

- No private platform sessions, inherited personal plugins/configuration, external sends or production activation.
- Domain-independent anonymous HTTPS reader, DNS-pinned TLS, no redirects/retries, 20-second whole-call ceiling, 1MiB wire body, 60,000-character extracted text.
- Actual process/search events, model suggestions, independent reads and human review remain distinct.
- Existing fixed-index mode unchanged; new internal executor is not yet a customer API, persistent budget integration or full Goal completion.
- Only targeted tests and one necessary independent batch review. Do not repeat existing full suites/builds.

### Task 1: Generic public page reader

**Files:** create `pilot/open_web_reader.py`, `pilot/open_web_reader_worker.py`, `tests/test_open_web_reader.py`.

**Interfaces:** `read_public_page(url: str, *, deadline: datetime) -> dict` returns exactly `url,title,text,observed_at,content_sha256,read_scope`; raises `PublicReadError(code)` with fixed `invalid_url`, `unavailable`, `unsupported_content`, `too_large`, `timeout`. `title` nullable; hash SHA256 of UTF8 extracted text; read_scope `PUBLIC_PAGE_TEXT`. URL stays requested normalized public URL, publication/identity unknown. Parent deadline must be timezone-aware.

- [ ] Write failing tests for normal HTML/plaintext and a never-enumerated public domain, blocked DNS mixed addresses, TLS hostname preservation with pinned socket, redirect refusal, body/decoded text bounds, hidden HTML, invalid UTF8/charset policy, native DNS timeout and process reaping. Tests may replace transport/DNS only, not skip real extraction or validation.
- [ ] Run `uv run --frozen --extra dev pytest -q tests/test_open_web_reader.py` and record expected missing implementation failure.
- [ ] Implement one bounded child operation using existing `_validate_url(url,'PUBLIC_WEB')`, stdlib HTTPS/socket/HTMLParser and strict bounded stdin/stdout. Never use unvalidated URL in direct httpx/requests fallback. Keep process and extraction concerns focused; no new public CLI/customer endpoint.
- [ ] Repeat the exact tests, inspect results, commit only owned files and report command/results plus limitations.

### Task 2: Codex discovery and controller (root)

**Files:** create `pilot/codex_discovery.py`, `pilot/open_web_research.py`, `tests/test_codex_discovery.py`, `tests/test_open_web_research.py`; add packaged research method only if behavioral baseline demonstrates needed guidance.

**Interfaces:** a validated immutable mission carries public description, exclusions, source/search ceilings and duration; `CodexDiscovery.discover(mission, *, deadline)` returns URL suggestions and actual completed search events. `research_public_web(mission, *, discovery, reader=read_public_page, cancelled=lambda:False)` returns unreviewed evidence plus structured read failures. No writes/approval authority or direct resource store mutation in these adapters.

- [ ] Test subprocess with executable fixture emitting representative Codex JSONL: completed search, terminal final JSON, usage; no-search hallucination, malformed/huge output, failed turn, timeout, credential/argv/config isolation, too many searches.
- [ ] Implement actual `codex exec` adapter with explicit binary/model/secret, new empty private runtime home/workspace, read-only capabilities and bounded process I/O. Never read existing auth/config or launch an actual paid run during tests.
- [ ] Test controller across two unknown domains, repeated URLs, failures, deadline/cancel, no model text treated as raw evidence. Use real CandidateRecord validation for PAGE shape where feasible.
- [ ] Implement orchestration and document exact internal invocation and remaining task/transaction integration gate; run only changed tests.

### Task 3: Independent review and integration

- [ ] Review final concrete code diff plus test evidence against spec. Fix findings with covering regressions and one delta review.
- [ ] Update taskbook with actual supported entry, tested boundaries and unimplemented production/customer/UI integration.
- [ ] Fetch, safely integrate concurrent main changes, then normal push to `yike-ai2026/main`; retain full V02 Goal ACTIVE.

### Task 2A: MCP read tool and domestic-model compatibility (root)

**Files:** create `pilot/research_tools.py`, `tests/test_research_tools.py`; add optional `research=["mcp==1.28.0"]` in pyproject/lock; internal run instructions `docs/RESEARCH_TOOLS.md`.

**Interfaces:** `build_server(*, max_reads: int, max_seconds: int, reader=read_public_page)` exposes only MCP tool `read_public_page(url)`. `python -m pilot.research_tools --max-reads 5 --max-seconds 60` uses stdio. Host limits cannot be supplied/changed in tool arguments; no model/tenant/credential parameter is accepted by the tool.

- [ ] SDK client RED tests: advertised input schema; two noncatalog domains; success/failure replay; read cap, session deadline, concurrent serialization; bad/extra input and callback errors return safe fixed codes.
- [ ] Implement official low-level SDK server (no custom JSON-RPC), optional dependency, bounded reads and explicit unreviewed output. Default application dependency versions stay fixed.
- [ ] Run SDK protocol tests, a subprocess stdio initialize/list/rejected-call test, and one anonymous public read as a transport probe, not a lead.
- [ ] Use a private temporary home/workspace, explicit domestic provider, existing authorized key loaded in-process, and no inherited Codex config/tools to test actual Codex response then MCP call/result continuation. Bound time/calls and report only safe status/usage/known test values; no secret/raw provider diagnostic persistence.
- [ ] Record compatibility or exact safe failure and next action. No silent provider/model substitution or production activation.

## Evidence

Implementation in progress. No new runtime/production/real lead claims are established by this plan.
