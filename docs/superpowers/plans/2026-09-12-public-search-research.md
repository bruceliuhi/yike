# Public Search Research Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Repository instruction replaces repeated per-task reviews with one independent whole-batch review.

**Goal:** Codex selects queries, searches real public sources and reads discovered originals without turning snippets into evidence.

**Architecture:** Fixed Serper search session on host; subprocess-bound request and private stdin key; existing authenticated loopback bridge exposes optional search route. MCP gets only temporary URL/token; new research worker records search observations separately.

**Tech Stack:** Existing Python/httpx/MCP/Codex, stdlib search child; no added dependency or production activation.

## Global Constraints

- Design `docs/superpowers/specs/2026-09-12-public-search-research-design.md` binds exact fields/statuses/bounds. Fixed https://google.serper.dev/search, POST `{q:query,num:10,hl:"zh-cn"}`, X-API-KEY, no arbitrary forwarding/proxy/redirect/retry.
- Query1–512 chars, max_searches1–10, task1–1800seconds, each search20seconds/1MiB; host limits only. Keys never argv/env/repo/logs; provider subprocess stdin only. Random temporary loopback token is not a provider credential.
- Search results are SEARCH_RESULTS observations, not original posts, verified buyers, dates or approved leads. Preserve empty-vs-failed and omitted_count; max10safeuniqueHTTPS URLs. Only actual discovered URLs readable in new search mode; existing read-only behavior remains.
- No login/sending, DB/customerAPI/persistentbudget/deploy; no personal Codex settings/keys inherited. One review, affected tests only. Same-source/same-query repeats never inflate facts.

### Task 1: Bounded search session and result contract

**Own files:** create `pilot/public_search.py`, `pilot/public_search_worker.py`, `tests/test_public_search.py` only.

**Interfaces:**
```python
normalize_query(query: str) -> str  # ValueError('invalid_query') fixed only
valid_search_result(value: dict, query: str) -> bool
class PublicSearchSession:
    def __init__(self, *, api_key: str, max_searches: int, deadline: float): ...
    def search(self, query: str) -> dict: ... # exact SEARCHED/FAILED design structure
    def close(self): ... # idempotent, stop new work and terminate/reap owned children
```

- [ ] Write failing contract tests: canonical query caching,10resultcap/urlnormalization/dedup/omitted_count, nullablehints, awareobservedtime, malformedorganic≠empty, fixedfailurecode, boundedfieldvalues. Example assert `session.search(' 中文   需求 ')['query']=='中文 需求'` and result read_scope SEARCH_RESULTS, not READ. Fake low-level HTTP in child module only for deterministic response parsing, not returning whole fake domain service.
- [ ] Write missing-module/behavior RED with `uv run --frozen --extra dev --extra research pytest -q tests/test_public_search.py`. Add real fixture-process deadline/close tests and inspect synthetickey absentargv/env; receiveskey onlystdin. Test concurrent samequery consumes one attempt and closing prevents spawn race.
- [ ] Implement session serial/cache/count reservation with own active-process lock and close flag; do not reuse global READS_STOPPED. Spawn isolatedPython worker `-I` with env{} and private stdin `{query,api_key,timeout_seconds}`; child stdlib HTTP fixedendpoint, headerkey, 1MiB body cap and no rawerror. Child response exact `{ok:true,result}` or `{ok:false,code}`; parent validates result and limits, kills/reaps at min(20,deadline-now). Payload/output bounded; child network data cannot echo key into result. No test-only public methods.
- [ ] GREEN targetedfile, diffcheck, commit only owned files. Report RED/GREEN/commit/remaininglimits, no live provider or credential reads by this agent.

### Task 2: Codex research mode and actual-event bookkeeping

**Own files:** `pilot/codex_research_worker.py`, `tests/test_codex_research_worker.py` only.

