# Durable Research Effects Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development; root owns PG admission/journal, one implementer owns effect validation/dispatcher. One whole-batch independent review, then delta fixes only.

**Goal:** Connect the existing MODEL/SEARCH/READ host gateway to authenticated, version-bound PostgreSQL permits and durable results, suitable for the next customer supervisor vertical.

**Architecture:** Reuse `ResearchResourceStore.begin` with an internal transaction-local issued hook to insert the journal atomically with the permit. Reuse current profile/strategy/material checks and coordinator ownership/generation/lease; do not duplicate allowance logic or hold transactions across network. A serial dispatcher calls the existing gateway perform callback only for a newly issued journal entry; known results replay, unknown/in-flight entries stop without resending.

**Tech Stack:** Existing Python/psycopg/PostgreSQL/RLS, Codex gateway and Responses parser. No added dependencies.

## Global Constraints

- Existing `docs/superpowers/specs/2026-09-13-dynamic-customer-research-integration-design.md` and approved V0.2 apply. No new customer capability/API, pricing, deployment, Windows build, credentials, real provider calls or outreach in this foundation batch. Supervisor, candidate publication, UI and real effects validation remain mandatory next.
- Context comes from `CustomerResearchContextStore` and its immutable v2 binding, not client facts. Validate current confirmed context before admission/replay; inside fresh permit transaction recompile stored context and require the same binding and strategy snapshot. Never call the separate-transaction context loader while holding its profile/task locks.
- `MODEL` consumes `MODEL_CALL`; `SEARCH` and `READ` each consume `SOURCE_READ`. Reuse original reservation/rule and max-count checks; no guessed pricing, refunds or duplicate allowance table.
- Logical sequence is a strict integer 1..1000, stable per task/run (not reset by generation). Action UUID derives from run UUID + task ID + sequence. Bind kind, complete canonical payload and full context binding into input SHA256. Generation is the actual coordinator generation, not existing resource `research_generation=1`.
- Coordinator owner is canonical UUID; generation strict integer 1..2147483647. Fresh admission requires matching task/run, owner, generation, RUNNING and future lease. Per-effect deadline is earliest task/permit deadline, lease deadline and worker monotonic deadline. A cached result still requires current authority/coordinator and exact input/context identity.
- Journal and permit insert/finish are atomic in one PG transaction. Active session is rechecked before commit. No network transaction. Acknowledgement uncertainty leaves occupied permit; never retry effects or refund automatically. Issued/UNKNOWN/FAILED replay does not invoke callback. Cancellation/lease loss prevents new effects; a previously admitted result may be recorded after cancellation or lease loss without authorizing continuation. Session revocation can prevent recording, leaving UNCERTAIN; no admin runtime fallback.
- Journal input/result are strict plain JSON dicts, each <=2MiB canonical UTF8; secret patterns rejected, fixed errors only. No credentials/URLs with session tokens persisted. SEARCH input exact query; READ input exact normalized anonymous HTTPS URL. MODEL input is already bridge-transformed request, contains model/input/tools/stream and only known public tool aliases; complete request is bound, not a partial prompt digest.
- Valid result: SEARCH must satisfy existing `valid_search_result`, READ `valid_page_evidence` against exact input URL. MODEL envelope must satisfy bridge envelope validation plus completed restored SSE/usage and tools allowed by its input. Reuse SSE parser without restoring aliases twice; arbitrary text is not a successful model result. Successful result revalidated on replay. Any returned failure/invalid result or thrown transport exception becomes UNKNOWN with no replayable result; no success/failure certainty invented.
- Same-owner RLS, minimal SELECT/INSERT/terminal-field UPDATE grants; immutable journal inputs and terminal records, context/permit/coordinator links. Persist original page text/hash, not only result summary; content publication into candidate records remains next vertical.

### Task 1: Validated effect contract and serial dispatcher (agent)

**Own:** new `pilot/research_effect_contract.py`, new `pilot/durable_research_dispatch.py`, new `tests/test_research_effect_contract.py`, new `tests/test_durable_research_dispatch.py`. Avoid editing bridge; reuse its parser with a restored-item validator in the new contract.

Interfaces produced:

```python
def effect_input(kind, payload, context_binding) -> tuple[dict, str]:
    # validated copied payload and SHA256 of {schema_version:'research-effect-input-v1',kind,payload,context_binding}
def effect_result(kind, payload, result) -> dict:
    # only validated successful copied result; raises ExecutionRuntimeError('invalid_effect_result',422)
class DurableResearchDispatcher:
    def __init__(self, journal, claims, *, task_id, run_id, generation, coordinator_owner, context_binding): ...
    def __call__(self, kind, payload, deadline, perform) -> dict: ...
```

