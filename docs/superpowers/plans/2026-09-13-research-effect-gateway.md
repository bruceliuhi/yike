# Host-Controlled Research Effects Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Implement independent source ownership in parallel, then one whole-batch spec/quality review and bounded fixes. Do not build desktop or deploy this internal slice.

**Goal:** A Codex research mission with an explicit trusted dispatcher cannot perform model, search or page-read IO outside that host dispatcher; page workers are owned and canceled per mission, not globally.
**Architecture:** Extend the existing Responses bridge with optional host model dispatch and private read endpoint; keep search caching and add dispatch after cache admission. Move controlled MCP reads to a strict loopback client. This is the prerequisite gateway for the same-PG permit/journal design, not the database implementation or customer capability.
**Tech Stack:** Existing Python/httpx/MCP/Codex, no new dependencies.

## Global Constraints

- Design basis: `docs/superpowers/specs/2026-09-13-dynamic-customer-research-integration-design.md`. Preserve legacy no-dispatcher calls, old task results, original Skill and fixed customer sources. New customer capability remains disabled.
- This batch implements the complete internal three-effect gate, NOT PG permits, customer context-v2 or supervisor. Never claim a callback is a persisted permit. Next integrate the dispatcher with same-PG task/permit/context/action journal before exposing customer execution.
- Model/search credentials stay in host/owned worker stdin only. MCP gets only literal loopback URL and ephemeral token. No arbitrary routes, redirects, environment proxy, login, or external messages.
- Dispatcher is trusted host code, not JSON supplied by client/model. Failure or invalid dispatcher/result fails closed; no fallback network request. All dispatch errors have fixed public messages, never exception text.
- Scope all action deadlines by monotonic host deadline; permit callback may shorten but never extend. Existing model and search request/read ceilings still apply, no blind retry after unknown/failed work. Network action callable is at-most-once even if dispatcher calls it twice.
- Keep exact existing read/search envelopes. `_valid_page` may move to `open_web_reader.valid_page_evidence` with a compatibility alias; research_tools/worker keep same imports callable. Evidence must be validated at host and MCP; search snippets never source evidence.

### Task 1: Effect dispatcher, model/search hooks and bridge read endpoint

**Own:** new `pilot/research_effects.py`; `pilot/responses_bridge.py`; `pilot/public_search.py`; new `tests/test_research_effects.py`; affected `tests/test_responses_bridge.py` and `tests/test_public_search.py`.

**Interfaces shared with root/Task 2:**

```python
class EffectDispatchError(RuntimeError):
    # fixed message 'effect_unavailable'; do not retain exception/payload
    ...

def dispatch_effect(dispatcher, *, kind, payload, deadline, perform):
    # kind in MODEL,SEARCH,READ. dispatcher(kind, payload_copy, deadline, guarded_perform)
    # guarded_perform(effective_deadline: float) -> dict
    # None dispatcher is legacy direct perform(deadline); non-None must be callable.
    # return dict; callers validate their exact result contract.
    ...
```

- [ ] RED tests: dispatcher denial/exception/invalid type zero perform, duplicate perform prevented, shortened deadline received, NaN/bool/past/extended deadlines prevented before perform; deepcopy payload and result; deadline elapsed while queued prevents IO; no exception secret echoed. Use finite JSON dict validation and bounded 2MiB payload/result; deadline finite <= original host deadline and >now. Result dict may be trusted persisted replay with no perform; domain caller still validates it. Default None legacy path keeps behavior, not claimed accounting.
- [ ] Implement `dispatch_effect`: copy plain finite JSON with <=2MiB UTF8 bound, validate kind/callables/deadline; once-lock around guarded_perform admission, no lock held across action; refuse repeated invocation even after failure; check deadline again at actual invocation and before handing result back; wrap exceptions as fixed EffectDispatchError. Only dispatcher receives clean payload, never callable secrets in serialized input.
- [ ] `PublicSearchSession(..., effect_dispatcher=None)` adds optional callable validation. After existing cache/attempt admission and inside operation lock, dispatch SEARCH payload `{'query':normalized}`; guarded action calls `_run(normalized, deadline=effective_deadline)`. `_run` optional deadline only shortens all communicate/pre/post checks. Validate `valid_search_result` before caching/return; exceptions => existing unavailable failure, no retry. Cache hit never dispatches again. Add `allows_read(url)->bool` with normalized exact URL membership in successful cached results only, no network; closed returns False. Existing default behavior/fixtures remain compatible.
- [ ] `ResponsesBridge(..., effect_dispatcher=None, read_service=None)` adds optional callable dispatcher and read_service requiring read/close. Expose `read_url = base_url+'/public-read'` only when service supplied (else None). Route POST /v1/public-read behind SAME token/content/size/closed/deadline checks, payload exact {'url'}; call read_service.read(url, deadline=self._deadline) returning read envelope; validate success with valid_page_evidence or fixed failure fields, invalid=>FAILED/unavailable. GET/wrong route/token never reads. Close only owned read_service (its close is idempotent).
- [ ] Bridge MODEL dispatch around actual `_forward`, payload is normalized outbound (already forced model). Adapter perform returns JSON-safe `{'status':int,'code':str,'body':str,'usage':dict|None}` from `_forward(outbound, deadline=effective_deadline)`; bytes→UTF8 SSE. Validate exact shape/status/code/body cap/usage types before serving; invalid/denied => fixed error, no untrusted header/body forwarding. Preserve SSE validation/tool restoration, request counters, locks, cancellation, explicit assistant status fix. `_forward` optional deadline shortens timer/pre/post checks, never mutates shared mission deadline. Keep callback result usage separate from lead approval; no callback calls in legacy None mode besides default direct wrapper.
- [ ] GREEN affected three files, no full suite/provider. Commit only owned files. Report RED/GREEN and any contract conflict before guessing.