**Consumes Task1:** PublicSearchSession(api_key,max_searches,deadline), normalize_query, valid_search_result.
**Consumes root:** ResponsesBridge optional `search_service=None` constructor, `.search_url` URL orNone; existing token. MCP env accepts `YIKE_PUBLIC_SEARCH_URL` and `YIKE_PUBLIC_SEARCH_TOKEN` only when enabled. MCP tool name `search_public_web`; namespace same `mcp__yike_public`. Root owns gateway/MCP implementation.
**Produces:**
```python
run_public_research_mission(description: str, *, codex_binary: str, python_binary: str,
                           api_key: str, model: str, search_api_key: str,
                           max_searches: int = 3, max_reads: int = 5,
                           max_requests: int = 8, max_seconds: int = 120,
                           cancelled=lambda:False) -> dict
# oldresultfields + searches:list[SEARCHED], search_failures:list[{query,code}]
```

- [ ] RED actual JSONL fixtures: real `mcp_tool_call` server yike_public/tool search_public_web/argumentsquery/result.structured_content plus read; invalidsearchschema/foreignurl/duplicateID conflict rejects; modeltext alone notsearch, valid searchzeroresults retained with no_verified_reads. Old read-onlyfixtures keep exact resultshape and originalmission semantics.
- [ ] RED subprocess config checks: provider andsearchkey absent env/argv/cwd/prompt; onlytemporaryURL/token passedMCP env. New mode allowstwofunctions and instructions explicitly search thenread; oldmode nosearch. Snapshot providerrecords aftercleanup, close search session even onspawn/enter/error/cancel. Reject key substrings inpublicdescription.
- [ ] Implement shared internal runner conservatively, preserve public oldfunctionsignature. Search events use Task1validator, dedupactualeventIDs; readURLs mustbelongto actualcompletedsearchresults in newmode. Finalcode no_verified_searches if no actualSEARCHED, no_verified_reads if search butno original. Source/modeltext remainseparate, no autonomousretry/leadapproval.
- [ ] Targeted changedfile GREEN (may wait for Task1 imports; no fakeproductionstub), diffcheck, commitownedfiles; report tests/commit/concerns. No realprovider/keyaccess byagent.

### Task 3: Loopback and MCP integration (root)

**Files:** `pilot/responses_bridge.py`, `pilot/research_tools.py`, new `pilot/search_tool_client.py`, corresponding tests, `docs/RESEARCH_TOOLS.md`.

- [ ] RED live loopback route: unauthenticated/unknownroute disabled, exactquerypayloadonly, no modelquota consumed, serviceclose oncontext exit, safeerrors. Bridge optionalservice drives exact `/v1/public-search` after existing Bearer/sizevalidation, responsevalidatedfixedcontract; defaultbridgeunchanged.
- [ ] RED MCP officialsession advertisessearch only opt-in, successful SEARCHED adds allowedreadURLs; only original reader can return READ; searchfailure emptydistinct; URL/tokenconfiguration mustbe fixedloopbackhttp with exactpath and numericport, no userinfo/query/fragment, not publicarbitraryrequest. `search_tool_client` POST uses httpx trust_env=False/no redirects, boundedresponse, fixederrorcodes. Credentials onlytemp token fromhostenv.
- [ ] Implement and run only affectedtests including old MCP/bridge regressions; no fullsuite/build. Existing hardwatchdog/reader cleanup retained.
- [ ] One tiny authorized real Codex/Ark/Serper mission from existing keys loadedinprocess, public Chinese query only, ≤2searches/2reads/5modelcalls/90sec. Report actualurls/time/status, snippets notbuyerfacts; failedsources notno-demand.

### Task 4: Independent review and integration

- [ ] Freeze code SHA, generate reviewpackage, freshindependentreview; fix realfindingswithnarrowtests/deltareview only.
- [ ] Update single evidence section/taskbook, fetch/preserveconcurrentmain, merge/push/verifyliveparity. Goal remainsfullACTIVE; thisisresearchcapability, notall-platform/production/customerproof.

## Evidence

Pending implementation. Existing Serper config key presence checked boolean-only at known siblingproject; validity not yet tested. Prior read-onlyCodex batch f9fc299 remains completed, not rerun.