Journal dependency supplied by root:

```python
journal.begin(claims, *, task_id, run_id, sequence, generation, coordinator_owner,
              context_binding, kind, payload) -> {'created': bool, 'entry': dict}
journal.finish(claims, *, task_id, run_id, sequence, permit_id, status, result=None) -> dict
# entry includes task_id,run_id,sequence,generation,coordinator_owner,kind,payload,input_sha256,
# context_binding,action_id,permit_id,deadline_at (aware ISO),status,result,output_sha256
```

- [ ] RED pure input/result fixtures: wrong types/control/secret/URLs/oversize, bad/unknown restored SSE function calls, usage mismatch; legitimate restored public tool calls stay unchanged. Fixed safe errors. Known aliases use `responses_bridge._alias` for mcp__yike_public/search_public_web and read_public_page.
- [ ] Implement effect_input using bounded JSON helpers; binding must have exact v2 compiler binding fields with valid schema/hash/UUID strings (reuse compiler format, do not accept arbitrary metadata). Validate model fields/tool aliases, preserve unchanged request contents. Implement result validation with existing SEARCH/READ validators and reused SSE parser whose restored-item hook validates identity rather than rewriting names; assert completed envelope usage matches returned usage.
- [ ] RED dispatcher with fake journal only: sequence ordering/concurrent serialized calls, begin denial zero perform; earlier effective deadline; create→perform→finish order; success is returned only after finish acknowledgement and identity/result match; transport/validation failure occupies UNKNOWN; finish failure no fallback second finish; replay ISSUED/UNKNOWN/FAILED no perform; success replay validated and no extra finish. Invalid/expired deadline must fail before begin. Do not conflate this with PG proof.
- [ ] Dispatcher uses lock and increasing sequence; each call binds all constructor scope, monotonic/UTC conversion for remaining deadline, and closes on first uncertainty/error so later calls cannot bypass failed sequence. Do not silently restart from sequence1 after failure or expose automatic resume. Exceptions must be fixed `EffectDispatchError` at gateway boundary. `BaseException` handling must not leak indefinite callbacks or reissue.
- [ ] Run only owned two test files, commit only owned files, report exact RED/GREEN and scope. No DB/provider/build calls.

### Task 2: Atomic PG journal and gateway integration (root)

**Own:** `pilot/research_resources.py` internal issued hook; new `pilot/research_effect_journal.py`; migration142 and grant; `pilot/db.py`; new `tests/test_research_effect_journal_postgres.py`; targeted worker/gateway integration test and docs.

- [ ] RED restricted PG actual confirmed dynamic task + context and coordinator fixture. Before callback, both permit and ISSUED journal must already be visible from another connection; successful finish updates both, replay identical without additional permits.
- [ ] Add optional `_on_issued(cursor,tenant,event)` to resource.begin; validate callable before DB access, invoke only newly created permit after INSERT and before final active-session check, in same transaction; previous/default paths unchanged. Callback failure rolls back permit. No invocation on replay.
- [ ] Add migration142 `pilot_research_effect_journal`: owner/task/run/sequence PK, unique action/permit, kind enum, actual generation/owner, context binding JSON, input payload/hash, aware effective deadline, state ISSUED/SUCCEEDED/FAILED/UNKNOWN, result/output digest. FK immutable customer context and permit (cascade for admin fixture cleanup), coordinator task/run. Before INSERT guard verifies context binding, permit identity/input/resource, matching live coordinator and bounded deadline; UPDATE only allows ISSUED→terminal fields matching finished permit, terminal immutable. Input/result JSONB storage allows rendering whitespace but Python canonical caps remain2MiB. Register migration and restricted grants.
- [ ] Implement journal.begin with effect_input and canonical scope validation; load authenticated context in independent completed transaction before resources.begin. In fresh admission callback compare current stored compiled binding/snapshot with event, lock actual coordinator and cap lease; issued hook inserts journal with expected identity. Read replay under active claims, require same generation/owner/coordinator live, exact input+context and same permit status/hash; reject missing/tampered/in-flight/unknown entries for automatic execution. Result expiry does not justify repeating old action.
- [ ] Implement journal.finish as short owner/permit/journal transaction, validate successful result and digest; lock event then journal in consistent order, update resource terminal fields and journal result atomically. Replay identical finalization only; do not require live task/coordinator for already admitted facts, but active authenticated session and same permit/sequence. No new effect/automatic continuation authority.
- [ ] PG tests: real restricted role, duplicate/concurrent begin one permit; input/owner/generation mismatch; old profile/material/session/cancel/lease loss deny next admission; quota exhaustion no extra entries; failed issued hook rollback; finish rollback/no partial event/result; UNKNOWN never re-executes; post-cancel result recorded but no further perform; immutable result and tenant isolation. Use own disposable database only.
- [ ] Actual host gateway `dispatch_effect` + DurableResearchDispatcher + journal with synthetic perform validates sequence of MODEL→SEARCH→READ, persisted usage/real original payload and no duplicate IO/replay. Explicitly synthetic provider, not actual customer UAT. Run affected resource regression, owned tests and one wholebatch review, delta fixes, latestmain merge/push parity and remove only owned disposable test container.

