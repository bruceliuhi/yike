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

- [x] Write failing tests for normal HTML/plaintext and a never-enumerated public domain, blocked DNS mixed addresses, TLS hostname preservation with pinned socket, redirect refusal, body/decoded text bounds, hidden HTML, invalid UTF8/charset policy, DNS timeout control flow and process reaping. Tests may replace transport/DNS only, not skip real extraction or validation.
- [x] Run reader tests and observe expected missing implementation failure.
- [x] Implement one bounded child operation using existing `_validate_url(url,'PUBLIC_WEB')`, stdlib HTTPS/socket/HTMLParser and strict bounded stdin/stdout. No unvalidated HTTP fallback or customer endpoint.
- [x] Reader tests and review regressions verified; see scoped evidence below. No real blocked-DNS claim from a replaced Popen timeout test.

### Task 2: Codex discovery and controller (root)

**Files:** create `pilot/codex_discovery.py`, `pilot/open_web_research.py`, `tests/test_codex_discovery.py`, `tests/test_open_web_research.py`; add packaged research method only if behavioral baseline demonstrates needed guidance.

**Interfaces:** a validated immutable mission carries public description, exclusions, source/search ceilings and duration; `CodexDiscovery.discover(mission, *, deadline)` returns URL suggestions and actual completed search events. `research_public_web(mission, *, discovery, reader=read_public_page, cancelled=lambda:False)` returns unreviewed evidence plus structured read failures. No writes/approval authority or direct resource store mutation in these adapters.

- [ ] Test subprocess with executable fixture emitting representative Codex JSONL: completed search, terminal final JSON, usage; no-search hallucination, malformed/huge output, failed turn, timeout, credential/argv/config isolation, too many searches.
- [ ] Implement actual `codex exec` adapter with explicit binary/model/secret, new empty private runtime home/workspace, read-only capabilities and bounded process I/O. Never read existing auth/config or launch an actual paid run during tests.
- [ ] Test controller across two unknown domains, repeated URLs, failures, deadline/cancel, no model text treated as raw evidence. Use real CandidateRecord validation for PAGE shape where feasible.
- [ ] Implement orchestration and document exact internal invocation and remaining task/transaction integration gate; run only changed tests.

### Task 3: Independent review and integration

- [x] Review reader/MCP concrete diff plus test evidence. Initial findings and two necessary lifecycle repair deltas closed at `7cb00f6`; Task 2 remains unimplemented and unreviewed.
- [x] Update taskbook with actual supported entry, tested boundaries and unimplemented production/customer/UI integration.
- [ ] Fetch, safely integrate concurrent main changes, then normal push to `yike-ai2026/main`; retain full V02 Goal ACTIVE.

### Task 2A: MCP read tool and domestic-model compatibility (root)

**Files:** create `pilot/research_tools.py`, `tests/test_research_tools.py`; add optional `research=["mcp==1.28.0"]` in pyproject/lock; internal run instructions `docs/RESEARCH_TOOLS.md`.

**Interfaces:** `build_server(*, max_reads: int, max_seconds: int, reader=read_public_page)` exposes only MCP tool `read_public_page(url)`. `python -m pilot.research_tools --max-reads 5 --max-seconds 60` uses stdio. Host limits cannot be supplied/changed in tool arguments; no model/tenant/credential parameter is accepted by the tool.

- [x] SDK client RED tests: advertised input schema; two noncatalog domains; success/failure replay; read cap, session deadline, concurrent serialization; bad/extra input and callback errors return safe fixed codes.
- [x] Implement official low-level SDK server (no custom JSON-RPC), optional dependency, bounded reads and explicit unreviewed output. Default application dependency versions stay fixed.
- [x] SDK protocol, real stdio initialize/list/rejected-call, and anonymous public-page transport probe completed, not a lead.
- [x] Private temporary home/workspace and explicit provider used for actual Codex response and MCP call/result continuation. Final successful roundtrip required a temporary protocol adapter; not yet shipped runtime.
- [x] Record compatibility, safe failures and next action. No silent provider/model substitution or production activation.

### Next: provider compatibility and actual research

