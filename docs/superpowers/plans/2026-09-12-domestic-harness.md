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

- [x] RED tests using actual localHTTP bridge request and synthetic `httpx.MockTransport`: roundtrip namespace/function declaration→flat alias; streamed `function_call` restored; next request input history converted; user/tool-argument dictionaries containing `type/function_call` unchanged. Use a synthetic key sentinel and assert no repr/error/status leakage.
```python
with ResponsesBridge(api_key='synthetic-key',model='test-model',max_requests=2,
                     deadline=monotonic()+10,
                     allowed_tools=(('mcp__yike_public','read_public_page'),),transport=transport) as bridge:
    response=httpx.post(bridge.base_url+'/responses',headers={'Authorization':'Bearer '+bridge.token},json=payload)
    assert response.status_code == 200
```
- [x] RED also covers wrongBearer/path/method, malformed/oversized payload, attempt cap and serial admission, expired deadline, provider400/body echo suppression, unknown function response, malformed/truncated SSE without response.completed, and cleanup. Provider unavailable≠successful empty response. No actual model requests.
- [x] Implement canonical stable ≤64char aliases with collision rejection. Transform only top-level tools, input items and response/event item structures; include outbound function-call history. Provider must receive host model and only allowed function tools. No silently accepting unknown shape. Remove only verified unsupported reasoning.summary.
- [x] Bound HTTP input and upstream response; use fixed upstream endpoint/httpx trust_env=False/no redirects/retries. Collect/validate response within task limits before sending a successful protocol body; no partial success. Terminal valid response.completed is required, provider errors become fixed safe502. Serial per-task request admission reserves count before external I/O. Context exit must close listeners/clients and active handlers.
- [x] Run `uv run --frozen --extra dev --extra research pytest -q tests/test_responses_bridge.py`, record RED/GREEN, `git diff --check`, commit only owned files. Report no-live-provider evidence to assigned report file.

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
- [x] RED fixture executable emits actual Codex JSONL shape (`item.completed/item:mcp_tool_call` with server/tool/arguments/result.structured_content, then agent_message/turn.completed). Assert no successful result from model-only answer, invalid/hash-mismatched read, foreign tool, terminalfailure, conflict/replayed item IDs. Usage validated ints excludingbool; missing staysNone. Actual stdout lines are authoritative, not parsed nested text.
- [x] Build explicit CLI with ephemeral/no-user-config/read-only/no git check/newtempworkspace; disable unrelated tools and empty MCP environment (`/usr/bin/env -i <python> -I -m pilot.research_tools ...`). Only fixed clean PATH, privateCODEX_HOME and temporarytoken enter Codex env; real API key stays bridge.
- [x] RED actual process tests timeout/cancel/outputcap and stalechild cleanup; inspect fixture-captured argv/env safely with synthetic markers, no provider access. Implement bounded pipe consumption and process-group cleanup with host monotonic deadline; no output persistence/raw errors.
- [x] Parse events while running, preserving valid facts/usage on terminalfailure but never upgrading partial status. Require actual completed authorized read and turn.completed for COMPLETED. Use existing `_valid_page` or equivalent authoritative field/hash validation; summary separate from evidence. `cancelled` remains host callback, not tool parameter.
- [x] Run changed test file, then one tiny authorized real public-page model call with explicit key loaded only in process from already-approved location. Report exact status/events/usage, not secret or raw provider payload. Compare Qwen only after knownlocalkey located; no silent model replacement.

### Task 3: Review and integration

- [x] Freeze concrete code SHA; independent architecture/code/quality review of the whole diff and targeted evidence; fix only real findings and delta-check.
- [ ] Update one evidence section and taskbook; fetch/integrate concurrent main preserving changes, normal push and live SHA parity. Retain GoalACTIVE; no fullsuite/build/deploy for this internal batch.

## Evidence

### Scope and targeted checks