## Evidence

Final code `b1e007a554bdbd47552314758e04c10f859e0067`: independent whole-batch and focused delta **Spec PASS / Quality PASS, ready to merge**. Base `97b2d8d`; root journal `e026588`, contract/dispatcher `419bd0f`, credential hardening `5d61d38`, review fixes `b80fc30` and `b1e007a`. Root journal derives action UUID as `uuid5(UUID(run_id), f'{task_id}:{sequence}')`; sequence cannot skip an issued/unknown/failed predecessor. Dispatcher bounds actual I/O by the earlier worker deadline and persisted task/lease ceiling. No automatic worker restart is added.

Observed RED: missing journal module; quoted credential/control-key handling failed three pure cases; successful replay incorrectly bypassed current capability/rule in two PG cases. The latter is fixed by same-transaction current-authority validation before returning the entry, not by changing legacy resource replay behavior. Empty deployment grant verification also exposed missing context/journal grants and a stale test treating the separate ops grant as a runtime grant; context/journal are included, ops remains explicitly separate.

Targeted GREEN (2026-09-13):
- Agent contract + dispatcher: **32 passed**, pure/fake-journal only; no DB or network claim.
- Root `tests/test_research_effect_journal_postgres.py`, `tests/test_research_resources_postgres.py`, `tests/test_research_effect_gateway.py`: **48 passed in 55.45s** using an owned disposable PostgreSQL16 database and restricted application role.
- `tests/test_empty_deployment_grants.py`: **2 passed in 0.50s** with a new non-owner LOGIN role on that isolated DB; complete runtime grant manifest exercised twice, ops never granted.
- Independent review found embedded credential/encoded URL handling and finish-result substitution gaps; fixed with **7 RED → 40 PASS**, then in-place mutation/userinfo refinements **2 RED → 42 PASS in 0.66s**. Expected result/digest freeze before finish; returned acknowledgement must match. Both findings independently closed at `b1e007a`.
- Root actual PG commit followed by synthetic lost ACK: **1 passed in 2.05s** at `c43b603`; no second effect/finish, persisted success remains. Post-first-review-fix gateway/UNKNOWN/lost-ACK integration: **3 passed in 4.66s** at `b80fc30`. No repeated full suite or provider requests.

PG evidence includes atomic issued-hook failure and result rollback, concurrent duplicate admission, current owner/generation/lease/profile/strategy/rule/capability, final-session fence rollback, RLS, SQL forged-entry/immutable-result guards, UNKNOWN occupancy, no sequence gaps, quota exhaustion and post-cancel closeout. Actual `dispatch_effect → DurableResearchDispatcher → ResearchEffectJournal` executes synthetic MODEL→SEARCH→READ: a second DB connection sees the permit and journal before each callback; complete original text and model SSE/usage persist; successful replay causes no additional callback or resource event. These callbacks are synthetic, not external providers or useful customer leads. Existing customer-context material-revocation checks remain inherited through the same loader/strategy path; this batch does not claim a new real-platform material scenario.

No credentials/provider calls, new capability/API, candidate publication, frontend change, Windows build, deployment or external messages. Full goal ACTIVE; next mandatory batch is dynamic customer supervisor + generic candidate evidence + existing UI/API vertical, followed by real same-budget research quality and cross-day evidence. Do not rerun this helper batch as a substitute for that path.

Tasks 1 and 2 are complete for this internal foundation; the checklist above retains the original test/implementation requirements. Merge/push and final narrow integration are recorded in the task handoff, not treated as deployment. A classified public-page failure versus an uncertain execution remains a customer-loop design consideration: this foundation stops on non-success and must not be marketed as already reproducing the local Skill's source-switching behavior.