- Implement/test a small server-owned Responses compatibility adapter: flatten namespace functions and restore namespaced calls, handle both request history and streamed responses, omit only verified unsupported provider parameters. No new Agent loop, no arbitrary forwarding endpoint, no personal config/key inheritance.
- Lock runtime/provider configuration and expose only admitted tools; add actual search separately from original reading. Connect mission budgets/cancellation and trustworthy event/evidence recording before a customer API.
- Qwen comparison is authorized but NOT_RUN until a locally configured credential is located. Use the same mission and original evidence for task quality, do not rank from plain text connectivity alone or silently downgrade the installed Codex.

## Evidence

### Code and independent review

Reader commits `bbff286`, `b5986cd`, `84b3b4f`; MCP/dependencies `9d14143`; repair deltas `bc58648`, `7cb00f6`. Initial reader **32 passed**, MCP **21 passed**. Whole-batch review first found 1 P1 (SDK stderr input echo) and 3 P2 (HTML state, incomplete HTTP body, process lifetime). Local regressions **9 failed / 53 passed**, fixes produced **62 passed in 2.39s** across the two changed test files.

Lifecycle delta review additionally reproduced blocked stdout flush and spawn/registration cancellation races. Targeted new RED **3 failed**; final changed lifecycle tests **6 passed in 3.38s**, plus late-start gate **1 passed in 0.25s**. These overlap earlier tests and are not additive full-suite totals. The final independent reviewer inspected exact `7cb00f6cb0e129493ca84d143e9661ca60ca4523` and closed all findings: **GO for this batch, 0 P0/P1/P2**. Previously passed unchanged suites were not repeated. `git diff --check` passed. No full build, production change, DB migration or UI change in this batch.

### Real transport and domestic-model diagnostics (2026-09-12)

Anonymous real reader call returned `READ`, `https://example.com/`, title `Example Domain`, 127 text characters, observation `2026-09-12T14:57:08Z`, textSHA256 `8c1e8564424fdb68b8b7bdff3e16173a2e3599e9b71620637251486c5c4d5ed6`. This is a public transport check, not buyer demand or full-site coverage.

Actual model is `doubao-seed-2-1-turbo-260628`; installed Codex `0.153.4`. Secret loaded only in the authorized local process, clean ephemeral Codex home/workspace, no inherited accounts/plugins, MCP launched with empty environment. Plain response succeeded; direct MCP run did not call the tool. Offline payload inspection showed namespace tools. Two tiny direct Responses probes returned namespace **400 InvalidParameter**, flat function **200 / function_call** (447 total tokens), isolating a protocol incompatibility rather than a key failure.

Temporary loopback diagnostic adapter (not committed/shipped) flattened tool namespaces and restored returned function-call names/namespace, including request history. Initial adapted request returned **400** on unsupported `reasoning.summary`; removing that field resulted in **two HTTP 200** requests, an actual completed MCP read and final answer `Example Domain`. Codex-reported usage: **7,249 input / 42 output**, of which 3,384 input cached; not a billing/搜贝 amount. No automatic retry or external messaging. This is one real tool roundtrip, not a reliability or lead-quality benchmark. Model metadata fallback warning remains to configure in the production adapter.

An isolated official `0.114.0` package was examined as a flat-tool comparison; its local `--help` process did not return promptly and was explicitly terminated/reaped. The installed Codex was not changed and no older runtime was adopted. The successful probe above uses current `0.153.4`.

Qwen: user authorized comparison; scoped environment/config lookup has not located a usable key, so **NOT_RUN**, not failed or inferior. User was asked only for the local file/software location, never the secret. Qwen official [Codex integration](https://help.aliyun.com/zh/model-studio/codex) and [Responses reference](https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-responses) establish an available integration path, not this account's tested access.

### Remaining delivery boundary

Task 1 and MCP tool slice are code-complete for an internal trusted host. Task 2, product provider adapter, search service, research Skill runtime, persistent task/budget/candidate wiring, customer progress, deployment and real cross-industry customer results remain open. Dedicated connectors/authorized browsers remain in place for login, comments and monitoring. No public success response or fixture counts as an approved opportunity, production rollout or completed V02 Goal.
