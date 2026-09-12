# Domestic Codex Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Repository instructions replace per-file reviews with one independent batch review.

**Goal:** A callable server-side Codex + domestic provider + real read-tool worker, retaining evidence and failure boundaries.

**Architecture:** Temporary authenticated loopback Responses bridge and isolated Codex subprocess; reuse existing MCP reader. No new Agent loop, search claim, customer API, DB or deployment.

**Tech Stack:** Python3.11+, stdlib, existing httpx, optional research MCP, explicit Codex0.153.4-compatible binary.

## Global Constraints

- Only fixed `https://ark.cn-beijing.volces.com/api/v3/responses` provider endpoint; no arbitrary forwarder or inherited credentials/config. Key passed in process, never argv/files/logs; Codex receives only a random temporary bridge token.
- Public research text≤4000 chars; task1..1800 seconds, provider1..20 requests, reader1..100 attempts; each request/response/process output≤2MiB. Unknown usage stays unknown; no automatic retry/send/login.
- Explicit host tool allowlist, currently `mcp__yike_public.read_public_page`; filter unrelated advertised tools, fail unknown actual calls. Specialized connectors untouched.
- New isolated Codex home/workspace and POSIX process group, cleanup success/failure/cancel/output limit. Runtime flags do not replace deployment container isolation.
- Scope/exact boundaries in `docs/superpowers/specs/2026-09-12-domestic-harness-design.md`. No production activation or full Goal completion; only affected tests and one necessary independent review.

### Task 1: Bounded Responses bridge

**Files:** create `pilot/responses_bridge.py`, `tests/test_responses_bridge.py`. Own only these files.

**Interface:**
```python
class BridgeError(Exception): ... # fixed safe code only
class ResponsesBridge:
    def __init__(self, *, api_key: str, model: str, max_requests: int,
                 deadline: float, allowed_tools: tuple[tuple[str,str],...],
                 transport=None): ...
    # deadline=time.monotonic() absolute; transport defaults to httpx.HTTPTransport(retries=0)
    # transport can be httpx.MockTransport for deterministic transport tests.
    def __enter__(self): ... # self.base_url, self.token; 127.0.0.1 randomport
    def __exit__(self, *exc): ... # release server and in-flight operations
    @property
    def records(self) -> list[dict]: ... # safe snapshots: ordinal/status/code/usage/elapsed_seconds
```

- [ ] RED tests using actual localHTTP bridge request and synthetic `httpx.MockTransport`: roundtrip namespace/function declaration→flat alias; streamed `function_call` restored; next request input history converted; user/tool-argument dictionaries containing `type/function_call` unchanged. Use a synthetic key sentinel and assert no repr/error/status leakage.
```python
with ResponsesBridge(api_key='synthetic-key',model='test-model',max_requests=2,
                     deadline=monotonic()+10,
                     allowed_tools=(('mcp__yike_public','read_public_page'),),transport=transport) as bridge:
    response=httpx.post(bridge.base_url+'/responses',headers={'Authorization':'Bearer '+bridge.token},json=payload)
    assert response.status_code == 200
```
- [ ] RED also covers wrongBearer/path/method, malformed/oversized payload, attempt cap and serial admission, expired deadline, provider400/body echo suppression, unknown function response, malformed/truncated SSE without response.completed, and cleanup. Provider unavailable≠successful empty response. No actual model requests.
- [ ] Implement canonical stable ≤64char aliases with collision rejection. Transform only top-level tools, input items and response/event item structures; include outbound function-call history. Provider must receive host model and only allowed function tools. No silently accepting unknown shape. Remove only verified unsupported reasoning.summary.
- [ ] Bound HTTP input and upstream response; use fixed upstream endpoint/httpx trust_env=False/no redirects/retries. Collect/validate response within task limits before sending a successful protocol body; no partial success. Terminal valid response.completed is required, provider errors become fixed safe502. Serial per-task request admission reserves count before external I/O. Context exit must close listeners/clients and active handlers.
- [ ] Run `uv run --frozen --extra dev --extra research pytest -q tests/test_responses_bridge.py`, record RED/GREEN, `git diff --check`, commit only owned files. Report no-live-provider evidence to assigned report file.

### Task 2: Isolated Codex research worker (root)

**Files:** create `pilot/codex_research_worker.py`, `tests/test_codex_research_worker.py`; extend `docs/RESEARCH_TOOLS.md` with actual internal invocation.

**Interface:**
```python
def run_public_read_mission(description: str, *, codex_binary: str, python_binary: str,
                            api_key: str, model: str, max_reads: int = 5,
                            max_requests: int = 8, max_seconds: int = 120,
                            cancelled=lambda:False) -> dict: ...
# {status, code, reads, read_failures, summary, usage, provider_calls}
# status COMPLETED/FAILED/CANCELLED; reads are actual unreviewed tool records.
```
- [ ] RED fixture executable emits actual Codex JSONL shape (`item.completed/item:mcp_tool_call` with server/tool/arguments/result.structured_content, then agent_message/turn.completed). Assert no successful result from model-only answer, invalid/hash-mismatched read, foreign tool, terminalfailure, conflict/replayed item IDs. Usage validated ints excludingbool; missing staysNone. Actual stdout lines are authoritative, not parsed nested text.
- [ ] Build explicit CLI with ephemeral/no-user-config/read-only/no git check/newtempworkspace; disable unrelated tools and empty MCP environment (`/usr/bin/env -i <python> -I -m pilot.research_tools ...`). Only fixed clean PATH, privateCODEX_HOME and temporarytoken enter Codex env; real API key stays bridge.
- [ ] RED actual process tests timeout/cancel/outputcap and stalechild cleanup; inspect fixture-captured argv/env safely with synthetic markers, no provider access. Implement bounded pipe consumption and process-group cleanup with host monotonic deadline; no output persistence/raw errors.
- [ ] Parse events while running, preserving valid facts/usage on terminalfailure but never upgrading partial status. Require actual completed authorized read and turn.completed for COMPLETED. Use existing `_valid_page` or equivalent authoritative field/hash validation; summary separate from evidence. `cancelled` remains host callback, not tool parameter.
- [ ] Run changed test file, then one tiny authorized real public-page model call with explicit key loaded only in process from already-approved location. Report exact status/events/usage, not secret or raw provider payload. Compare Qwen only after knownlocalkey located; no silent model replacement.

### Task 3: Review and integration

- [ ] Freeze concrete code SHA; independent architecture/code/quality review of the whole diff and targeted evidence; fix only real findings and delta-check.
- [ ] Update one evidence section and taskbook; fetch/integrate concurrent main preserving changes, normal push and live SHA parity. Retain GoalACTIVE; no fullsuite/build/deploy for this internal batch.

## Evidence

Implementation not yet complete. Prior temporary successful probe is documented in the open-web plan; it does not certify this new code.