### Task 2: Mission-owned page reads and strict read client

**Own:** `pilot/open_web_reader.py`; new `pilot/public_read_session.py`; new `pilot/read_tool_client.py`; affected `tests/test_open_web_reader.py`; new `tests/test_public_read_session.py`, `tests/test_read_tool_client.py`.

**Consumes:** Task 1 `dispatch_effect`; `PublicSearchSession.allows_read(url)` (inject callable in session, not whole search object). Bridge read_service interface below.

```python
class PublicPageReader:
    def read(self, url, *, deadline): ...  # aware datetime -> existing raw evidence dict
    def close(self): ...  # cancel/reap own workers only; idempotent, blocks later reads

class PublicReadSession:
    def __init__(self, *, max_reads, deadline, allowed_url, effect_dispatcher, reader=None): ...
    def read(self, url, *, deadline): ...  # monotonic float -> existing READ/FAILED envelope
    def close(self): ...

class ReadToolClient:
    def __init__(self, *, url, token): ...
    def read(self, url, *, deadline): ...  # aware datetime -> raw evidence or PublicReadError
```

- [ ] RED per-reader isolation: closing reader A cancels/reaps A child and prevents new A IO, not B or legacy global reads. Refactor existing read process function into a shared private implementation with explicit lock/active-set/is-stopped scope; legacy `read_public_page` and `cancel_active_reads` retain their process-global behavior/tests. New PublicPageReader owns separate scope, not resetting any global stopped flags. Move `_valid_page` semantics from research_tools into `valid_page_evidence(value,url)` here, avoid import cycles (root will alias it in research_tools).
- [ ] PublicReadSession validates strict max_reads 1..100, finite mission deadline within1800s, callable allowed_url/dispatcher, reader object read/close or create PublicPageReader. Normalize HTTPS before operation; host checks allowed_url EACH call even cache hit; no discovered URL => invalid_url and zero read/dispatch. Serialize/cache by normalized URL with used count; unknown/failure cached, no retry; remaining=min(mission,requested deadline), max20s per page; dispatch READ payload {'url':normalized}; convert action effective monotonic deadline into aware UTC for reader. Dispatch result is raw page evidence; validate hash/url/time/text/type before READ envelope, otherwise fixed FAILED invalid_read_result/unavailable. No claimed review approval. Closed/expired/over-budget fixed failure; per-mission close cancels reader and prevents late results from succeeding. Never call global cancel_active_reads here.
- [ ] ReadToolClient modeled after SearchToolClient but only '/v1/public-read', literal127.0.0.1 HTTP and ephemeraltoken validation. Host/proxy/redirect isolation, <=300000 response bytes, <=min(21sec, supplied aware deadline) with client-close timer. Exact read envelope or fixedfailure; validate raw evidence via valid_page_evidence, return evidence notenvelope to existing MCP reader callback; no fallback to direct public IO if endpoint unavailable/malformed/unauthorized. Map unsupported failure codes to PublicReadError unavailable, preserve allowed reader codes. Reject public/proxy/userinfo/wrongroute config.
- [ ] GREEN only owned affected files; no provider/public-page IO. Commit only own files; report tests/concerns.

### Task 3: Controlled mission wiring and protocol verification (root)

**Own:** `pilot/codex_research_worker.py`, `pilot/research_tools.py`, `tests/test_codex_research_worker.py`, `tests/test_research_tools.py`, new `tests/test_research_effect_gateway.py`, docs.

- [ ] Add optional keyword `effect_dispatcher` with omitted sentinel to run_public_research_mission/_run_mission. Omitted keeps old internal modes; explicitly None/noncallable => invalid_configuration before tempdir/search/bridge/subprocess/cancel. Valid dispatcher passed to search/bridge and new PublicReadSession(max_reads,deadline,allowed_url=search_service.allows_read,effect_dispatcher). No new result fields/claim of customer permit.
- [ ] Wrap dispatcher with existing cancelled() check before each effect; callback failures block IO. Controlled `_command` adds YIKE_PUBLIC_READ_URL/TOKEN to MCP env -i args from bridge only; no supplied business/real secrets. In research_tools.main, when either read URL/token exists build ReadToolClient; partial/invalidconfig fails, never default reader. With no read config keep legacy behavior. `_valid_page` compatibility alias to new validator.
- [ ] RED integration tests prove real loopback bridge + MCP stdio tool uses host READ, allowed_url from actually successful search, denial means no external mocked transport/read action; repeated cached query/URL dispatch once; closure/cancellation no later effect. Fixture Codex process exercises actual command/env and emits protocol events; no model success invented. Preserve old7/9fields and research binding, originalcontext guard tests.
- [ ] GREEN targeted affected root files plus one combined same-flow protocol check, then freeze SHA and independent entire batch review. Packaging/deployment/PG-permit ledger/customercapability NOT implemented here; record exact boundary and next context/journal wiring. No actual provider retry merely for wiring proof; real customer research later after authenticated PG chain exists.

## Evidence

Pending. This is a prerequisite of the full customer dynamic-research path, not its completion. Full goal ACTIVE.