- Root worker `36858ae`: initial missing-module RED; first implementation 18 passed/2 failed. Fixed actual subprocess working-directory isolation and made the cancellation regression trigger after an observed read instead of a startup timer. Two affected tests then passed; complete worker file: **20 passed in 9.76s**.
- Bridge `89f95dd` initially tested a nonrepresentative tool declaration. Correction `4dc0294` uses actual Codex namespace arrays, filters unrelated advertised tools and bounds incomplete socket bodies. New regressions were RED (5 failed/15 passed), then bridge file **20 passed in 8.41s**.
- Tests use synthetic provider transport/fixture executables for repeatable boundary checks; they are not model, search, customer or deployment proof. Existing reader suite, full product suite and installers were not rerun.

### Actual product-code transport checks

Two controlled calls used installed Codex **0.153.4**, `doubao-seed-2-1-turbo-260628`, the known authorized key loaded only in process, and only `https://example.com/`. Candidate `4dc0294` failed with `runtime_failed`, zero reads and unknown usage. The second call inspected only safe upstream status and SSE event types: **HTTP200**, valid `response.completed`, then `data: [DONE]`. The adapter erroneously parsed that sentinel as JSON and returned `provider_error`. This is an identified protocol defect, not a successful tool read or a model-quality result; correction and a real rerun are still required.

After correction, actual product-code candidate **`761dad7`** returned **COMPLETED in 7.73 seconds**. Two successful provider requests, one completed MCP read, no read failures; model summary matched the actual page title:

- URL `https://example.com/`; title `Example Domain`.
- Observed `2026-09-12T15:26:46Z`, SHA256 `8c1e8564424fdb68b8b7bdff3e16173a2e3599e9b71620637251486c5c4d5ed6`, scope `PUBLIC_PAGE_TEXT`, still UNREVIEWED.
- Codex reported 5,805 input tokens (2,360 cached), 63 output tokens. Provider receipts were 2,783/55 and 3,022/8 input/output. These are this call's reported usage, not a pricing calculation or representative task cost.
- Real key remained in the host/bridge process, never command arguments, Codex configuration, repository or logs. The probe inspected only public-page and usage/status metadata; no lead/customer/private-platform data was used.
- This proves **one supplied public URL → actual model/tool roundtrip → validated evidence**, not keyword search, unknown-source discovery, commercial lead quality, customer integration or deployment.

### Qwen comparison boundary

Read-only inspection located the expected TongYi/`qwen3.7-max` configuration in the **XingheAI2026V2 local real-Yudao model database**. The local Yudao/MySQL/Redis containers are stopped; actual stored key presence/validity remains unknown. No other-project service was started, no raw database files were extracted, and no Qwen request was sent. Do not infer Qwen availability or choose a winner from configuration scripts.

### Integration status

Independent whole-batch initial review of `4dc0294` found three P2s (unsupported actual calls, lost in-flight request records, drip-response absolute deadline), plus the separately root-confirmed `[DONE]` issue. Root fix `71c48de` captures records after bridge shutdown; its regression first failed, then three directly affected tests passed in 2.47s. Bridge fixes through `761dad7` passed 27 targeted tests in 12.13s. The first correction-only review resolved all except slow response headers; final fix **`33aa75899810a83f9af3498fb904525702f7b6a6`** starts the cutoff before connection/header I/O. The bridge file then passed **28 tests in 13.10s**. Independent deadline-only verification passed **2 tests in 1.67s**, and the same reviewer issued **internal integration GO**, no remaining P0/P1/P2. Final review is limited to this internal public-URL reading batch; the live provider evidence above remains bound to `761dad7`, not relabeled as a new provider run on `33aa758`.

No deployment, customer wiring or full Goal completion is claimed. Prior temporary probe success in the open-web plan does not certify this implementation. Concurrent remote Windows ACL work at `2a85dbc` has been fetched and will be preserved during integration. Full suites/builds/provider calls were not repeated for doc-only integration or the final deadline correction.
